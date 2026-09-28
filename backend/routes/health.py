"""
Health and status endpoints
FIXED C2b, C20, M28, M29
"""
from fastapi import APIRouter
import os
import threading
from datetime import datetime, timezone
from broker_capabilities import (
    broker_config_has_saved_value,
    get_broker_capabilities,
    is_broker_configured,
    missing_broker_config_fields,
    normalize_broker_id,
)
from live_readiness import evaluate_live_readiness
from order_execution import close_broker_client
from readiness_status import readiness_ready_for_live, status_flag
from settings_flags import coerce_bool
from source_config import summarize_source_policy

router = APIRouter(tags=["Health"])
db = None

_status_lock = threading.Lock()  # FIXED C20: thread-safe bot_status

bot_status = {
    "discord_connected": False,
    "discord_token_configured": False,
    "discord_channel_count": 0,
    "broker_connected": False,
    "active_broker": "ibkr",
    "auto_trading_enabled": True,
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
    if key not in _VALID_STATUS_KEYS:
        return
    with _status_lock:
        bot_status[key] = value


def _readiness_status_snapshot() -> dict:
    from bridge_health import evaluate_bridge_health

    status = get_bot_status()
    status["chrome_bridge_healthy"] = status_flag(evaluate_bridge_health(), "healthy")
    return status


@router.get("/health")
async def health():
    """FIXED M28: real health check"""
    status = _readiness_status_snapshot()
    discord_ok = status_flag(status, "discord_connected")
    if db:
        settings = await db.get_settings() or {}
        runtime = await db.get_runtime_state() if hasattr(db, "get_runtime_state") else {}
        readiness = evaluate_live_readiness(settings, runtime, status=status)
        signal_ingestion = readiness.get("checks", {}).get("signal_ingestion", {})
        discord_ok = status_flag(signal_ingestion, "discord_connected")
        broker_ok = await resolve_broker_connected(settings, status)
    else:
        broker_ok = status_flag(status, "broker_connected")
    return {
        "status": "healthy" if (discord_ok and broker_ok) else "degraded",
        "discord_connected": discord_ok,
        "broker_connected": broker_ok
    }


async def resolve_broker_connected(settings: dict, status: dict, *, client_factory=None) -> bool:
    """Return broker connectivity from status, falling back to a direct configured-client check."""
    settings = _dict_or_empty(settings)
    active_broker = normalize_broker_id(settings.get("active_broker"), default="")
    broker_configs = _dict_or_empty(settings.get("broker_configs"))
    if not active_broker or not is_broker_configured(broker_configs, active_broker):
        return False
    if status_flag(status, "broker_connected"):
        return True
    if client_factory is None:
        from order_execution import get_configured_broker_client

        client_factory = get_configured_broker_client
    try:
        client = client_factory(settings, active_broker)
        connected = await client.check_connection()
        return bool(connected)
    except Exception:
        return False
    finally:
        if "client" in locals():
            await close_broker_client(client)


@router.get("/status")
async def get_status():
    """Get current bot status, with trading flags derived from persisted settings."""
    status = _readiness_status_snapshot()
    if db:
        settings = _dict_or_empty(await db.get_settings())
        runtime = {}
        has_runtime_state = hasattr(db, "get_runtime_state")
        if has_runtime_state:
            runtime = _dict_or_empty(await db.get_runtime_state())
        active_broker = normalize_broker_id(
            settings.get("active_broker", status.get("active_broker", "ibkr")),
            default="ibkr",
        )
        broker_connected = await resolve_broker_connected(settings, status)
        update_bot_status("broker_connected", broker_connected)
        readiness_status = {**status, "broker_connected": broker_connected}
        readiness = evaluate_live_readiness(settings, runtime, status=readiness_status)
        signal_ingestion = readiness.get("checks", {}).get("signal_ingestion", {})
        status.update(
            {
                "discord_connected": status_flag(signal_ingestion, "discord_connected"),
                "broker_connected": broker_connected,
                "active_broker": active_broker,
                "auto_trading_enabled": coerce_bool(settings.get("auto_trading_enabled"), default=True),
                "simulation_mode": coerce_bool(settings.get("simulation_mode"), default=True),
            }
        )
        status.update(await _persistent_alert_status(db, status))
        if has_runtime_state:
            status["shutdown_triggered"] = coerce_bool(runtime.get("shutdown_triggered"), default=False)
            status["shutdown_reason"] = runtime.get("shutdown_reason", "")
    return status


@router.get("/diagnostics/setup")
async def setup_diagnostics():
    """Report setup readiness without exposing tokens or broker secrets."""
    settings = _dict_or_empty(await db.get_settings() if db else {})
    runtime = _dict_or_empty(await db.get_runtime_state() if db and hasattr(db, "get_runtime_state") else {})
    status = _readiness_status_snapshot()

    discord_token_configured = _discord_token_configured(settings, status)
    channel_ids = settings.get("discord_channel_ids") or []

    active_broker = normalize_broker_id(settings.get("active_broker"), default="ibkr")
    broker_configs = _dict_or_empty(settings.get("broker_configs"))
    active_broker_config = broker_configs.get(active_broker)
    broker_configured = is_broker_configured(broker_configs, active_broker)
    missing_broker_fields = []
    if not broker_configured and broker_config_has_saved_value(active_broker_config):
        missing_broker_fields = list(missing_broker_config_fields(active_broker_config, active_broker))
    broker_connected = broker_configured and status_flag(status, "broker_connected")
    broker_capabilities = get_broker_capabilities(active_broker)
    order_status_supported = broker_configured and bool(
        broker_capabilities.get("supports_order_status", False)
    )

    source_policy = summarize_source_policy(settings.get("source_overrides"))
    source_config_valid = bool(source_policy.get("valid", False))
    source_error = str(source_policy.get("error") or "")

    auto_trading_enabled = coerce_bool(settings.get("auto_trading_enabled"), default=True)
    simulation_mode = coerce_bool(settings.get("simulation_mode"), default=True)
    shutdown_triggered = (
        coerce_bool(runtime.get("shutdown_triggered"), default=False)
        or coerce_bool(settings.get("shutdown_triggered"), default=False)
    )
    auto_live_sources = int(source_policy.get("auto_live_sources", 0))
    readiness = evaluate_live_readiness(settings, runtime, status=status)

    warnings = _setup_warnings(
        discord_token_configured=discord_token_configured,
        source_count=int(source_policy.get("override_count", 0)),
        auto_live_sources=auto_live_sources,
        source_config_valid=source_config_valid,
        source_error=source_error,
        broker_configured=broker_configured,
        missing_broker_fields=missing_broker_fields,
        order_status_supported=order_status_supported,
        auto_trading_enabled=auto_trading_enabled,
        simulation_mode=simulation_mode,
        shutdown_triggered=shutdown_triggered,
    )
    warnings = _merge_readiness_warnings(warnings, readiness)
    ready_for_live = readiness_ready_for_live(readiness)
    signal_ingestion = readiness.get("checks", {}).get("signal_ingestion", {})

    return {
        "ready_for_live": ready_for_live,
        "discord": {
            "token_configured": discord_token_configured,
            "connected": status_flag(signal_ingestion, "discord_connected"),
            "channel_count": int(signal_ingestion.get("discord_channel_count", len(channel_ids))),
            "message_content_intent_requested": True,
            "message_content_portal_check_required": True,
        },
        "source_policy": source_policy,
        "broker": {
            "active_broker": active_broker,
            "configured": broker_configured,
            "missing_required_fields": missing_broker_fields,
            "connected": broker_connected,
            "order_status_supported": order_status_supported,
            "capabilities": broker_capabilities,
        },
        "trading": {
            "auto_trading_enabled": auto_trading_enabled,
            "simulation_mode": simulation_mode,
            "shutdown_triggered": shutdown_triggered,
            "live_trading_armed": coerce_bool(runtime.get("live_trading_armed"), default=False),
            "live_trading_armed_until": runtime.get("live_trading_armed_until", ""),
        },
        "readiness": readiness,
        "warnings": warnings,
    }


def _discord_token_configured(settings: dict, status: dict) -> bool:
    return (
        bool(str(settings.get("discord_token") or "").strip())
        or bool(os.environ.get("DISCORD_BOT_TOKEN", "").strip())
        or status_flag(status, "discord_token_configured")
    )


def _dict_or_empty(value) -> dict:
    return value if isinstance(value, dict) else {}


async def _persistent_alert_status(database, status: dict) -> dict:
    if not hasattr(database, "get_alerts"):
        return {}
    try:
        alerts = await database.get_alerts(limit=1000)
    except Exception:
        return {}
    if not isinstance(alerts, list) or not alerts:
        return {}

    newest_value = None
    newest_sort_key = None
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        raw_timestamp = alert.get("received_at") or alert.get("created_at") or alert.get("timestamp")
        sort_key = _timestamp_sort_key(raw_timestamp)
        if sort_key is None:
            continue
        if newest_sort_key is None or sort_key > newest_sort_key:
            newest_sort_key = sort_key
            newest_value = raw_timestamp.isoformat() if isinstance(raw_timestamp, datetime) else str(raw_timestamp)

    current_count = _safe_int(status.get("alerts_processed"))
    return {
        "alerts_processed": max(current_count, len([alert for alert in alerts if isinstance(alert, dict)])),
        "last_alert_time": newest_value or status.get("last_alert_time"),
    }


def _timestamp_sort_key(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _safe_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _setup_warnings(
    *,
    discord_token_configured: bool,
    source_count: int,
    auto_live_sources: int,
    source_config_valid: bool,
    source_error: str,
    broker_configured: bool,
    missing_broker_fields: list[str],
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
    if missing_broker_fields:
        warnings.append(f"Active broker config is missing required fields: {', '.join(missing_broker_fields)}.")
    elif not broker_configured:
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
    readiness = readiness if isinstance(readiness, dict) else {}
    for issue in readiness.get("blocking_issues", []) or []:
        if not isinstance(issue, dict):
            continue
        summary = str(issue.get("summary") or "").strip()
        if summary and summary not in seen:
            merged.append(summary)
            seen.add(summary)
    return merged
