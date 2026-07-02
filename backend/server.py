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

# Import models
from models import Alert, Settings
from order_execution import build_client_order_id, build_oco_exit_plan
from paper_shadow import (
    build_entry_shadow_records,
    build_exit_shadow_records,
    is_paper_shadow_position,
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
from notifications import (
    notify_trade_filled, notify_trade_failed,
    notify_auto_shutdown, notify_discord_disconnected,
    notify_correlation_block,
)
from fill_monitor import monitor_fill
from fill_reconciliation import OrderContext
from trade_lifecycle import build_exit_plans, is_exit_alert

# Import database abstraction
from database import init_database, get_db, USE_SQLITE, MongoDBDatabase
from database_paths import configured_database_path

# Import routes
from routes import (
    health_router, brokers_router, settings_router, 
    discord_router, profiles_router, trading_router,
    operator_router, analytics_router, sentinel_archive_router,
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


def _active_broker_is_paper(settings: Settings, settings_raw: dict[str, Any]) -> bool:
    active_broker = str(_plain_value(settings.active_broker) or "").strip().lower()
    broker_configs = settings_raw.get("broker_configs") if isinstance(settings_raw, dict) else {}
    if not isinstance(broker_configs, dict):
        broker_configs = {}
    config = _mapping_from_model(broker_configs.get(active_broker))

    truthy_paper_fields = ("paper_trading", "paper", "paper_mode", "is_paper", "sandbox")
    if any(str(config.get(field) or "").strip().lower() in {"1", "true", "yes", "on"} for field in truthy_paper_fields):
        return True

    mode = str(config.get("mode") or config.get("trading_mode") or "").strip().lower()
    if mode in {"paper", "paper_trading", "sandbox"}:
        return True

    base_url = str(config.get("base_url") or config.get("url") or "").strip().lower()
    if active_broker == "alpaca" and "paper-api.alpaca.markets" in base_url:
        return True
    return False


def _requires_live_arming(settings: Settings, settings_raw: dict[str, Any]) -> bool:
    return not settings.simulation_mode and not _active_broker_is_paper(settings, settings_raw)


async def process_trade(alert: Alert, parsed: dict):
    """Process a trade based on parsed alert — with risk sizing, correlation check, fill monitoring."""
    from models import Trade, Position
    
    # Get settings
    if USE_SQLITE:
        from database_sqlite import get_settings
        settings_dict = get_settings()
    else:
        settings_doc = sync_mongo_db.settings.find_one({'id': 'main_settings'})
        settings_dict = settings_doc if settings_doc else {}
    
    settings = Settings(**settings_dict) if settings_dict else Settings()
    settings_raw = settings_dict or {}
    if parsed.get("_force_simulation"):
        settings.simulation_mode = True
        settings_raw = dict(settings_raw)
        settings_raw["simulation_mode"] = True
    trade_executed = False
    trade_result = None

    if parsed['alert_type'] == 'buy':
        source_config = parsed.get("_source_config") or {}

        # 1. Risk-based position sizing.
        quantity = calculate_position_size(
            entry_price=alert.entry_price,
            default_quantity=settings.default_quantity,
            max_position_size=settings.max_position_size,
            risk_multiplier=source_config.get("risk_multiplier", 1.0),
        )
        quantity = apply_source_quantity_limits(quantity, source_config)
        if quantity <= 0:
            logger.warning(
                "[process_trade] trade BLOCKED: one contract for %s exceeds max_position_size",
                alert.ticker,
            )
            await update_alert_status(
                alert.id,
                {
                    'processed': True,
                    'trade_executed': False,
                    'trade_result': 'blocked: position size limit',
                },
            )
            return

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
            logger.error(f"[process_trade] blocking trade because correlation check failed: {e}")
            allowed, block_reason = False, "Risk controls unavailable"

        if not allowed:
            logger.warning(f"[process_trade] trade BLOCKED: {block_reason}")
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
            # Update alert as processed but not executed
            await update_alert_status(
                alert.id,
                {
                    'processed': True,
                    'trade_executed': False,
                    'trade_result': f'blocked: {block_reason}',
                },
            )
            return

        if _requires_live_arming(settings, settings_raw):
            try:
                from live_arming import is_live_trading_armed
                from live_readiness import live_execution_role_enabled

                runtime_state = await get_db().get_runtime_state()
                if not is_live_trading_armed(runtime_state):
                    logger.warning("[process_trade] live BUY blocked because live trading is not armed")
                    await update_alert_status(
                        alert.id,
                        {
                            'processed': True,
                            'trade_executed': False,
                            'trade_result': 'blocked: live trading not armed',
                        },
                    )
                    return
                if not live_execution_role_enabled():
                    logger.warning("[process_trade] live BUY blocked because Sentinel Echo is not in live_executioner role")
                    await update_alert_status(
                        alert.id,
                        {
                            'processed': True,
                            'trade_executed': False,
                            'trade_result': 'blocked: live executioner role disabled',
                        },
                    )
                    return
            except Exception as exc:
                logger.error("[process_trade] live BUY blocked while checking arming state: %s", exc)
                await update_alert_status(
                    alert.id,
                    {
                        'processed': True,
                        'trade_executed': False,
                        'trade_result': f'blocked: live arming check failed: {exc}',
                    },
                )
                return

        # 3. Build the trade record.
        trade = Trade(
            alert_id=alert.id,
            ticker=alert.ticker,
            strike=alert.strike,
            option_type=alert.option_type,
            expiration=alert.expiration,
            entry_price=alert.entry_price,
            quantity=quantity,
            broker=settings.active_broker.value,
            simulated=settings.simulation_mode
        )

        if source_config.get("paper_shadow") and not settings.simulation_mode:
            shadow_trade, shadow_position = build_entry_shadow_records(
                alert=alert,
                quantity=quantity,
                broker=settings.active_broker.value,
            )
            shadow_position_data = shadow_position.model_dump(mode="json")
            shadow_oco_exit_plan = build_oco_exit_plan(
                settings_raw,
                alert_id=alert.id,
                position_id=shadow_position.id,
                entry_price=alert.entry_price,
                quantity=quantity,
            )
            if shadow_oco_exit_plan:
                shadow_position_data["oco_exit_plan"] = shadow_oco_exit_plan
                shadow_position_data["oco_exit_protected"] = True
            if USE_SQLITE:
                from database_sqlite import insert_trade, insert_position
                insert_trade(shadow_trade.model_dump(mode="json"))
                insert_position(shadow_position_data)
            else:
                sync_mongo_db.trades.insert_one(shadow_trade.model_dump())
                sync_mongo_db.positions.insert_one(shadow_position_data)

        if settings.simulation_mode:
            # Simulated — no broker call, no fill monitoring needed
            trade.status = "simulated"
            trade.executed_at = datetime.now(timezone.utc)
            logger.info(
                f"SIMULATED BUY: {trade.quantity}x {trade.ticker} "
                f"${trade.strike} {trade.option_type} @ ${trade.entry_price:.2f}"
            )
            position = Position(
                ticker=alert.ticker,
                strike=alert.strike,
                option_type=alert.option_type,
                expiration=alert.expiration,
                entry_price=alert.entry_price,
                original_quantity=quantity,
                remaining_quantity=quantity,
                total_cost=alert.entry_price * quantity * 100,
                broker=settings.active_broker.value,
                simulated=True,
                trade_ids=[trade.id],
                highest_price=alert.entry_price
            )
            position_data = position.model_dump()
            oco_exit_plan = build_oco_exit_plan(
                settings_raw,
                alert_id=alert.id,
                position_id=position.id,
                entry_price=alert.entry_price,
                quantity=quantity,
            )
            if oco_exit_plan:
                position_data["oco_exit_plan"] = oco_exit_plan
                position_data["oco_exit_protected"] = True
            if USE_SQLITE:
                from database_sqlite import insert_trade, insert_position
                insert_trade(trade.model_dump())
                insert_position(position_data)
            else:
                sync_mongo_db.trades.insert_one(trade.model_dump())
                sync_mongo_db.positions.insert_one(position_data)

            await notify_trade_filled(
                trade.id, trade.ticker, trade.strike, trade.option_type,
                quantity, trade.entry_price, "BUY (SIM)", settings_raw,
            )
            trade_executed = True

        else:
            # Real order — place with broker, store as "pending", start fill monitor
            trade.status = "pending"
            order_id = None
            
            # Apply price buffer for safety (default 3% below entry)
            limit_price = alert.entry_price
            buffer_applied = 0.0
            if settings.premium_buffer_enabled:
                buffer_dollars = max(0.0, settings.premium_buffer_amount) / 100
                limit_price = max(0.01, round(alert.entry_price - buffer_dollars, 2))
                buffer_applied = alert.entry_price - limit_price
                logger.info(f"[process_trade] applying buffer: ${buffer_applied:.2f} (limit: ${limit_price})")
            
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
                    price=limit_price,  # Use buffered price
                    client_order_id=build_client_order_id(alert.id, "BUY"),
                )
                order_id = order_result.get("order_id")
                if not order_id:
                    raise ValueError(order_result.get("error", "Broker did not return an order id"))
                trade.order_id = order_id
                logger.info(
                    f"[process_trade] placed order {order_id} for "
                    f"{quantity}x {alert.ticker} ${alert.strike} {alert.option_type}"
                )
            except Exception as e:
                trade.status = "failed"
                trade.error_message = str(e)
                trade_result = f"failed: {trade.error_message}"
                logger.error(f"[process_trade] order placement failed: {e}")
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
                            alert_price=limit_price,
                            simulated=False,
                        ),
                        broker_client=broker_client,
                        db=db_obj,
                        settings=settings_raw,
                    ))
                except Exception as e:
                    logger.error(f"[process_trade] failed to start fill monitor: {e}")
    elif parsed["alert_type"] == "average_down":
        trade_executed = await process_average_down_alert(
            alert,
            parsed,
            settings,
            settings_raw,
            source_config=parsed.get("_source_config") or {},
        )
    elif is_exit_alert(parsed):
        trade_executed = await process_exit_alert(
            alert,
            parsed,
            settings,
            settings_raw,
            source_config=parsed.get("_source_config") or {},
        )
    else:
        logger.info("[process_trade] unsupported alert_type=%s", parsed.get("alert_type"))

    # Update alert status.
    updates = {'processed': True, 'trade_executed': trade_executed}
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
    """Process average-down alerts by adding to a matching open option position."""
    from models import Trade

    if not settings.averaging_down_enabled:
        logger.info("[process_average_down_alert] averaging down is disabled")
        return False

    db_obj = get_db()
    open_positions = await db_obj.get_positions("open")
    partial_positions = await db_obj.get_positions("partial")
    candidates = [
        position
        for position in open_positions + partial_positions
        if _average_down_position_matches(position, parsed)
        and (settings.simulation_mode or not _position_is_simulated(position))
    ]
    if not candidates:
        logger.info("[process_average_down_alert] no matching open position for %s", parsed)
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
        simulated=settings.simulation_mode,
    )

    if settings.simulation_mode:
        trade.status = "simulated"
        trade.executed_at = datetime.now(timezone.utc)
        await db_obj.insert_trade(trade.model_dump())
        await db_obj.update_position(
            position["id"],
            _average_down_position_update(
                position,
                trade_id=trade.id,
                quantity=quantity,
                entry_price=alert_price,
                settings_raw=settings_raw,
                alert_id=alert.id,
            ),
        )
        await notify_trade_filled(
            trade.id,
            trade.ticker,
            trade.strike,
            trade.option_type,
            quantity,
            alert_price,
            "AVG DOWN (SIM)",
            settings_raw,
        )
        return True

    if _requires_live_arming(settings, settings_raw):
        try:
            from live_arming import is_live_trading_armed
            from live_readiness import live_execution_role_enabled

            runtime_state = await db_obj.get_runtime_state()
            if not is_live_trading_armed(runtime_state):
                logger.warning("[process_average_down_alert] live BUY blocked because live trading is not armed")
                return False
            if not live_execution_role_enabled():
                logger.warning("[process_average_down_alert] live BUY blocked because Sentinel Echo is not in live_executioner role")
                return False
        except Exception as exc:
            logger.error("[process_average_down_alert] live BUY blocked while checking arming state: %s", exc)
            return False

    limit_price = alert_price
    if settings.premium_buffer_enabled:
        buffer_dollars = max(0.0, settings.premium_buffer_amount) / 100
        limit_price = max(0.01, round(alert_price - buffer_dollars, 2))

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
                    alert_price=limit_price,
                    simulated=False,
                ),
                broker_client=broker_client,
                db=db_obj,
                settings=settings_raw,
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


def _position_is_simulated(position: dict[str, Any]) -> bool:
    broker = str(position.get("broker") or "").lower()
    return bool(position.get("simulated")) or broker.endswith(":paper_shadow")


def _date_key(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "/")


async def process_exit_alert(
    alert: Alert,
    parsed: dict,
    settings: Settings,
    settings_raw: dict,
    source_config: dict | None = None,
) -> bool:
    """Process sell/trim/close alerts against matching open positions."""
    from models import Trade, Position
    from routes.settings import check_and_trigger_shutdown

    db_obj = get_db()
    open_positions = await db_obj.get_positions("open")
    partial_positions = await db_obj.get_positions("partial")
    candidate_positions = open_positions + partial_positions
    source_config = source_config or {}
    exit_trigger = str(parsed.get("exit_trigger") or "sell_alert").strip() or "sell_alert"
    any_submitted = False
    any_executed = False

    try:
        if source_config.get("paper_shadow") and not settings.simulation_mode:
            shadow_exit_plans = build_exit_plans(
                [
                    position
                    for position in candidate_positions
                    if is_paper_shadow_position(position)
                ],
                parsed,
                include_simulated=True,
            )
            for shadow_plan in shadow_exit_plans:
                shadow_position = Position(**shadow_plan["position"])
                shadow_trade, shadow_update = build_exit_shadow_records(
                    alert=alert,
                    position=shadow_position,
                    quantity=shadow_plan["quantity"],
                    exit_price=shadow_plan["exit_price"],
                )
                shadow_trade.sell_percentage = shadow_plan.get("percentage")
                shadow_trade.exit_trigger = exit_trigger
                shadow_trade.exit_reason = "Discord sell alert"
                await db_obj.insert_trade(shadow_trade.model_dump(mode="json"))
                await db_obj.update_position(shadow_position.id, shadow_update)
                any_submitted = True
                any_executed = True

        exit_plans = build_exit_plans(
            candidate_positions,
            parsed,
            include_simulated=settings.simulation_mode,
        )
    except ValueError as exc:
        logger.warning("[process_exit_alert] blocked exit alert: %s", exc)
        return False

    if not exit_plans:
        if any_submitted:
            logger.info("[process_exit_alert] recorded paper-shadow exit for %s", parsed)
        else:
            logger.info("[process_exit_alert] no matching open position for %s", parsed)
        return any_executed

    for plan in exit_plans:
        position = Position(**plan["position"])
        sell_qty = plan["quantity"]
        exit_price = plan["exit_price"]
        realized_pnl = (exit_price - position.entry_price) * sell_qty * 100

        trade = Trade(
            alert_id=alert.id,
            ticker=position.ticker,
            strike=position.strike,
            option_type=position.option_type,
            expiration=position.expiration,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=sell_qty,
            side="SELL",
            broker=settings.active_broker.value,
            simulated=settings.simulation_mode,
            realized_pnl=realized_pnl,
            sell_percentage=plan.get("percentage"),
            exit_trigger=exit_trigger,
            exit_reason="Discord sell alert",
        )

        if settings.simulation_mode:
            trade.status = "simulated"
            trade.executed_at = datetime.now(timezone.utc)
            await db_obj.insert_trade(trade.model_dump())

            new_remaining = max(0, position.remaining_quantity - sell_qty)
            update_data = {
                "$set": {
                    "remaining_quantity": new_remaining,
                    "realized_pnl": position.realized_pnl + realized_pnl,
                    "current_price": exit_price,
                    "status": "closed" if new_remaining <= 0 else "partial",
                },
                "$push": {"trade_ids": trade.id},
            }
            if new_remaining <= 0:
                update_data["$set"]["closed_at"] = datetime.now(timezone.utc).isoformat()

            await db_obj.update_position(position.id, update_data)
            await check_and_trigger_shutdown(realized_pnl)
            await notify_trade_filled(
                trade.id,
                trade.ticker,
                trade.strike,
                trade.option_type,
                sell_qty,
                exit_price,
                "SELL (SIM)",
                settings_raw,
            )
            any_submitted = True
            any_executed = True
            continue

        if _requires_live_arming(settings, settings_raw):
            try:
                from live_arming import is_live_trading_armed
                from live_readiness import live_execution_role_enabled

                runtime_state = await db_obj.get_runtime_state()
                if not is_live_trading_armed(runtime_state):
                    logger.warning("[process_exit_alert] live SELL blocked because live trading is not armed")
                    continue
                if not live_execution_role_enabled():
                    logger.warning("[process_exit_alert] live SELL blocked because Sentinel Echo is not in live_executioner role")
                    continue
            except Exception as exc:
                logger.error("[process_exit_alert] live SELL blocked while checking arming state: %s", exc)
                continue

        try:
            from order_execution import get_configured_broker_client

            broker_client = get_configured_broker_client(
                settings_raw,
                settings.active_broker.value,
                require_order_status=True,
            )
            order_result = await broker_client.place_order(
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
                    ),
                    broker_client=broker_client,
                    db=db_obj,
                    settings=settings_raw,
                )
            )
            any_submitted = True
        except Exception as exc:
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

    return any_executed


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
        if str(trade.get("status") or "").lower() == "pending" and trade.get("order_id")
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
    set_discord_bot(discord_bot, discord_bot_thread)
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
api_router.include_router(sentinel_archive_router)
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
