"""
Trading Bot Backend - Refactored with Modular Routes and Database Abstraction
Main FastAPI server supporting both MongoDB (server) and SQLite (desktop)
"""
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from contextlib import asynccontextmanager
import os
import sys
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List
import discord
from discord.ext import commands
import asyncio
import uuid

# Import models
from models import Alert, Settings
from order_execution import (
    build_client_order_id,
    build_oco_exit_plan,
    calculate_option_buy_limit_price,
)
# Import utilities
from discord_ingestion import DiscordIngestionDeps, handle_discord_message
from openclaw_discord_config import resolve_saved_or_runtime_discord_config

# Import new professional features
from risk import (
    SQLiteDuplicateAlertStore,
    is_duplicate_alert,
    calculate_position_size,
    check_correlation,
)
from source_config import apply_source_quantity_limits
from settings_flags import coerce_bool
from entry_alignment import (
    EntryAlignmentDecision,
    apply_alignment_quantity,
    disabled_entry_alignment,
    evaluate_entry_alignment,
    entry_slippage_size_cap,
)
from notifications import (
    notify_trade_filled, notify_trade_failed,
    notify_auto_shutdown, notify_discord_disconnected,
    notify_correlation_block,
)
from fill_monitor import monitor_fill
from fill_reconciliation import (
    BrokerOrderUpdate,
    OrderContext,
    reconcile_order_update,
    trade_owns_alert_status,
)
from trade_lifecycle import build_exit_plans, is_exit_alert
from utils import normalize_expiration_for_order

# Import database abstraction
from database import init_database, get_db, USE_SQLITE, MongoDBDatabase
from database_paths import configured_database_path

# Import routes
from routes import (
    health_router, brokers_router, settings_router, 
    discord_router, profiles_router, trading_router,
    operator_router, analytics_router,
    bot_bus_router, pairing_router, init_routes, update_bot_status, set_discord_bot
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'tradebot')
SQLITE_PATH = configured_database_path()
duplicate_alert_store = SQLiteDuplicateAlertStore(SQLITE_PATH) if USE_SQLITE else None

# MongoDB clients (only used if not using SQLite)
mongo_client = None
mongo_db = None
sync_mongo_client = None
sync_mongo_db = None

if not USE_SQLITE:
    from motor.motor_asyncio import AsyncIOMotorClient
    import pymongo
    mongo_client = AsyncIOMotorClient(MONGO_URL)
    mongo_db = mongo_client[DB_NAME]
    sync_mongo_client = pymongo.MongoClient(MONGO_URL)
    sync_mongo_db = sync_mongo_client[DB_NAME]

# Discord bot reference
discord_bot = None
discord_bot_thread = None


def check_duplicate_alert(parsed: dict) -> bool:
    """Use a process-shared store in SQLite mode so workers do not double-enter alerts."""
    return is_duplicate_alert(parsed, store=duplicate_alert_store)


async def update_alert_status(alert_id: str, updates: dict[str, Any], *, db=None) -> None:
    """Persist alert status through the database abstraction layer."""
    db_obj = db if db is not None else get_db()
    update_alert = getattr(db_obj, "update_alert", None)
    if update_alert is not None:
        result = update_alert(alert_id, updates)
        if hasattr(result, "__await__"):
            await result
        return

    if db is not None:
        raise AttributeError(f"{type(db_obj).__name__} does not implement update_alert")

    if USE_SQLITE:
        from database_sqlite import update_alert as update_sqlite_alert

        update_sqlite_alert(alert_id, updates)
        return

    sync_mongo_db.alerts.update_one(
        {'id': alert_id},
        {'$set': updates},
    )


def _load_settings_sync() -> dict:
    """Load settings from the sync path used by the Discord bot thread."""
    if USE_SQLITE:
        from database_sqlite import get_settings
        return get_settings()

    settings_doc = sync_mongo_db.settings.find_one({'id': 'main_settings'})
    return settings_doc if settings_doc else {}


def _record_discord_runtime_config(token: str, channel_ids: List[str] | str) -> None:
    channels = _normalize_channel_ids(channel_ids)
    update_bot_status("discord_token_configured", bool(str(token or "").strip()))
    update_bot_status("discord_channel_count", len(channels))


# Discord Bot Factory
def create_discord_bot(token: str, channel_ids: List[str]):
    """Create and configure the Discord bot"""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    @bot.event
    async def on_ready():
        logger.info(f'Discord bot logged in as {bot.user}')
        update_bot_status('discord_connected', True)
    
    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return
        
        if channel_ids and str(message.channel.id) not in channel_ids:
            return
        
        def insert_alert_sync(alert: Alert):
            if USE_SQLITE:
                # FIXED C7 note: still bypasses DatabaseInterface abstraction.
                # Full fix: use asyncio.run_coroutine_threadsafe() with the main loop.
                from database_sqlite import insert_alert
                insert_alert(alert.model_dump())
            else:
                sync_mongo_db.alerts.insert_one(alert.model_dump())

        def increment_alerts_processed():
            from routes.health import bot_status
            update_bot_status('alerts_processed', bot_status.get('alerts_processed', 0) + 1)

        result = await handle_discord_message(
            message,
            channel_ids=channel_ids,
            deps=DiscordIngestionDeps(
                load_settings=_load_settings_sync,
                insert_alert=insert_alert_sync,
                process_trade=process_trade,
                update_status=update_bot_status,
                is_duplicate_alert=check_duplicate_alert,
                increment_alerts_processed=increment_alerts_processed,
                card_database=get_db(),
            ),
            bot_user=bot.user,
        )
        if result.skip_reason and result.skip_reason not in {"unparsed", "self message", "channel not monitored"}:
            logger.info("[on_message] skipped alert: %s", result.skip_reason)
        
        await bot.process_commands(message)
    
    return bot


def _plain_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def _mapping_from_model(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {}


async def _reconcile_local_positions_before_entry(db_obj, settings: Settings, settings_raw: dict, log_context: str) -> None:
    broker_client = None
    try:
        from bot_managed_exits import reconcile_local_positions_against_broker
        from order_execution import get_configured_broker_client

        broker_client = get_configured_broker_client(
            settings_raw,
            settings.active_broker.value,
            require_order_status=True,
        )
        stale = await reconcile_local_positions_against_broker(db_obj, broker_client, settings_raw)
        if stale.get("closed"):
            logger.info(
                "[%s] closed %s stale local broker position(s) before entry matching",
                log_context,
                stale["closed"],
            )
    except Exception as exc:
        logger.warning("[%s] broker position reconciliation skipped before entry matching: %s", log_context, exc)
    finally:
        if broker_client is not None:
            from order_execution import close_broker_client

            await close_broker_client(broker_client)


async def resolve_entry_alignment(
    alert: Alert,
    settings: Settings,
    settings_raw: dict,
) -> EntryAlignmentDecision:
    """Load point-in-time Alpaca context and produce a non-blocking sizing decision."""
    if not settings.smart_sizing_enabled:
        return disabled_entry_alignment()

    context: dict[str, Any] = {}
    broker_client = None
    try:
        from order_execution import get_configured_broker_client

        broker_client = get_configured_broker_client(
            settings_raw,
            settings.active_broker.value,
            require_order_status=True,
        )
        loader = getattr(broker_client, "get_entry_market_context", None)
        if loader is not None:
            context = await loader(
                ticker=alert.ticker,
                strike=alert.strike,
                option_type=alert.option_type,
                expiration=alert.expiration,
            )
    except Exception as exc:
        logger.warning("[entry_alignment] context unavailable for %s: %s", alert.ticker, exc)
    finally:
        if broker_client is not None:
            from order_execution import close_broker_client

            await close_broker_client(broker_client)

    return evaluate_entry_alignment(
        option_type=alert.option_type,
        bars=context.get("bars") if isinstance(context, dict) else [],
        option_bid=context.get("option_bid") if isinstance(context, dict) else None,
        option_ask=context.get("option_ask") if isinstance(context, dict) else None,
        agreement_percent=settings.smart_sizing_agreement_percent,
        mixed_percent=settings.smart_sizing_mixed_percent,
        conflict_percent=settings.smart_sizing_conflict_percent,
        source=str(context.get("source") or settings.active_broker.value) if isinstance(context, dict) else settings.active_broker.value,
    )


async def _process_starter_buy_alert(
    alert: Alert,
    settings: Settings,
    settings_raw: dict,
    source_config: dict | None = None,
    *,
    pending_trade_result: str | None = None,
    log_context: str = "process_trade",
) -> tuple[bool, str | None]:
    """Submit a starter BUY using the standard entry path."""
    from models import Trade

    source_config = source_config or {}
    trade_executed = False
    trade_result = None

    try:
        db_for_entry = get_db()
        await _reconcile_local_positions_before_entry(db_for_entry, settings, settings_raw, log_context)
        open_positions = await db_for_entry.get_positions("open")
        partial_positions = await db_for_entry.get_positions("partial")
        closed_positions = await db_for_entry.get_positions("closed")
        from entry_controls import existing_contract_entry_block_reason

        block_reason = existing_contract_entry_block_reason(
            list(open_positions or []) + list(partial_positions or []) + list(closed_positions or []),
            {
                "ticker": alert.ticker,
                "strike": alert.strike,
                "option_type": alert.option_type,
                "expiration": alert.expiration,
            },
            alert.raw_message,
            alert_id=alert.id,
            allow_fresh_entry_after_close=coerce_bool(
                source_config.get("allow_fresh_entry_after_close"),
                default=False,
            ),
        )
    except Exception as e:
        logger.warning(f"[{log_context}] entry-state duplicate check unavailable: {e}")
        block_reason = None
    if block_reason:
        logger.warning("[%s] trade BLOCKED: %s", log_context, block_reason)
        return False, block_reason

    # 1. Risk-based position sizing.
    from entry_controls import alert_risk_size_cap, resolve_entry_exit_profile

    risk_language_cap, risk_language_reasons = alert_risk_size_cap(
        alert.raw_message,
        cap_percent=settings.coordinated_high_risk_size_percent,
    )
    entry_risk_profile = "high_risk" if risk_language_reasons else "normal"
    entry_exit_profile = resolve_entry_exit_profile(alert.raw_message, source_config)
    estimated_stop_loss_percent = (
        settings.coordinated_high_risk_stop_loss_percent
        if entry_risk_profile == "high_risk"
        else settings.coordinated_normal_stop_loss_percent
    )
    quantity = calculate_position_size(
        entry_price=alert.entry_price,
        default_quantity=settings.default_quantity,
        max_position_size=settings.max_position_size,
        risk_multiplier=source_config.get("risk_multiplier", 1.0),
        max_loss_per_trade=(
            settings.max_loss_per_trade if settings.risk_budget_sizing_enabled else None
        ),
        stop_loss_percent=(
            estimated_stop_loss_percent if settings.risk_budget_sizing_enabled else None
        ),
    )
    quantity = apply_source_quantity_limits(quantity, source_config)
    if quantity <= 0:
        logger.warning(
            "[%s] trade BLOCKED: one contract for %s exceeds max_position_size",
            log_context,
            alert.ticker,
        )
        return False, "blocked: position size limit"

    base_quantity = quantity
    alignment = await resolve_entry_alignment(alert, settings, settings_raw)
    sizing_percent = float(alignment.multiplier_percent)
    alignment_context = alignment.as_dict()
    alignment_context.update(
        {
            "entry_risk_profile": entry_risk_profile,
            "entry_exit_profile": entry_exit_profile,
            "risk_budget_sizing_enabled": settings.risk_budget_sizing_enabled,
            "max_loss_budget": settings.max_loss_per_trade,
            "estimated_stop_loss_percent": estimated_stop_loss_percent,
        }
    )
    if risk_language_cap is not None:
        sizing_percent = min(sizing_percent, risk_language_cap)
        alignment_context.update(
            {
                "market_alignment_percent": float(alignment.multiplier_percent),
                "multiplier_percent": sizing_percent,
                "risk_language_cap_percent": risk_language_cap,
                "risk_language_reasons": risk_language_reasons,
            }
        )
    if settings.entry_slippage_sizing_enabled:
        slippage_cap, slippage_percent = entry_slippage_size_cap(
            alert.entry_price,
            alignment.option_ask,
            warning_percent=settings.entry_slippage_warning_percent,
            severe_percent=settings.entry_slippage_severe_percent,
            warning_size_percent=settings.entry_slippage_warning_size_percent,
            severe_size_percent=settings.entry_slippage_severe_size_percent,
            mode=settings.entry_slippage_mode,
        )
        alignment_context["entry_slippage_percent"] = slippage_percent
        if slippage_cap is not None:
            if slippage_cap <= 0:
                return False, "blocked: entry price beyond binary slippage limit"
            sizing_percent = min(sizing_percent, slippage_cap)
            alignment_context.update(
                {
                    "slippage_size_cap_percent": slippage_cap,
                    "multiplier_percent": sizing_percent,
                }
            )
    quantity = apply_alignment_quantity(base_quantity, sizing_percent)
    logger.info(
        "[%s] entry alignment=%s score=%+.1f sizing=%.0f%% quantity=%s/%s",
        log_context,
        alignment.tier,
        alignment.alignment_score,
        sizing_percent,
        quantity,
        base_quantity,
    )
    try:
        from operator_audit import record_operator_event

        await record_operator_event(
            get_db(),
            "entry_intelligence",
            "entry_size_selected",
            f"Selected {quantity} of {base_quantity} contracts for {alert.ticker} {alert.option_type}.",
            details={
                "alert_id": alert.id,
                "ticker": alert.ticker,
                "strike": alert.strike,
                "option_type": alert.option_type,
                "expiration": alert.expiration,
                "base_quantity": base_quantity,
                "selected_quantity": quantity,
                "decision": alignment_context,
            },
        )
    except Exception as exc:
        logger.warning("[%s] could not persist entry alignment telemetry: %s", log_context, exc)

    # 2. Correlation / concentration check.
    # We need the async db abstraction here.  In the SQLite path we use
    # asyncio.get_event_loop() since we're already inside the Discord
    # bot's own event loop.
    try:
        db_for_risk = get_db()
        allowed, block_reason = await check_correlation(
            ticker=alert.ticker,
            db=db_for_risk,
            settings=settings_raw,
        )
    except Exception as e:
        logger.error(f"[{log_context}] blocking trade because correlation check failed: {e}")
        allowed, block_reason = False, "Risk controls unavailable"

    if not allowed:
        logger.warning(f"[{log_context}] trade BLOCKED: {block_reason}")
        try:
            open_count = int(block_reason.split()[2]) if block_reason else 0
        except (IndexError, ValueError):
            open_count = 0
        await notify_correlation_block(
            ticker=alert.ticker,
            open_count=open_count,
            max_count=int(settings_raw.get("max_positions_per_ticker", 3)),
            settings=settings_raw,
        )
        return False, f"blocked: {block_reason}"

    # 3. Build the trade record.
    source_card = alert.card_action if isinstance(alert.card_action, dict) else {}
    trade = Trade(
        alert_id=alert.id,
        ticker=alert.ticker,
        strike=alert.strike,
        option_type=alert.option_type,
        expiration=alert.expiration,
        entry_price=alert.entry_price,
        quantity=quantity,
        broker=settings.active_broker.value,
        simulated=False,
        entry_alignment_tier=alignment.tier,
        entry_alignment_score=alignment.alignment_score,
        entry_sizing_percent=sizing_percent,
        entry_alignment_context=alignment_context,
        entry_risk_profile=entry_risk_profile,
        entry_exit_profile=entry_exit_profile,
        max_loss_budget=settings.max_loss_per_trade,
        estimated_stop_loss_percent=estimated_stop_loss_percent,
        source_reported_stop_price=source_card.get("reported_stop_price"),
        source_reported_stop_percent=source_card.get("reported_stop_percent"),
        source_reported_break_even_stop=bool(source_card.get("reported_break_even_stop")),
    )

    # Place with broker, store as "pending", start fill monitor.
    trade.status = "pending"
    order_id = None
    broker_client = None
    fill_monitor_started = False

    limit_price = calculate_option_buy_limit_price(
        alert.entry_price,
        premium_buffer_enabled=settings.premium_buffer_enabled,
        premium_buffer_amount=settings.premium_buffer_amount,
        live_ask=alignment.option_ask,
        marketable_entry_enabled=settings.marketable_entry_enabled,
    )
    if settings.premium_buffer_enabled:
        buffer_applied = limit_price - alert.entry_price
        logger.info(
            "[%s] applying premium cap: +$%.2f (limit: $%.2f)",
            log_context,
            buffer_applied,
            limit_price,
        )

    try:
        from order_execution import get_configured_broker_client

        broker_client = get_configured_broker_client(
            settings_raw,
            settings.active_broker.value,
            require_order_status=True,
        )
        order_result = await broker_client.place_order(
            ticker=alert.ticker,
            strike=alert.strike,
            option_type=alert.option_type,
            expiration=alert.expiration,
            side="BUY",
            quantity=quantity,
            price=limit_price,
            client_order_id=build_client_order_id(alert.id, "BUY"),
        )
        order_id = order_result.get("order_id")
        if not order_id:
            raise ValueError(order_result.get("error", "Broker did not return an order id"))
        trade.order_id = order_id
        logger.info(
            f"[{log_context}] placed order {order_id} for "
            f"{quantity}x {alert.ticker} ${alert.strike} {alert.option_type}"
        )
        trade_result = pending_trade_result
    except Exception as e:
        trade.status = "failed"
        trade.error_message = str(e)
        trade_result = f"failed: {trade.error_message}"
        logger.error(f"[{log_context}] order placement failed: {e}")
        await notify_trade_failed(
            trade.id, alert.ticker, alert.strike, alert.option_type,
            str(e), settings_raw,
        )

    # Persist the trade (pending or failed)
    if USE_SQLITE:
        from database_sqlite import insert_trade
        insert_trade(trade.model_dump())
    else:
        sync_mongo_db.trades.insert_one(trade.model_dump())

    # 4. Fill confirmation monitor.
    if trade.status == "pending" and order_id:
        try:
            db_obj = get_db()
            asyncio.create_task(monitor_fill(
                order_context=OrderContext(
                    trade_id=trade.id,
                    order_id=order_id,
                    side="BUY",
                    ticker=alert.ticker,
                    strike=alert.strike,
                    option_type=alert.option_type,
                    expiration=alert.expiration,
                    requested_quantity=quantity,
                    broker=settings.active_broker.value,
                    alert_id=alert.id,
                    alert_price=alert.entry_price,
                    simulated=False,
                    entry_risk_profile=entry_risk_profile,
                    entry_exit_profile=entry_exit_profile,
                    max_loss_budget=settings.max_loss_per_trade,
                    estimated_stop_loss_percent=estimated_stop_loss_percent,
                    source_reported_stop_price=trade.source_reported_stop_price,
                    source_reported_stop_percent=trade.source_reported_stop_percent,
                    source_reported_break_even_stop=trade.source_reported_break_even_stop,
                ),
                broker_client=broker_client,
                db=db_obj,
                settings=settings_raw,
                close_broker_client_when_done=True,
            ))
            fill_monitor_started = True
        except Exception as e:
            logger.error(f"[{log_context}] failed to start fill monitor: {e}")

    if broker_client is not None and not fill_monitor_started:
        from order_execution import close_broker_client

        await close_broker_client(broker_client)

    return trade_executed, trade_result


async def process_trade(alert: Alert, parsed: dict):
    """Process a trade based on parsed alert — with risk sizing, correlation check, fill monitoring."""
    # Get settings
    if USE_SQLITE:
        from database_sqlite import get_settings
        settings_dict = get_settings()
    else:
        settings_doc = sync_mongo_db.settings.find_one({'id': 'main_settings'})
        settings_dict = settings_doc if settings_doc else {}

    settings = Settings(**settings_dict) if settings_dict else Settings()
    settings_raw = settings_dict or {}
    trade_executed = False
    trade_result = None

    if parsed['alert_type'] == 'buy':
        trade_executed, trade_result = await _process_starter_buy_alert(
            alert,
            settings,
            settings_raw,
            source_config=parsed.get("_source_config") or {},
        )
    elif parsed["alert_type"] == "average_down":
        average_down_result = await process_average_down_alert(
            alert,
            parsed,
            settings,
            settings_raw,
            source_config=parsed.get("_source_config") or {},
        )
        if isinstance(average_down_result, tuple):
            trade_executed, trade_result = average_down_result
        else:
            trade_executed = average_down_result
    elif is_exit_alert(parsed):
        trade_executed = await process_exit_alert(
            alert,
            parsed,
            settings,
            settings_raw,
            source_config=parsed.get("_source_config") or {},
        )
        trade_result = parsed.get("_exit_skip_reason")
    else:
        logger.info("[process_trade] unsupported alert_type=%s", parsed.get("alert_type"))

    # Update alert status.
    updates = {'processed': True, 'trade_executed': trade_executed}
    if parsed.get("_resolved_alert_type"):
        updates["alert_type"] = parsed["_resolved_alert_type"]
    if is_exit_alert(parsed):
        updates['exit_trigger'] = str(parsed.get("exit_trigger") or "sell_alert")
    if trade_result is not None:
        updates['trade_result'] = trade_result
    await update_alert_status(alert.id, updates)


async def process_average_down_alert(
    alert: Alert,
    parsed: dict,
    settings: Settings,
    settings_raw: dict,
    source_config: dict | None = None,
) -> bool:
    """Resolve explicit adds against position state, then scale in or open a fresh re-entry."""
    from models import Trade
    from entry_controls import explicit_reentry_allowed

    source_config = source_config or {}
    explicit_reentry = explicit_reentry_allowed(alert.raw_message)

    db_obj = get_db()
    await _reconcile_local_positions_before_entry(db_obj, settings, settings_raw, "process_average_down_alert")
    open_positions = await db_obj.get_positions("open")
    partial_positions = await db_obj.get_positions("partial")
    candidates = [
        position
        for position in open_positions + partial_positions
        if _average_down_position_matches(position, parsed)
    ]
    if not candidates:
        if explicit_reentry:
            parsed["_resolved_alert_type"] = "buy"
            logger.info(
                "[process_average_down_alert] explicit re-entry has no matching open position; "
                "opening a fresh starter BUY",
            )
            return await _process_starter_buy_alert(
                alert,
                settings,
                settings_raw,
                source_config=source_config or {},
                pending_trade_result="pending: explicit re-entry opened fresh buy",
                log_context="process_reentry_alert",
            )
        if not settings.averaging_down_enabled:
            logger.info("[process_average_down_alert] averaging down is disabled")
            return False
        logger.info(
            "[process_average_down_alert] no matching open position for %s; falling back to starter BUY",
            parsed,
        )
        return await _process_starter_buy_alert(
            alert,
            settings,
            settings_raw,
            source_config=source_config or {},
            pending_trade_result="pending: average_down fallback opened starter buy",
            log_context="process_average_down_alert",
        )

    if not settings.averaging_down_enabled:
        logger.info("[process_average_down_alert] averaging down is disabled")
        return False

    position = candidates[0]
    if int(position.get("average_down_count") or 0) >= int(settings.averaging_down_max_buys):
        logger.warning("[process_average_down_alert] max average-down buys reached for %s", position.get("id"))
        return False

    entry_price = float(position.get("entry_price") or 0.0)
    alert_price = float(alert.entry_price or parsed.get("entry_price") or 0.0)
    if entry_price <= 0 or alert_price <= 0:
        logger.warning("[process_average_down_alert] missing valid entry price for %s", position.get("id"))
        return False

    drop_pct = ((entry_price - alert_price) / entry_price) * 100
    if drop_pct < float(settings.averaging_down_threshold):
        logger.info(
            "[process_average_down_alert] price drop %.2f%% is below threshold %.2f%%",
            drop_pct,
            settings.averaging_down_threshold,
        )
        return False

    quantity = _average_down_quantity(position, alert_price, settings, source_config or {})
    if quantity <= 0:
        logger.warning("[process_average_down_alert] average-down blocked by position size controls")
        return False

    trade = Trade(
        alert_id=alert.id,
        ticker=alert.ticker,
        strike=alert.strike,
        option_type=alert.option_type,
        expiration=alert.expiration,
        entry_price=alert_price,
        quantity=quantity,
        side="BUY",
        broker=settings.active_broker.value,
        simulated=False,
    )

    limit_price = calculate_option_buy_limit_price(
        alert_price,
        premium_buffer_enabled=settings.premium_buffer_enabled,
        premium_buffer_amount=settings.premium_buffer_amount,
    )
    if settings.premium_buffer_enabled:
        logger.info(
            "[process_average_down_alert] applying premium cap: +$%.2f (limit: $%.2f)",
            limit_price - alert_price,
            limit_price,
        )

    broker_client = None
    try:
        from order_execution import get_configured_broker_client

        broker_client = get_configured_broker_client(
            settings_raw,
            settings.active_broker.value,
            require_order_status=True,
        )
        order_result = await broker_client.place_order(
            ticker=alert.ticker,
            strike=alert.strike,
            option_type=alert.option_type,
            expiration=alert.expiration,
            side="BUY",
            quantity=quantity,
            price=limit_price,
            client_order_id=build_client_order_id(alert.id, "AVG-DOWN", position["id"]),
        )
        order_id = order_result.get("order_id")
        if not order_id:
            raise ValueError(order_result.get("error", "Broker did not return an order id"))
        trade.order_id = order_id
        trade.status = "pending"
        await db_obj.insert_trade(trade.model_dump())
        asyncio.create_task(
            monitor_fill(
                order_context=OrderContext(
                    trade_id=trade.id,
                    order_id=order_id,
                    side="BUY",
                    ticker=alert.ticker,
                    strike=alert.strike,
                    option_type=alert.option_type,
                    expiration=alert.expiration,
                    requested_quantity=quantity,
                    broker=settings.active_broker.value,
                    position_id=position["id"],
                    alert_id=alert.id,
                    alert_price=alert_price,
                    simulated=False,
                ),
                broker_client=broker_client,
                db=db_obj,
                settings=settings_raw,
                close_broker_client_when_done=True,
            )
        )
        return False
    except Exception as exc:
        trade.status = "failed"
        trade.error_message = str(exc)
        await db_obj.insert_trade(trade.model_dump())
        logger.error("[process_average_down_alert] average-down order failed: %s", exc)
        await notify_trade_failed(
            trade.id,
            trade.ticker,
            trade.strike,
            trade.option_type,
            str(exc),
            settings_raw,
        )
        if broker_client is not None:
            from order_execution import close_broker_client

            await close_broker_client(broker_client)
        return False


def _average_down_quantity(
    position: dict[str, Any],
    alert_price: float,
    settings: Settings,
    source_config: dict[str, Any],
) -> int:
    original_quantity = max(1, int(position.get("original_quantity") or position.get("remaining_quantity") or 1))
    try:
        source_multiplier = float(source_config.get("risk_multiplier", 1.0))
    except (TypeError, ValueError):
        source_multiplier = 1.0
    if source_multiplier <= 0:
        source_multiplier = 1.0
    desired_quantity = max(
        1,
        int(original_quantity * (float(settings.averaging_down_percentage) / 100.0) * source_multiplier),
    )

    remaining_quantity = max(0, int(position.get("remaining_quantity") or 0))
    current_basis = float(position.get("entry_price") or 0.0) * remaining_quantity * 100
    available_budget = float(settings.max_position_size) - current_basis
    risk_quantity = int(available_budget / (alert_price * 100)) if alert_price > 0 else 0
    return apply_source_quantity_limits(min(desired_quantity, risk_quantity), source_config)


def _average_down_position_update(
    position: dict[str, Any],
    *,
    trade_id: str,
    quantity: int,
    entry_price: float,
    settings_raw: dict,
    alert_id: str,
) -> dict:
    remaining_before = max(0, int(position.get("remaining_quantity") or position.get("quantity") or 0))
    original_before = max(remaining_before, int(position.get("original_quantity") or remaining_before))
    new_remaining = remaining_before + quantity
    new_original = original_before + quantity
    current_basis = float(position.get("entry_price") or 0.0) * remaining_before * 100
    added_cost = entry_price * quantity * 100
    new_total_cost = current_basis + added_cost
    new_entry_price = new_total_cost / (new_remaining * 100)
    current_price = entry_price
    highest_price = max(float(position.get("highest_price") or 0.0), current_price)
    set_update = {
        "entry_price": new_entry_price,
        "current_price": current_price,
        "original_quantity": new_original,
        "remaining_quantity": new_remaining,
        "total_cost": round(new_total_cost, 2),
        "average_down_count": int(position.get("average_down_count") or 0) + 1,
        "initial_entry_price": position.get("initial_entry_price") or position.get("entry_price"),
        "highest_price": highest_price,
        "status": "open",
    }
    if position.get("oco_exit_protected") or position.get("oco_exit_plan"):
        oco_exit_plan = build_oco_exit_plan(
            settings_raw,
            alert_id=alert_id,
            position_id=position.get("id"),
            entry_price=new_entry_price,
            quantity=new_remaining,
        )
        if oco_exit_plan:
            set_update["oco_exit_plan"] = oco_exit_plan
            set_update["oco_exit_protected"] = True

    return {"$set": set_update, "$push": {"trade_ids": trade_id}}


def _average_down_position_matches(position: dict[str, Any], parsed: dict) -> bool:
    if str(position.get("status", "open")).lower() not in {"open", "partial"}:
        return False
    if str(position.get("ticker") or "").strip().upper() != str(parsed.get("ticker") or "").strip().upper():
        return False
    try:
        if abs(float(position.get("strike")) - float(parsed.get("strike"))) >= 0.001:
            return False
    except (TypeError, ValueError):
        return False
    if str(position.get("option_type") or "").strip().upper() != str(parsed.get("option_type") or "").strip().upper():
        return False
    return _date_key(position.get("expiration")) == _date_key(parsed.get("expiration"))


def _date_key(value: Any) -> str:
    return str(normalize_expiration_for_order(value) or value or "").strip().upper().replace("-", "/")


async def _resolve_alert_exit_price(
    broker_client,
    position: dict[str, Any],
    reported_price: float | None,
) -> float:
    """Use an executable broker quote, not the analyst's already-filled sale price."""
    loader = getattr(broker_client, "get_option_market_context", None)
    if loader is not None:
        try:
            context = await loader(
                ticker=str(position.get("ticker") or "").upper(),
                strike=float(position.get("strike") or 0.0),
                option_type=str(position.get("option_type") or "").upper(),
                expiration=str(position.get("expiration") or ""),
            )
            bid = float((context or {}).get("option_bid") or 0.0)
            if bid > 0:
                return round(bid, 2)
        except Exception as exc:
            logger.warning(
                "[process_exit_alert] fresh option bid unavailable for %s: %s",
                position.get("id"),
                exc,
            )

    for key in ("option_bid", "current_price"):
        try:
            value = float(position.get(key) or 0.0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return round(value, 2)
    try:
        fallback = float(reported_price or 0.0)
    except (TypeError, ValueError):
        fallback = 0.0
    if fallback > 0:
        return round(fallback, 2)
    raise ValueError(
        f"No executable option bid is available for position {position.get('id')}"
    )


async def process_exit_alert(
    alert: Alert,
    parsed: dict,
    settings: Settings,
    settings_raw: dict,
    source_config: dict | None = None,
) -> bool:
    """Process sell/trim/close alerts against matching open positions."""
    from models import Trade, Position

    db_obj = get_db()
    broker_client = None
    broker_positions_failed = False
    try:
        from order_execution import get_configured_broker_client

        broker_client = get_configured_broker_client(
            settings_raw,
            settings.active_broker.value,
            require_order_status=True,
        )
    except Exception as exc:
        logger.warning("[process_exit_alert] broker client unavailable before reconciliation: %s", exc)

    if broker_client is not None:
        try:
            from bot_managed_exits import (
                get_broker_positions_snapshot,
                reconcile_pending_exit_orders,
                reconcile_broker_positions,
                reconcile_local_positions_against_broker,
            )

            broker_positions, broker_positions_failed = await get_broker_positions_snapshot(broker_client)
            if broker_positions_failed:
                logger.warning("[process_exit_alert] broker position snapshot failed before exit matching")
            else:
                repaired_exits = await reconcile_pending_exit_orders(
                    db_obj,
                    broker_client,
                    settings_raw,
                )
                if repaired_exits:
                    logger.info(
                        "[process_exit_alert] reconciled %s pending exit order(s) before exit matching",
                        repaired_exits,
                    )
                imported = await reconcile_broker_positions(
                    db_obj,
                    broker_client,
                    settings_raw,
                    broker_positions=broker_positions,
                    broker_positions_failed=False,
                )
                if imported:
                    logger.info("[process_exit_alert] imported %s broker position(s) before exit matching", imported)
                stale = await reconcile_local_positions_against_broker(
                    db_obj,
                    broker_client,
                    settings_raw,
                    broker_positions=broker_positions,
                    broker_positions_failed=False,
                )
                if stale.get("closed"):
                    logger.info(
                        "[process_exit_alert] closed %s stale local broker position(s) before exit matching",
                        stale["closed"],
                    )
        except Exception as exc:
            broker_positions_failed = True
            logger.warning("[process_exit_alert] broker position reconciliation failed before exit matching: %s", exc)
        finally:
            from order_execution import close_broker_client

            await close_broker_client(broker_client)
            broker_client = None

    open_positions = await db_obj.get_positions("open")
    partial_positions = await db_obj.get_positions("partial")
    candidate_positions = open_positions + partial_positions
    if parsed.get('_card'):
        position_id = parsed['_card'].get('position_id')
        candidate_positions = [position for position in candidate_positions if position.get('id') == position_id]
    protected_positions = [] if coerce_bool(
        settings_raw.get("core_runner_enabled"), default=False
    ) else [
        position
        for position in candidate_positions
        if _contextual_exit_is_trailing_protected(
            position,
            parsed,
            settings_raw,
            source_config or {},
        )
    ]
    if protected_positions:
        protected_ids = {str(position.get("id") or "") for position in protected_positions}
        candidate_positions = [
            position for position in candidate_positions if str(position.get("id") or "") not in protected_ids
        ]
        parsed["_exit_skip_reason"] = (
            "contextual exit ignored for trailing-protected position: "
            + ", ".join(sorted(position_id for position_id in protected_ids if position_id))
        )
        logger.info("[process_exit_alert] %s", parsed["_exit_skip_reason"])
    if broker_positions_failed and _has_active_broker_option_positions(candidate_positions, settings_raw):
        logger.warning("[process_exit_alert] blocked sell alert because broker positions could not be verified")
        return False
    source_config = source_config or {}
    exit_trigger = str(parsed.get("exit_trigger") or "sell_alert").strip() or "sell_alert"
    any_submitted = False

    try:
        exit_plans = build_exit_plans(
            candidate_positions,
            parsed,
            include_simulated=True,
            allow_missing_exit_price=True,
        )
    except ValueError as exc:
        logger.warning("[process_exit_alert] blocked exit alert: %s", exc)
        return False

    if not exit_plans:
        logger.info("[process_exit_alert] no matching open position for %s", parsed)
        return False

    for plan in exit_plans:
        plan = _cap_analyst_exit_plan(plan, parsed, settings_raw)
        plan_updates = plan.get("position_updates") or {}
        if plan_updates:
            plan["position"].update(plan_updates)
            await db_obj.update_position(
                str(plan["position"].get("id") or ""),
                {"$set": plan_updates},
            )
        if int(plan.get("quantity") or 0) <= 0:
            parsed["_exit_skip_reason"] = str(
                plan.get("skip_reason") or "analyst exit held to preserve runner contracts"
            )
            logger.info("[process_exit_alert] %s", parsed["_exit_skip_reason"])
            continue
        if bool(plan["position"].get("exit_order_pending")):
            superseded = await _supersede_pending_exit_order(
                db_obj,
                plan["position"],
                requested_quantity=int(plan.get("quantity") or 0),
                requested_percentage=float(plan.get("percentage") or 100.0),
                settings_raw=settings_raw,
            )
            if not superseded:
                logger.warning(
                    "[process_exit_alert] position %s still has an active broker exit order",
                    plan["position"].get("id"),
                )
                continue
            refreshed_position = await db_obj.get_position_by_id(plan["position"].get("id"))
            refreshed_plans = build_exit_plans(
                [refreshed_position] if refreshed_position else [],
                parsed,
                include_simulated=True,
                allow_missing_exit_price=True,
            )
            if not refreshed_plans:
                continue
            plan = _cap_analyst_exit_plan(refreshed_plans[0], parsed, settings_raw)
            if int(plan.get("quantity") or 0) <= 0:
                continue
        position = Position(**plan["position"])
        sell_qty = plan["quantity"]
        exit_price = plan["exit_price"]

        trade = Trade(
            alert_id=alert.id,
            position_id=position.id,
            ticker=position.ticker,
            strike=position.strike,
            option_type=position.option_type,
            expiration=position.expiration,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=sell_qty,
            side="SELL",
            broker=settings.active_broker.value,
            simulated=False,
            realized_pnl=0.0,
            sell_percentage=plan.get("percentage"),
            exit_trigger=exit_trigger,
            exit_reason="Discord sell alert",
            exit_allocation_target=plan.get("exit_allocation_target"),
            target_remaining_quantity=plan.get("target_remaining_quantity"),
            exit_runner_audit=plan.get("runner_audit") or {},
        )

        order_client = None
        reservation = {
            "exit_order_pending": True,
            "exit_order_id": None,
            "exit_reservation_token": str(uuid.uuid4()),
            "exit_reservation_trigger": exit_trigger,
            "exit_reservation_created_at": datetime.now(timezone.utc).isoformat(),
            "exit_target_remaining_quantity": plan.get("target_remaining_quantity"),
            "exit_target_trigger": exit_trigger,
            "exit_target_allocation_target": plan.get("exit_allocation_target"),
            "exit_target_updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            from order_execution import get_configured_broker_client

            await db_obj.update_position(position.id, {"$set": reservation})
            order_client = get_configured_broker_client(
                settings_raw,
                settings.active_broker.value,
                require_order_status=True,
            )
            exit_price = await _resolve_alert_exit_price(
                order_client,
                plan["position"],
                exit_price,
            )
            trade.exit_price = exit_price
            order_result = await order_client.place_order(
                ticker=position.ticker,
                strike=position.strike,
                option_type=position.option_type,
                expiration=position.expiration,
                side="SELL",
                quantity=sell_qty,
                price=exit_price,
                client_order_id=build_client_order_id(alert.id, "SELL", position.id),
            )
            order_id = order_result.get("order_id")
            if not order_id:
                raise ValueError(order_result.get("error", "Broker did not return an order id"))

            trade.order_id = order_id
            trade.status = "pending"
            await db_obj.insert_trade(trade.model_dump())
            await db_obj.update_position(position.id, {"$set": {"exit_order_id": order_id}})
            asyncio.create_task(
                monitor_fill(
                    order_context=OrderContext(
                        trade_id=trade.id,
                        order_id=order_id,
                        side="SELL",
                        ticker=position.ticker,
                        strike=position.strike,
                        option_type=position.option_type,
                        expiration=position.expiration,
                        requested_quantity=sell_qty,
                        broker=settings.active_broker.value,
                        position_id=position.id,
                        alert_id=alert.id,
                        alert_price=exit_price,
                        simulated=False,
                        sell_percentage=plan.get("percentage"),
                        exit_trigger=exit_trigger,
                        exit_allocation_target=plan.get("exit_allocation_target"),
                        target_remaining_quantity=plan.get("target_remaining_quantity"),
                    ),
                    broker_client=order_client,
                    db=db_obj,
                    settings=settings_raw,
                    close_broker_client_when_done=True,
                )
            )
            order_client = None
            any_submitted = True
        except Exception as exc:
            await db_obj.update_position(
                position.id,
                {
                    "$set": {
                        "exit_order_pending": False,
                        "exit_order_id": None,
                        "exit_reservation_token": None,
                    }
                },
            )
            if order_client is not None:
                from order_execution import close_broker_client

                await close_broker_client(order_client)
            trade.status = "failed"
            trade.error_message = str(exc)
            await db_obj.insert_trade(trade.model_dump())
            logger.error("[process_exit_alert] sell order failed: %s", exc)
            await notify_trade_failed(
                trade.id,
                trade.ticker,
                trade.strike,
                trade.option_type,
                str(exc),
                settings_raw,
            )

    return any_submitted


def _cap_analyst_exit_plan(
    plan: dict,
    parsed: dict,
    settings_raw: dict,
) -> dict:
    position = plan.get("position") if isinstance(plan.get("position"), dict) else {}
    remaining = int(position.get("remaining_quantity") or position.get("quantity") or 0)
    requested = min(remaining, max(0, int(plan.get("quantity") or 0)))
    if not coerce_bool(settings_raw.get("core_runner_enabled"), default=False):
        return {
            **plan,
            "exit_allocation_target": "entire_position",
            "target_remaining_quantity": max(0, remaining - requested),
            "runner_audit": {
                "requested_quantity": requested,
                "protected_quantity": 0,
                "permitted_quantity": requested,
                "target_remaining_quantity": max(0, remaining - requested),
            },
        }

    from core_runner_policy import cap_exit_quantity, update_runner_state

    bid = float(
        position.get("option_bid")
        or position.get("current_price")
        or position.get("entry_price")
        or 0.0
    )
    state = update_runner_state(position, settings_raw, bid=bid)
    inferred_position_id = str(parsed.get("inferred_from_position_id") or "").strip()
    explicit_contract = not inferred_position_id and all(
        (
            str(parsed.get("ticker") or "").strip(),
            parsed.get("strike") is not None,
            str(parsed.get("option_type") or "").strip(),
        )
    )
    sell_percentage = float(parsed.get("sell_percentage") or plan.get("percentage") or 100.0)
    override_threshold = max(
        1.0,
        min(100.0, float(settings_raw.get("core_runner_analyst_override_percent") or 80.0)),
    )
    explicit_override = (
        explicit_contract
        and sell_percentage >= override_threshold
        and coerce_bool(settings_raw.get("core_runner_explicit_full_exit_overrides"), default=True)
    )
    contextual_full_override = (
        not explicit_contract
        and sell_percentage >= 100.0
        and coerce_bool(settings_raw.get("core_runner_contextual_full_exit_overrides"), default=False)
    )
    trigger = str(parsed.get("exit_trigger") or "trim_alert").strip() or "trim_alert"
    decision = {
        "triggered": requested > 0,
        "action": "triggered",
        "exit_trigger": trigger,
        "quantity": requested,
        "position_updates": state.updates,
    }
    if explicit_override or contextual_full_override:
        decision["exit_allocation_target"] = "entire_position"
    capped = cap_exit_quantity(decision, state, settings_raw)
    permitted = int(capped.get("quantity") or 0) if capped.get("triggered") else 0
    raw_target = capped.get("target_remaining_quantity")
    target = remaining if raw_target is None else int(raw_target)
    protected = max(0, requested - permitted)
    return {
        **plan,
        "quantity": permitted,
        "exit_allocation_target": capped.get("exit_allocation_target") or "core_only",
        "target_remaining_quantity": target,
        "position_updates": capped.get("position_updates") or {},
        "skip_reason": capped.get("reason") if not capped.get("triggered") else None,
        "runner_audit": {
            "requested_quantity": requested,
            "protected_quantity": protected,
            "permitted_quantity": permitted,
            "target_remaining_quantity": target,
            "explicit_override": explicit_override,
            "contextual_full_override": contextual_full_override,
        },
    }


def _contextual_exit_is_trailing_protected(
    position: dict,
    parsed: dict,
    settings_raw: dict,
    source_config: dict,
) -> bool:
    if not coerce_bool(
        source_config.get("protect_trailing_armed_from_contextual_exits"),
        default=True,
    ):
        return False

    explicit_contract_core = (
        not str(parsed.get("inferred_from_position_id") or "").strip()
        and bool(str(parsed.get("ticker") or "").strip())
        and parsed.get("strike") is not None
        and bool(str(parsed.get("option_type") or "").strip())
    )
    try:
        sell_percentage = float(parsed.get("sell_percentage") or 0.0)
        override_percentage = float(
            source_config.get("trailing_context_exit_override_percent", 80.0) or 80.0
        )
    except (TypeError, ValueError):
        sell_percentage = 0.0
        override_percentage = 80.0
    if (
        explicit_contract_core
        and coerce_bool(
            source_config.get("trailing_context_exit_override_enabled"),
            default=True,
        )
        and sell_percentage >= max(1.0, min(100.0, override_percentage))
    ):
        return False

    inferred_position_id = str(parsed.get("inferred_from_position_id") or "").strip()
    position_id = str(position.get("id") or "").strip()
    if inferred_position_id:
        contextual = not position_id or inferred_position_id == position_id
    else:
        contextual = not all(
            (
                str(parsed.get("ticker") or "").strip(),
                parsed.get("strike") is not None,
                str(parsed.get("option_type") or "").strip(),
                str(parsed.get("expiration") or "").strip(),
            )
        )
    if not contextual:
        return False

    from options_exit_policy import is_trailing_protection_eligible

    return is_trailing_protection_eligible(position, settings_raw)


async def _supersede_pending_exit_order(
    db_obj,
    position: dict,
    *,
    requested_quantity: int,
    requested_percentage: float,
    settings_raw: dict,
) -> bool:
    """Cancel a smaller resting exit and reconcile its final broker state before replacement."""
    position_id = str(position.get("id") or "").strip()
    order_id = str(position.get("exit_order_id") or "").strip()
    if not position_id or not order_id:
        return False

    trades = await db_obj.get_trades(limit=500)
    pending_statuses = {"pending", "partial", "unconfirmed", "pending_broker", "submitted"}
    pending_trade = next(
        (
            trade
            for trade in trades or []
            if str(trade.get("position_id") or "").strip() == position_id
            and str(trade.get("order_id") or "").strip() == order_id
            and str(trade.get("side") or "").upper() == "SELL"
            and str(trade.get("status") or "").lower() in pending_statuses
        ),
        None,
    )
    if not pending_trade:
        return False

    pending_quantity = max(1, int(pending_trade.get("quantity") or 1))
    if requested_percentage < 100.0 and requested_quantity <= pending_quantity:
        return False

    from order_execution import close_broker_client, get_configured_broker_client

    broker_name = str(settings_raw.get("active_broker") or position.get("broker") or "").lower()
    client = get_configured_broker_client(settings_raw, broker_name, require_order_status=True)
    context = _pending_trade_order_context(pending_trade)
    if context is None:
        await close_broker_client(client)
        return False

    try:
        cancel_result = await client.cancel_order(order_id)
        logger.info(
            "[process_exit_alert] superseding exit %s for %s: %s",
            order_id,
            position_id,
            cancel_result,
        )
        for _ in range(8):
            status_data = await client.get_order_status(order_id)
            status = str(status_data.get("status") or "unknown").lower()
            filled_qty = max(0, int(status_data.get("filled_qty") or 0))
            fill_price = float(status_data.get("avg_fill_price") or 0.0)
            if status == "filled":
                await reconcile_order_update(
                    db_obj,
                    context,
                    BrokerOrderUpdate(status="filled", filled_qty=filled_qty, avg_fill_price=fill_price),
                    settings=settings_raw,
                )
                return True
            if status in {"cancelled", "canceled", "expired", "rejected"}:
                await reconcile_order_update(
                    db_obj,
                    context,
                    BrokerOrderUpdate(
                        status="cancelled",
                        filled_qty=filled_qty,
                        avg_fill_price=fill_price,
                        reason="superseded by newer analyst exit",
                    ),
                    settings=settings_raw,
                )
                return True
            await asyncio.sleep(0.25)
    except Exception as exc:
        logger.warning("[process_exit_alert] unable to supersede exit %s: %s", order_id, exc)
    finally:
        await close_broker_client(client)
    return False


def _has_active_broker_option_positions(positions: list[dict], settings: dict) -> bool:
    active_broker = str(settings.get("active_broker") or "").strip().lower()
    for position in positions or []:
        if not isinstance(position, dict):
            continue
        broker = str(position.get("broker") or "").strip().lower()
        if active_broker and broker and broker != active_broker:
            continue
        option_type = str(position.get("option_type") or "").strip().upper()
        try:
            strike = float(position.get("strike") or 0.0)
        except (TypeError, ValueError):
            strike = 0.0
        if (
            str(position.get("ticker") or "").strip()
            and strike > 0
            and option_type in {"CALL", "PUT"}
            and str(position.get("expiration") or "").strip()
        ):
            return True
    return False


def _default_schedule_fill_monitor(**kwargs):
    asyncio.create_task(monitor_fill(**kwargs))


def _pending_trade_order_context(trade: dict) -> OrderContext | None:
    order_id = str(trade.get("order_id") or "").strip()
    trade_id = str(trade.get("id") or "").strip()
    if not trade_id or not order_id:
        return None
    return OrderContext(
        trade_id=trade_id,
        order_id=order_id,
        side=str(trade.get("side") or "BUY").upper(),
        ticker=str(trade.get("ticker") or ""),
        strike=float(trade.get("strike") or 0.0),
        option_type=str(trade.get("option_type") or ""),
        expiration=str(trade.get("expiration") or ""),
        requested_quantity=max(1, int(trade.get("quantity") or 1)),
        broker=str(trade.get("broker") or ""),
        position_id=trade.get("position_id"),
        alert_id=trade.get("alert_id"),
        alert_price=float(trade.get("entry_price") or trade.get("exit_price") or 0.0) or None,
        simulated=bool(trade.get("simulated")),
        sell_percentage=trade.get("sell_percentage"),
        exit_trigger=trade.get("exit_trigger"),
        exit_allocation_target=trade.get("exit_allocation_target"),
        target_remaining_quantity=trade.get("target_remaining_quantity"),
        entry_risk_profile=str(trade.get("entry_risk_profile") or "normal"),
        max_loss_budget=trade.get("max_loss_budget"),
        estimated_stop_loss_percent=trade.get("estimated_stop_loss_percent"),
        source_reported_stop_price=trade.get("source_reported_stop_price"),
        source_reported_stop_percent=trade.get("source_reported_stop_percent"),
        source_reported_break_even_stop=bool(trade.get("source_reported_break_even_stop")),
        update_alert_status=trade_owns_alert_status(trade),
    )


async def resume_pending_fill_monitors(
    db,
    settings: dict[str, Any],
    *,
    broker_client=None,
    schedule_monitor=None,
    limit: int = 500,
) -> int:
    """Restart broker fill polling for persisted pending orders after process restart."""
    schedule_monitor = schedule_monitor or _default_schedule_fill_monitor
    trades = await db.get_trades(limit=limit)
    pending_trades = [
        trade for trade in trades
        if str(trade.get("status") or "").lower() in {"pending", "partial", "unconfirmed", "pending_broker"}
        and trade.get("order_id")
    ]
    if not pending_trades:
        return 0

    if broker_client is None:
        from order_execution import get_configured_broker_client

        active_broker = str(settings.get("active_broker") or "").lower()
        broker_client = get_configured_broker_client(
            settings,
            active_broker,
            require_order_status=True,
        )

    scheduled = 0
    for trade in pending_trades:
        order_context = _pending_trade_order_context(trade)
        if order_context is None:
            continue
        result = schedule_monitor(
            order_context=order_context,
            broker_client=broker_client,
            db=db,
            settings=settings,
        )
        if asyncio.iscoroutine(result):
            await result
        scheduled += 1
    if scheduled:
        logger.info("Rescheduled %s pending broker fill monitor(s) after startup.", scheduled)
    return scheduled


def run_discord_bot(token: str, channel_ids: List[str]):
    """Run the Discord bot in a separate thread"""
    global discord_bot, discord_bot_thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _record_discord_runtime_config(token, channel_ids)
    discord_bot = create_discord_bot(token, channel_ids)
    if discord_bot_thread is None or not discord_bot_thread.is_alive():
        discord_bot_thread = threading.current_thread()
    set_discord_bot(discord_bot, discord_bot_thread, token=token, channel_ids=channel_ids, loop=loop)
    try:
        loop.run_until_complete(discord_bot.start(token))
    finally:
        update_bot_status('discord_connected', False)
        loop.close()


def _normalize_channel_ids(channel_ids: List[str] | str) -> List[str]:
    if isinstance(channel_ids, str):
        raw_ids = channel_ids.split(',')
    else:
        raw_ids = channel_ids
    return [str(channel_id).strip() for channel_id in raw_ids if str(channel_id).strip()]


async def _wait_for_discord_bot_ready(thread: threading.Thread, timeout_seconds: float = 5.0) -> bool:
    """Wait briefly for the Discord worker thread to create and publish the bot object."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        if discord_bot is not None:
            set_discord_bot(discord_bot, thread)
            return True
        if not thread.is_alive():
            return discord_bot is not None
        await asyncio.sleep(0.01)
    return False


async def init_discord_bot(token: str, channel_ids: List[str] | str):
    """Start the Discord bot in the background without blocking API startup."""
    global discord_bot_thread
    channels = _normalize_channel_ids(channel_ids)
    if not token or not channels:
        logger.warning("Discord bot not configured - set token and channel ids")
        _record_discord_runtime_config(token, channels)
        return None

    if discord_bot_thread and discord_bot_thread.is_alive():
        logger.info("Discord bot already running")
        _record_discord_runtime_config(token, channels)
        return discord_bot_thread

    _record_discord_runtime_config(token, channels)
    discord_bot_thread = threading.Thread(
        target=run_discord_bot,
        args=(token, channels),
        daemon=True,
        name="SentinelEcho",
    )
    discord_bot_thread.start()
    if not await _wait_for_discord_bot_ready(discord_bot_thread):
        logger.warning("Discord bot thread started but bot object was not initialized before timeout.")
    return discord_bot_thread


async def shutdown_bot():
    """Stop the Discord bot if it is running."""
    global discord_bot, discord_bot_thread
    if discord_bot:
        await discord_bot.close()
        update_bot_status('discord_connected', False)
    discord_bot = None
    discord_bot_thread = None
    set_discord_bot(None, None)


# FastAPI App
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database abstraction layer
    if USE_SQLITE:
        db = init_database(sqlite_path=SQLITE_PATH)
        logger.info(f"Using SQLite database: {SQLITE_PATH}")
    else:
        db = init_database(mongo_db=mongo_db)
        logger.info(f"Using MongoDB database: {DB_NAME}")
    
    # Initialize routes with database abstraction
    init_routes(db)

    settings = await db.get_settings()
    try:
        await resume_pending_fill_monitors(db, settings)
    except Exception as exc:
        logger.error("Failed to resume pending fill monitors on startup: %s", exc)

    bot_managed_exit_task = None
    try:
        from bot_managed_exits import reconcile_broker_positions, start_bot_managed_exit_worker
        from order_execution import get_configured_broker_client

        active_broker = str(settings.get("active_broker") or "").lower()
        broker_client = get_configured_broker_client(
            settings,
            active_broker,
            require_order_status=True,
        )
        await reconcile_broker_positions(db, broker_client, settings)
        bot_managed_exit_task = await start_bot_managed_exit_worker(
            db,
            settings,
            broker_client=broker_client,
        )
    except Exception as exc:
        logger.error("Failed to initialize bot-managed exits on startup: %s", exc)

    discord_config = resolve_saved_or_runtime_discord_config(settings, os.environ)
    if discord_config.token and discord_config.channel_ids:
        logger.info(
            "Discord runtime config source=%s channel_count=%s",
            discord_config.source,
            len(discord_config.channel_ids),
        )
        await init_discord_bot(discord_config.token, discord_config.channel_ids)
    elif discord_config.warnings:
        logger.info(
            "Discord runtime config unavailable: %s",
            "; ".join(discord_config.warnings),
        )
    
    yield
    
    # Cleanup
    if bot_managed_exit_task:
        bot_managed_exit_task.cancel()
        try:
            await bot_managed_exit_task
        except asyncio.CancelledError:
            pass
    await shutdown_bot()
    if mongo_client:
        mongo_client.close()


app = FastAPI(title="Trading Bot API", lifespan=lifespan)

# Authentication middleware.
# Set API_KEY env var to a secret string. All requests must include:
#   X-API-Key: <your-secret>
# /api/health is exempt so uptime monitors work without a key.
# If API_KEY is not set, auth is disabled only for explicit localhost desktop mode.
_LOCAL_BIND_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _is_production_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"prod", "production", "live"}


def validate_api_auth_startup(
    *,
    api_key: str,
    use_sqlite: bool,
    bind_host: str,
    app_env: str | None,
) -> dict[str, bool]:
    normalized_key = str(api_key or "").strip()
    normalized_host = str(bind_host or "").strip().lower()
    authless_desktop_mode = (
        not normalized_key
        and use_sqlite
        and normalized_host in _LOCAL_BIND_HOSTS
        and not _is_production_env(app_env)
    )
    if not normalized_key and _is_production_env(app_env):
        raise RuntimeError("API_KEY is required when ENV/APP_ENV/ENVIRONMENT is production.")
    return {"authless_desktop_mode": authless_desktop_mode}


_API_KEY = os.environ.get("API_KEY", "").strip()
_BIND_HOST = os.environ.get("HOST", "127.0.0.1").strip().lower()
_APP_ENV = (
    os.environ.get("ENV")
    or os.environ.get("APP_ENV")
    or os.environ.get("ENVIRONMENT")
    or ""
)
_AUTH_CONFIG = validate_api_auth_startup(
    api_key=_API_KEY,
    use_sqlite=USE_SQLITE,
    bind_host=_BIND_HOST,
    app_env=_APP_ENV,
)
_AUTHLESS_DESKTOP_MODE = _AUTH_CONFIG["authless_desktop_mode"]
if not _API_KEY:
    if _AUTHLESS_DESKTOP_MODE:
        logger.warning(
            "API_KEY environment variable is not set - authentication is disabled "
            "for local desktop mode only because HOST=%s and USE_SQLITE=true.",
            _BIND_HOST,
        )
    else:
        logger.error(
            "API_KEY environment variable is not set and HOST=%s is not an authless "
            "desktop bind. Non-health API requests will be rejected.",
            _BIND_HOST,
        )

_PUBLIC_PATHS = {"/api/health", "/api/pairing/status"}  # paths that never require a key

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Always allow CORS preflight through
        if request.method == "OPTIONS":
            return await call_next(request)
        # Skip auth on public paths.
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)
        # Allow keyless operation only for explicit local desktop mode.
        if not _API_KEY and _AUTHLESS_DESKTOP_MODE:
            return await call_next(request)
        if not _API_KEY:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": (
                        "API_KEY is required unless HOST is 127.0.0.1/localhost "
                        "with USE_SQLITE=true desktop mode."
                    )
                },
            )
        provided = request.headers.get("X-API-Key", "")
        if provided != _API_KEY:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key. Set X-API-Key header."},
            )
        return await call_next(request)

# FIXED C9: restrict CORS - set ALLOWED_ORIGINS env var (comma-separated)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3003,http://127.0.0.1:3003,"
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)
# Auth middleware runs after CORS so preflight responses aren't blocked
app.add_middleware(APIKeyMiddleware)

# Create main API router and include all sub-routers
api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(brokers_router)
api_router.include_router(settings_router)
api_router.include_router(discord_router)
api_router.include_router(profiles_router)
api_router.include_router(trading_router)
api_router.include_router(operator_router)
api_router.include_router(analytics_router)
api_router.include_router(bot_bus_router)
api_router.include_router(pairing_router)

app.include_router(api_router)


def find_packaged_static_dir() -> Path | None:
    """Return the exported frontend directory bundled by the Windows installer."""
    # PyInstaller exposes bundled files through sys._MEIPASS at runtime.
    candidates = [
        Path.cwd() / "static",
        Path(__file__).resolve().parent / "static",
        Path(getattr(sys, "_MEIPASS", "")) / "static",
    ]
    if getattr(sys, "frozen", False):
        candidates.extend([
            Path(sys.executable).resolve().parent / "static",
            Path(sys.executable).resolve().parent / "_internal" / "static",
        ])

    for candidate in candidates:
        if candidate and (candidate / "index.html").exists():
            return candidate
    return None


packaged_static_dir = find_packaged_static_dir()
if packaged_static_dir:
    app.mount("/app", StaticFiles(directory=str(packaged_static_dir), html=True), name="app")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=8001)
