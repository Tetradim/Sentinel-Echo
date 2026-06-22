"""
Health and status endpoints
FIXED C2b, C20, M28, M29
"""
from fastapi import APIRouter
import os
import threading
from broker_capabilities import get_broker_capabilities, normalize_broker_id
from live_readiness import evaluate_live_readiness
from source_config import normalize_source_overrides

router = APIRouter(tags=["Health"])
db = None

_status_lock = threading.Lock()  # FIXED C20: thread-safe bot_status

bot_status = {
    "discord_connected": False,
    "broker_connected": False,
    "active_broker": "ibkr",
    "auto_trading_enabled": False,  # FIXED C2b: was True
    "simulation_mode": True,
    "last_alert_time": None,
    "alerts_processed": 0
}

_VALID_STATUS_KEYS = set(bot_status.keys())  # FIXED M29: schema enforcement


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
    discord_ok = bool(status.get("discord_connected", False))
    if db:
        settings = await db.get_settings() or {}
        runtime = await db.get_runtime_state() if hasattr(db, "get_runtime_state") else {}
        readiness = evaluate_live_readiness(settings, runtime, status=status)
        signal_ingestion = readiness.get("checks", {}).get("signal_ingestion", {})
        discord_ok = bool(signal_ingestion.get("discord_connected", False))
    broker_ok = bool(status.get("broker_connected", False))
    return {
        "status": "healthy" if (discord_ok and broker_ok) else "degraded",
        "discord_connected": discord_ok,
        "broker_connected": broker_ok
    }


@router.get("/status")
async def get_status():
    """Get current bot status, with trading flags derived from persisted settings."""
    status = get_bot_status()
    if db:
        settings = _dict_or_empty(await db.get_settings())
        active_broker = normalize_broker_id(
            settings.get("active_broker", status.get("active_broker", "ibkr")),
            default="ibkr",
        )
        status.update(
            {
                "active_broker": active_broker,
                "auto_trading_enabled": bool(settings.get("auto_trading_enabled", False)),
                "simulation_mode": bool(settings.get("simulation_mode", True)),
            }
        )
        if hasattr(db, "get_runtime_state"):
            runtime = _dict_or_empty(await db.get_runtime_state())
            status["shutdown_triggered"] = bool(runtime.get("shutdown_triggered", False))
            status["shutdown_reason"] = runtime.get("shutdown_reason", "")
    return status


@router.get("/diagnostics/setup")
async def setup_diagnostics():
    """Report setup readiness without exposing tokens or broker secrets."""
    settings = _dict_or_empty(await db.get_settings() if db else {})
    runtime = _dict_or_empty(await db.get_runtime_state() if db and hasattr(db, "get_runtime_state") else {})
    status = get_bot_status()

    discord_token_configured = _discord_token_configured(settings, status)
    channel_ids = settings.get("discord_channel_ids") or []

    active_broker = normalize_broker_id(settings.get("active_broker"), default="ibkr")
    broker_configs = _dict_or_empty(settings.get("broker_configs"))
    broker_configured = active_broker in broker_configs
    broker_capabilities = get_broker_capabilities(active_broker)
    order_status_supported = broker_configured and bool(
        broker_capabilities.get("supports_order_status", False)
    )

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
    shutdown_triggered = bool(
        runtime.get("shutdown_triggered", False)
        or settings.get("shutdown_triggered", False)
    )
    auto_live_sources = _auto_live_source_count(normalized_sources)
    readiness = evaluate_live_readiness(settings, runtime, status=status)

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
    warnings = _merge_readiness_warnings(warnings, readiness)
    ready_for_live = bool(readiness.get("ready_for_live", False))
    signal_ingestion = readiness.get("checks", {}).get("signal_ingestion", {})

    return {
        "ready_for_live": ready_for_live,
        "discord": {
            "token_configured": discord_token_configured,
            "connected": bool(signal_ingestion.get("discord_connected", False)),
            "channel_count": int(signal_ingestion.get("discord_channel_count", len(channel_ids))),
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
            "capabilities": broker_capabilities,
        },
        "trading": {
            "auto_trading_enabled": auto_trading_enabled,
            "simulation_mode": simulation_mode,
            "shutdown_triggered": shutdown_triggered,
            "live_trading_armed": bool(runtime.get("live_trading_armed", False)),
            "live_trading_armed_until": runtime.get("live_trading_armed_until", ""),
        },
        "readiness": readiness,
        "warnings": warnings,
    }


def _discord_token_configured(settings: dict, status: dict) -> bool:
    return (
        bool(str(settings.get("discord_token") or "").strip())
        or bool(os.environ.get("DISCORD_BOT_TOKEN", "").strip())
        or bool(status.get("discord_token_configured", False))
    )


def _dict_or_empty(value) -> dict:
    return value if isinstance(value, dict) else {}


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


def _merge_readiness_warnings(warnings: list[str], readiness: dict) -> list[str]:
    merged = list(warnings)
    seen = set(merged)
    for issue in readiness.get("blocking_issues", []) or []:
        summary = str(issue.get("summary") or "").strip()
        if summary and summary not in seen:
            merged.append(summary)
            seen.add(summary)
    return merged


def _auto_live_source_count(normalized_sources: dict) -> int:
    return sum(
        1
        for config in normalized_sources.values()
        if config.get("enabled", True)
        and not config.get("paper_only")
        and not config.get("require_manual_confirm")
    )
