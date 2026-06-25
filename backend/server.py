"""
Trading Bot Backend - Refactored with Modular Routes and Database Abstraction
Main FastAPI server supporting both MongoDB (server) and SQLite (desktop)
"""
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from contextlib import asynccontextmanager
import os
import logging
import threading
from datetime import datetime, timezone
from typing import List
import discord
from discord.ext import commands
import asyncio

# Import models
from models import Alert, Settings
from order_execution import build_client_order_id
from paper_shadow import (
    build_entry_shadow_records,
    build_exit_shadow_records,
    is_paper_shadow_position,
)

# Import utilities
from discord_ingestion import DiscordIngestionDeps, handle_discord_message

# Import new professional features
from risk import is_duplicate_alert, calculate_position_size, check_correlation
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

# Import routes
from routes import (
    health_router, brokers_router, settings_router, 
    discord_router, profiles_router, trading_router,
    edge_sr_router,
    analytics_router,
    init_routes, update_bot_status, set_discord_bot
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'tradebot')
SQLITE_PATH = os.environ.get('DATABASE_PATH', 'tradebot.db')

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


def _load_settings_sync() -> dict:
    """Load settings from the sync path used by the Discord bot thread."""
    if USE_SQLITE:
        from database_sqlite import get_settings
        return get_settings()

    settings_doc = sync_mongo_db.settings.find_one({'id': 'main_settings'})
    return settings_doc if settings_doc else {}


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
                is_duplicate_alert=is_duplicate_alert,
                increment_alerts_processed=increment_alerts_processed,
            ),
            bot_user=bot.user,
        )
        if result.skip_reason and result.skip_reason not in {"unparsed", "self message", "channel not monitored"}:
            logger.info("[on_message] skipped alert: %s", result.skip_reason)
        
        await bot.process_commands(message)
    
    return bot


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

    if parsed['alert_type'] == 'buy':
        source_config = parsed.get("_source_config") or {}

        # ── 1. Risk-based position sizing ─────────────────────────────────────
        quantity = calculate_position_size(
            entry_price=alert.entry_price,
            default_quantity=settings.default_quantity,
            max_position_size=settings.max_position_size,
            risk_multiplier=source_config.get("risk_multiplier", 1.0),
        )
        quantity = apply_source_quantity_limits(quantity, source_config)

        # ── 2. Correlation / concentration check ─────────────────────────────
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
            logger.warning(f"[process_trade] correlation check failed ({e}) — proceeding")
            allowed, block_reason = True, ""

        if not allowed:
            logger.warning(f"[process_trade] trade BLOCKED: {block_reason}")
            await notify_correlation_block(
                ticker=alert.ticker,
                open_count=int(block_reason.split()[2]) if block_reason else 0,
                max_count=int(settings_raw.get("max_positions_per_ticker", 3)),
                settings=settings_raw,
            )
            # Update alert as processed but not executed
            if USE_SQLITE:
                from database_sqlite import update_alert
                update_alert(alert.id, {'processed': True, 'trade_executed': False})
            else:
                sync_mongo_db.alerts.update_one(
                    {'id': alert.id},
                    {'$set': {'processed': True, 'trade_executed': False}}
                )
            return

        # ── 3. Build the trade record ─────────────────────────────────────────
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
            if USE_SQLITE:
                from database_sqlite import insert_trade, insert_position
                insert_trade(shadow_trade.model_dump(mode="json"))
                insert_position(shadow_position.model_dump(mode="json"))
            else:
                sync_mongo_db.trades.insert_one(shadow_trade.model_dump())
                sync_mongo_db.positions.insert_one(shadow_position.model_dump())

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
            if USE_SQLITE:
                from database_sqlite import insert_trade, insert_position
                insert_trade(trade.model_dump())
                insert_position(position.model_dump())
            else:
                sync_mongo_db.trades.insert_one(trade.model_dump())
                sync_mongo_db.positions.insert_one(position.model_dump())

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
                buffer_pct = settings.premium_buffer_amount / 100  # Convert cents to decimal
                limit_price = round(alert.entry_price * (1 - buffer_pct), 2)
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
                trade_executed = True
            except Exception as e:
                trade.status = "failed"
                trade.error_message = str(e)
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

            # ── 4. Fill confirmation monitor ───────────────────────────────
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

    # ── Update alert status ───────────────────────────────────────────────────
    if USE_SQLITE:
        from database_sqlite import update_alert
        update_alert(alert.id, {'processed': True, 'trade_executed': trade_executed})
    else:
        sync_mongo_db.alerts.update_one(
            {'id': alert.id},
            {'$set': {'processed': True, 'trade_executed': trade_executed}}
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
    from routes.settings import check_and_trigger_shutdown

    db_obj = get_db()
    open_positions = await db_obj.get_positions("open")
    partial_positions = await db_obj.get_positions("partial")
    candidate_positions = open_positions + partial_positions
    source_config = source_config or {}
    any_submitted = False

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
                await db_obj.insert_trade(shadow_trade.model_dump(mode="json"))
                await db_obj.update_position(shadow_position.id, shadow_update)
                any_submitted = True

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
        return any_submitted

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

    return any_submitted


def run_discord_bot(token: str, channel_ids: List[str]):
    """Run the Discord bot in a separate thread"""
    global discord_bot, discord_bot_thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
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


async def init_discord_bot(token: str, channel_ids: List[str] | str):
    """Start the Discord bot in the background without blocking API startup."""
    global discord_bot_thread
    channels = _normalize_channel_ids(channel_ids)
    if not token or not channels:
        logger.warning("Discord bot not configured - set token and channel ids")
        return None

    if discord_bot_thread and discord_bot_thread.is_alive():
        logger.info("Discord bot already running")
        return discord_bot_thread

    discord_bot_thread = threading.Thread(
        target=run_discord_bot,
        args=(token, channels),
        daemon=True,
        name="ConsolidationDiscordBot",
    )
    discord_bot_thread.start()
    set_discord_bot(discord_bot, discord_bot_thread)
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

    token = os.environ.get('DISCORD_BOT_TOKEN', '').strip()
    channel_ids = os.environ.get('DISCORD_CHANNEL_IDS', '').strip()
    if token and channel_ids:
        await init_discord_bot(token, channel_ids)
    
    yield
    
    # Cleanup
    await shutdown_bot()
    if mongo_client:
        mongo_client.close()


app = FastAPI(title="Trading Bot API", lifespan=lifespan)

# ── Authentication middleware (C2 fix) ──────────────────────────────────────
# Set API_KEY env var to a secret string. All requests must include:
#   X-API-Key: <your-secret>
# /api/health is exempt so uptime monitors work without a key.
# If API_KEY is not set, auth is disabled (dev mode) with a warning.
_API_KEY = os.environ.get("API_KEY", "").strip()
if not _API_KEY:
    logger.warning(
        "API_KEY environment variable is not set — authentication is DISABLED. "
        "Set API_KEY to a strong random secret before exposing this server."
    )

_PUBLIC_PATHS = {"/api/health"}  # paths that never require a key

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Always allow CORS preflight through
        if request.method == "OPTIONS":
            return await call_next(request)
        # Skip auth on public paths or when no key is configured (dev mode)
        if not _API_KEY or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)
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
api_router.include_router(edge_sr_router)
api_router.include_router(analytics_router)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
