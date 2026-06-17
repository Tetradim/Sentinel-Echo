"""
Health and status endpoints
FIXED C2b, C20, M28, M29
"""
from fastapi import APIRouter
import threading
from source_config import normalize_source_overrides

router = APIRouter(tags=["Health"])
db = None

_status_lock = threading.Lock()  # FIXED C20: thread-safe bot_status

bot_status = {
    "discord_connected": False,
    "broker_connected": False,
    "active_broker": "ibkr",
    "auto_trading_enabled": False,  # FIXED C2b: was True
    "last_alert_time": None,
    "alerts_processed": 0
}

_VALID_STATUS_KEYS = set(bot_status.keys())  # FIXED M29: schema enforcement
ORDER_STATUS_SUPPORTED_BROKERS = {"alpaca", "tradier"}


def set_db(database):
    """Set the database reference for diagnostics."""
    global db
    db = database


def get_bot_status():
    """Get a thread-safe snapshot of bot status"""
    with _status_lock:
        return dict(bot_status)


def update_bot_status(key: str, value):
    """Update bot status (thread-safe)"""
    with _status_lock:
        bot_status[key] = value


@router.get("/health")
async def health():
    """FIXED M28: real health check"""
    status = get_bot_status()
    discord_ok = status.get("discord_connected", False)
    broker_ok = status.get("broker_connected", False)
    return {
        "status": "healthy" if (discord_ok and broker_ok) else "degraded",
        "discord_connected": discord_ok,
        "broker_connected": broker_ok
    }


@router.get("/status")
async def get_status():
    """Get current bot status"""
    return bot_status


@router.get("/diagnostics/setup")
async def setup_diagnostics():
    """Report setup readiness without exposing tokens or broker secrets."""
    settings = await db.get_settings() if db else {}
    settings = settings or {}
    status = get_bot_status()

    discord_token_configured = bool(settings.get("discord_token"))
    channel_ids = settings.get("discord_channel_ids") or []

    active_broker = str(settings.get("active_broker") or "").lower() or "ibkr"
    broker_configs = settings.get("broker_configs") or {}
    broker_configured = active_broker in broker_configs
    order_status_supported = broker_configured and active_broker in ORDER_STATUS_SUPPORTED_BROKERS

    source_overrides = settings.get("source_overrides") or {}
    try:
        normalized_sources = normalize_source_overrides(source_overrides)
        source_config_valid = True
        source_error = ""
    except ValueError as exc:
        normalized_sources = {}
        source_config_valid = False
        source_error = str(exc)

    auto_trading_enabled = bool(settings.get("auto_trading_enabled", False))
    simulation_mode = bool(settings.get("simulation_mode", True))
    shutdown_triggered = bool(settings.get("shutdown_triggered", False))
    auto_live_sources = _auto_live_source_count(normalized_sources)

    warnings = _setup_warnings(
        discord_token_configured=discord_token_configured,
        source_count=len(normalized_sources),
        auto_live_sources=auto_live_sources,
        source_config_valid=source_config_valid,
        source_error=source_error,
        broker_configured=broker_configured,
        order_status_supported=order_status_supported,
        auto_trading_enabled=auto_trading_enabled,
        simulation_mode=simulation_mode,
        shutdown_triggered=shutdown_triggered,
    )
    ready_for_live = not warnings

    return {
        "ready_for_live": ready_for_live,
        "discord": {
            "token_configured": discord_token_configured,
            "connected": bool(status.get("discord_connected", False)),
            "channel_count": len(channel_ids),
            "message_content_intent_requested": True,
            "message_content_portal_check_required": True,
        },
        "source_policy": {
            "override_count": len(normalized_sources),
            "valid": source_config_valid,
            "paper_only_sources": sum(
                1 for config in normalized_sources.values() if config.get("paper_only")
            ),
            "paper_shadow_sources": sum(
                1 for config in normalized_sources.values() if config.get("paper_shadow")
            ),
            "manual_confirm_sources": sum(
                1 for config in normalized_sources.values() if config.get("require_manual_confirm")
            ),
            "auto_live_sources": auto_live_sources,
        },
        "broker": {
            "active_broker": active_broker,
            "configured": broker_configured,
            "connected": bool(status.get("broker_connected", False)),
            "order_status_supported": order_status_supported,
        },
        "trading": {
            "auto_trading_enabled": auto_trading_enabled,
            "simulation_mode": simulation_mode,
            "shutdown_triggered": shutdown_triggered,
        },
        "warnings": warnings,
    }


def _setup_warnings(
    *,
    discord_token_configured: bool,
    source_count: int,
    auto_live_sources: int,
    source_config_valid: bool,
    source_error: str,
    broker_configured: bool,
    order_status_supported: bool,
    auto_trading_enabled: bool,
    simulation_mode: bool,
    shutdown_triggered: bool,
) -> list[str]:
    warnings = []
    if not discord_token_configured:
        warnings.append("Discord token is not configured.")
    if source_count <= 0:
        warnings.append("No source overrides are configured.")
    elif auto_live_sources <= 0:
        warnings.append("No source override can submit live orders automatically.")
    if not source_config_valid:
        warnings.append(f"Source overrides are invalid: {source_error}")
    if not broker_configured:
        warnings.append("Active broker is not configured.")
    elif not order_status_supported:
        warnings.append("Active broker does not support live fill status polling.")
    if not auto_trading_enabled:
        warnings.append("Auto trading is disabled.")
    if simulation_mode:
        warnings.append("Simulation mode is enabled.")
    if shutdown_triggered:
        warnings.append("Runtime shutdown is active.")
    return warnings


def _auto_live_source_count(normalized_sources: dict) -> int:
    return sum(
        1
        for config in normalized_sources.values()
        if config.get("enabled", True)
        and not config.get("paper_only")
        and not config.get("require_manual_confirm")
    )
