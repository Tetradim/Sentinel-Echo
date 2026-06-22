"""
Settings and risk management endpoints
"""
from fastapi import APIRouter, Body, HTTPException, Header
from models import (
    Settings, SettingsUpdate,
    AveragingDownSettingsUpdate, RiskManagementSettingsUpdate,
    TrailingStopSettingsUpdate, AutoShutdownSettingsUpdate
)
from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, Optional
from operator_audit import record_operator_event
from source_config import normalize_source_overrides
# C4: credential encryption at rest
from utils.credentials import (
    SENSITIVE_FIELDS,
    decrypt_broker_configs,
    encrypt_broker_configs,
    is_masked_secret,
    mask_broker_configs,
)

router = APIRouter(tags=["Settings"])
logger = logging.getLogger(__name__)

# Database instance - will be set by main server
db = None


def set_db(database):
    """Set the database reference"""
    global db
    db = database


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _settings_response(settings: Dict[str, Any] | None) -> Dict[str, Any]:
    """Return settings safe for API clients: no plaintext broker credentials."""
    if not isinstance(settings, dict) or not settings:
        settings = Settings().model_dump()
    response = dict(settings)
    if response.get("broker_configs"):
        decrypted = decrypt_broker_configs(response["broker_configs"])
        response["broker_configs"] = mask_broker_configs(decrypted)
    return response


def _merge_broker_configs(
    existing_configs: Dict[str, Dict[str, Any]],
    incoming_configs: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Merge partial broker updates while preserving masked existing secrets."""
    merged_configs = dict(existing_configs)
    for broker_id, config in incoming_configs.items():
        clean_config = {
            key: value
            for key, value in (config or {}).items()
            if key != "configured_fields"
        }
        merged = dict(existing_configs.get(broker_id, {}))
        for key, value in clean_config.items():
            if key in SENSITIVE_FIELDS and is_masked_secret(value):
                continue
            merged[key] = value
        merged_configs[broker_id] = merged
    return merged_configs


@router.get("/settings")
async def get_settings():
    """Get all settings with broker credentials masked for client safety."""
    settings = await db.get_settings()
    return _settings_response(settings)


@router.put("/settings")
async def update_settings(update: SettingsUpdate):
    """Update settings -- broker_configs encrypted before persistence."""
    update_dict = {k: v for k, v in update.model_dump().items() if v is not None}
    # C4: broker screens save one config at a time, so merge before encryption.
    if 'broker_configs' in update_dict:
        existing_settings = _dict_or_empty(await db.get_settings())
        existing_configs = decrypt_broker_configs(existing_settings.get('broker_configs', {}))
        merged_configs = _merge_broker_configs(existing_configs, update_dict['broker_configs'])
        update_dict['broker_configs'] = encrypt_broker_configs(merged_configs)
    settings = await db.update_settings(update_dict)
    await record_operator_event(
        db,
        "settings",
        "settings_updated",
        "Settings updated.",
        details={"fields": sorted(update_dict.keys()), "updates": update_dict},
    )
    return _settings_response(settings)


@router.get("/source-overrides")
async def get_source_overrides():
    """Get per-channel/per-analyst source overrides."""
    settings = _dict_or_empty(await db.get_settings())
    try:
        return normalize_source_overrides(settings.get("source_overrides", {}))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Stored source overrides are invalid: {exc}")


@router.put("/source-overrides")
async def update_source_overrides(source_overrides: Dict[str, Dict[str, Any]] = Body(...)):
    """Replace per-source overrides used by Discord alert intake."""
    try:
        normalized = normalize_source_overrides(source_overrides)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.update_settings({"source_overrides": normalized})
    return normalized


@router.get("/correlation-settings")
async def get_correlation_settings():
    """Get per-ticker position concentration limit."""
    settings = await db.get_settings()
    return {
        "max_positions_per_ticker": settings.get("max_positions_per_ticker", 3),
    }


@router.put("/correlation-settings")
async def update_correlation_settings(max_positions_per_ticker: int):
    """Set the maximum number of open positions allowed in one underlying."""
    if max_positions_per_ticker < 0:
        raise HTTPException(status_code=400, detail="Value must be >= 0")
    await db.update_settings({"max_positions_per_ticker": max_positions_per_ticker})
    return {"max_positions_per_ticker": max_positions_per_ticker}


# Trading Toggles
@router.post("/toggle-trading")
async def toggle_trading():
    """Toggle auto trading on/off"""
    # Persisted settings are the source of truth for Discord ingestion.
    from routes.health import update_bot_status
    settings = await db.get_settings()
    if not isinstance(settings, dict):
        blocked_readiness = {
            "ready_for_live": False,
            "blocking_issues": [
                {
                    "code": "settings_malformed",
                    "summary": "Persisted settings are malformed.",
                }
            ],
            "blocking_codes": ["settings_malformed"],
        }
        await record_operator_event(
            db,
            "live_safety",
            "auto_trading_enable_blocked",
            "Auto trading enable was blocked because settings are malformed.",
            severity="warning",
            details={"blocking_issues": blocked_readiness["blocking_issues"]},
        )
        raise HTTPException(status_code=409, detail=blocked_readiness)
    current = bool((settings or {}).get("auto_trading_enabled", False))
    new_state = not current
    if new_state and not bool((settings or {}).get("simulation_mode", True)):
        from live_readiness import evaluate_live_readiness
        from routes.health import get_bot_status

        candidate_settings = dict(settings or {})
        candidate_settings["auto_trading_enabled"] = True
        runtime = await db.get_runtime_state() if hasattr(db, "get_runtime_state") else {}
        readiness = _dict_or_empty(evaluate_live_readiness(candidate_settings, runtime, status=get_bot_status()))
        if not readiness.get("ready_for_live", False):
            await record_operator_event(
                db,
                "live_safety",
                "auto_trading_enable_blocked",
                "Auto trading enable was blocked by live readiness checks.",
                severity="warning",
                details={"blocking_issues": _list_or_empty(readiness.get("blocking_issues"))},
            )
            raise HTTPException(status_code=409, detail=readiness)
    await db.update_settings({"auto_trading_enabled": new_state})
    if hasattr(db, "update_runtime_state"):
        await db.update_runtime_state({"auto_trading_enabled": new_state})
    update_bot_status("auto_trading_enabled", new_state)
    await record_operator_event(
        db,
        "live_safety",
        "auto_trading_toggled",
        f"Auto trading {'enabled' if new_state else 'disabled'}.",
        severity="warning" if new_state else "info",
        details={"auto_trading_enabled": new_state},
    )
    return {"auto_trading_enabled": new_state}


# Premium Buffer
@router.post("/toggle-premium-buffer")
async def toggle_premium_buffer():
    """Toggle premium buffer"""
    settings = await db.get_settings()
    new_state = not settings.get('premium_buffer_enabled', False)
    await db.update_settings({'premium_buffer_enabled': new_state})
    return {"premium_buffer_enabled": new_state}


@router.get("/premium-buffer-settings")
async def get_premium_buffer_settings():
    """Get premium buffer settings"""
    settings = await db.get_settings()
    return {
        "premium_buffer_enabled": settings.get('premium_buffer_enabled', False),
        "premium_buffer_amount": settings.get('premium_buffer_amount', 10.0)
    }


@router.put("/premium-buffer-settings")
async def update_premium_buffer_settings(
    premium_buffer_amount: float,
    premium_buffer_enabled: Optional[bool] = None,
):
    """Update premium buffer settings."""
    update_dict = {'premium_buffer_amount': premium_buffer_amount}
    if premium_buffer_enabled is not None:
        update_dict['premium_buffer_enabled'] = premium_buffer_enabled
    await db.update_settings(update_dict)
    settings = await db.get_settings()
    return {
        "premium_buffer_enabled": settings.get('premium_buffer_enabled', False),
        "premium_buffer_amount": settings.get('premium_buffer_amount', premium_buffer_amount),
    }


# Averaging Down
@router.post("/toggle-averaging-down")
async def toggle_averaging_down():
    """Toggle averaging down"""
    settings = await db.get_settings()
    new_state = not settings.get('averaging_down_enabled', False)
    await db.update_settings({'averaging_down_enabled': new_state})
    return {"averaging_down_enabled": new_state}


@router.get("/averaging-down-settings")
async def get_averaging_down_settings():
    """Get averaging down settings"""
    settings = await db.get_settings()
    return {
        "averaging_down_enabled": settings.get('averaging_down_enabled', False),
        "averaging_down_threshold": settings.get('averaging_down_threshold', 10.0),
        "averaging_down_percentage": settings.get('averaging_down_percentage', 25.0),
        "averaging_down_max_buys": settings.get('averaging_down_max_buys', 3)
    }


@router.put("/averaging-down-settings")
async def update_averaging_down_settings(update: AveragingDownSettingsUpdate):
    """Update averaging down settings"""
    update_dict = {k: v for k, v in update.model_dump().items() if v is not None}
    await db.update_settings(update_dict)
    settings = await db.get_settings()
    return {
        "averaging_down_enabled": settings.get('averaging_down_enabled', False),
        "averaging_down_threshold": settings.get('averaging_down_threshold', 10.0),
        "averaging_down_percentage": settings.get('averaging_down_percentage', 25.0),
        "averaging_down_max_buys": settings.get('averaging_down_max_buys', 3)
    }


# Take Profit / Stop Loss
@router.post("/toggle-take-profit")
async def toggle_take_profit():
    """Toggle take profit"""
    settings = await db.get_settings()
    new_state = not settings.get('take_profit_enabled', False)
    await db.update_settings({'take_profit_enabled': new_state})
    return {"take_profit_enabled": new_state}


@router.post("/toggle-stop-loss")
async def toggle_stop_loss():
    """Toggle stop loss"""
    settings = await db.get_settings()
    new_state = not settings.get('stop_loss_enabled', False)
    await db.update_settings({'stop_loss_enabled': new_state})
    return {"stop_loss_enabled": new_state}


@router.get("/risk-management-settings")
async def get_risk_management_settings():
    """Get risk management settings"""
    settings = await db.get_settings()
    return {
        "take_profit_enabled": settings.get('take_profit_enabled', False),
        "take_profit_percentage": settings.get('take_profit_percentage', 50.0),
        "bracket_order_enabled": settings.get('bracket_order_enabled', False),
        "stop_loss_enabled": settings.get('stop_loss_enabled', False),
        "stop_loss_percentage": settings.get('stop_loss_percentage', 25.0),
        "stop_loss_order_type": settings.get('stop_loss_order_type', 'market')
    }


@router.put("/risk-management-settings")
async def update_risk_management_settings(update: RiskManagementSettingsUpdate):
    """Update risk management settings"""
    update_dict = {k: v for k, v in update.model_dump().items() if v is not None}
    if 'stop_loss_order_type' in update_dict and update_dict['stop_loss_order_type'] not in ['market', 'limit']:
        raise HTTPException(status_code=400, detail="stop_loss_order_type must be 'market' or 'limit'")
    await db.update_settings(update_dict)
    settings = await db.get_settings()
    return {
        "take_profit_enabled": settings.get('take_profit_enabled', False),
        "take_profit_percentage": settings.get('take_profit_percentage', 50.0),
        "bracket_order_enabled": settings.get('bracket_order_enabled', False),
        "stop_loss_enabled": settings.get('stop_loss_enabled', False),
        "stop_loss_percentage": settings.get('stop_loss_percentage', 25.0),
        "stop_loss_order_type": settings.get('stop_loss_order_type', 'market')
    }


# Trailing Stop
@router.post("/toggle-trailing-stop")
async def toggle_trailing_stop():
    """Toggle trailing stop"""
    settings = await db.get_settings()
    new_state = not settings.get('trailing_stop_enabled', False)
    await db.update_settings({'trailing_stop_enabled': new_state})
    return {"trailing_stop_enabled": new_state}


@router.get("/trailing-stop-settings")
async def get_trailing_stop_settings():
    """Get trailing stop settings"""
    settings = await db.get_settings()
    return {
        "trailing_stop_enabled": settings.get('trailing_stop_enabled', False),
        "trailing_stop_type": settings.get('trailing_stop_type', 'percent'),
        "trailing_stop_percent": settings.get('trailing_stop_percent', 10.0),
        "trailing_stop_cents": settings.get('trailing_stop_cents', 50.0)
    }


@router.put("/trailing-stop-settings")
async def update_trailing_stop_settings(update: TrailingStopSettingsUpdate):
    """Update trailing stop settings"""
    update_dict = {k: v for k, v in update.model_dump().items() if v is not None}
    if 'trailing_stop_type' in update_dict and update_dict['trailing_stop_type'] not in ['percent', 'premium']:
        raise HTTPException(status_code=400, detail="trailing_stop_type must be 'percent' or 'premium'")
    await db.update_settings(update_dict)
    settings = await db.get_settings()
    return {
        "trailing_stop_enabled": settings.get('trailing_stop_enabled', False),
        "trailing_stop_type": settings.get('trailing_stop_type', 'percent'),
        "trailing_stop_percent": settings.get('trailing_stop_percent', 10.0),
        "trailing_stop_cents": settings.get('trailing_stop_cents', 50.0)
    }


# Auto Shutdown
@router.post("/toggle-auto-shutdown")
async def toggle_auto_shutdown():
    """Toggle auto shutdown"""
    settings = await db.get_settings()
    new_state = not settings.get('auto_shutdown_enabled', False)
    await db.update_settings({'auto_shutdown_enabled': new_state})
    return {"auto_shutdown_enabled": new_state}


@router.get("/auto-shutdown-settings")
async def get_auto_shutdown_settings():
    """Get auto shutdown settings (config) merged with current runtime counters."""
    settings = await db.get_settings()
    # M6: live counters come from runtime_state, not the settings blob
    runtime = await db.get_runtime_state()
    return {
        "auto_shutdown_enabled": settings.get('auto_shutdown_enabled', False),
        "max_consecutive_losses": settings.get('max_consecutive_losses', 3),
        "max_daily_losses": settings.get('max_daily_losses', 5),
        "max_daily_loss_amount": settings.get('max_daily_loss_amount', 500.0),
        "consecutive_losses": runtime.get('consecutive_losses', 0),
        "daily_losses": runtime.get('daily_losses', 0),
        "daily_loss_amount": runtime.get('daily_loss_amount', 0.0),
        "shutdown_triggered": runtime.get('shutdown_triggered', False),
        "shutdown_reason": runtime.get('shutdown_reason', ''),
    }


@router.put("/auto-shutdown-settings")
async def update_auto_shutdown_settings(update: AutoShutdownSettingsUpdate):
    """Update auto shutdown settings"""
    update_dict = {k: v for k, v in update.model_dump().items() if v is not None}
    await db.update_settings(update_dict)
    settings = await db.get_settings()
    return {
        "auto_shutdown_enabled": settings.get('auto_shutdown_enabled', False),
        "max_consecutive_losses": settings.get('max_consecutive_losses', 3),
        "max_daily_losses": settings.get('max_daily_losses', 5),
        "max_daily_loss_amount": settings.get('max_daily_loss_amount', 500.0)
    }


@router.post("/reset-loss-counters")
async def reset_loss_counters(x_admin_key: Optional[str] = Header(default=None)):
    """Reset all loss counters and re-enable trading.
    
    C14 fix: Optionally require admin key header to bypass safety system.
    If ADMIN_API_KEY env var is not set, allow reset without admin key (dev/desktop mode).
    """
    admin_key = os.environ.get("ADMIN_API_KEY", "").strip()
    # Only enforce admin key check if ADMIN_API_KEY is configured
    if admin_key and x_admin_key != admin_key:
        raise HTTPException(status_code=403, detail="Admin key required to reset loss counters")
    from routes.health import bot_status, get_bot_status
    settings = await db.get_settings()
    if not isinstance(settings, dict):
        blocked_readiness = {
            "ready_for_live": False,
            "blocking_issues": [
                {
                    "code": "settings_malformed",
                    "summary": "Persisted settings are malformed.",
                }
            ],
            "blocking_codes": ["settings_malformed"],
        }
        await record_operator_event(
            db,
            "live_safety",
            "loss_counter_reset_blocked",
            "Loss counter reset was blocked because settings are malformed.",
            severity="warning",
            details={"blocking_issues": blocked_readiness["blocking_issues"]},
        )
        raise HTTPException(status_code=409, detail=blocked_readiness)
    if not bool((settings or {}).get("simulation_mode", True)):
        from live_readiness import evaluate_live_readiness

        candidate_settings = dict(settings or {})
        candidate_settings["auto_trading_enabled"] = True
        runtime = await db.get_runtime_state() if hasattr(db, "get_runtime_state") else {}
        readiness = _dict_or_empty(evaluate_live_readiness(candidate_settings, runtime, status=get_bot_status()))
        if not readiness.get("ready_for_live", False):
            await record_operator_event(
                db,
                "live_safety",
                "loss_counter_reset_blocked",
                "Loss counter reset trading re-enable was blocked by live readiness checks.",
                severity="warning",
                details={"blocking_issues": _list_or_empty(readiness.get("blocking_issues"))},
            )
            raise HTTPException(status_code=409, detail=readiness)
    # M6/C16: use the atomic reset method
    await db.reset_loss_counters()
    await db.update_settings({'auto_trading_enabled': True})
    await db.update_runtime_state({'auto_trading_enabled': True})
    bot_status['auto_trading_enabled'] = True
    return {"message": "Loss counters reset, trading re-enabled"}


# Notification settings
@router.get("/notification-settings")
async def get_notification_settings():
    """Get SMS and notification settings."""
    settings = await db.get_settings()
    return {
        "sms_enabled": settings.get("sms_enabled", False),
        "sms_phone_number": settings.get("sms_phone_number", ""),
        "twilio_account_sid": settings.get("twilio_account_sid", ""),
        "twilio_auth_token": "********" if settings.get("twilio_auth_token") else "",
        "twilio_from_number": settings.get("twilio_from_number", ""),
    }


@router.put("/notification-settings")
async def update_notification_settings(
    sms_enabled: Optional[bool] = None,
    sms_phone_number: Optional[str] = None,
    twilio_account_sid: Optional[str] = None,
    twilio_auth_token: Optional[str] = None,
    twilio_from_number: Optional[str] = None,
):
    """Update SMS and notification settings."""
    update: Dict[str, Any] = {}
    if sms_enabled is not None:
        update["sms_enabled"] = sms_enabled
    if sms_phone_number is not None:
        update["sms_phone_number"] = sms_phone_number.strip()
    if twilio_account_sid is not None:
        update["twilio_account_sid"] = twilio_account_sid.strip()
    if twilio_auth_token is not None:
        update["twilio_auth_token"] = twilio_auth_token.strip()
    if twilio_from_number is not None:
        update["twilio_from_number"] = twilio_from_number.strip()
    if update:
        await db.update_settings(update)
    return {"message": "Notification settings updated"}


@router.post("/notification-settings/test")
async def test_sms_notification():
    """Send a test SMS to verify Twilio credentials."""
    from notifications import send_notification

    settings = await db.get_settings()
    if not settings.get("sms_enabled"):
        raise HTTPException(status_code=400, detail="SMS notifications are disabled.")
    entry = await send_notification(
        event_type="test",
        message="This is a test SMS from your Trading Bot. If you receive this, notifications are working!",
        settings=settings,
    )
    if not entry["sent_sms"]:
        raise HTTPException(status_code=500, detail=entry.get("error", "Send failed"))
    return {"message": "Test SMS sent successfully."}


@router.get("/notification-log")
async def get_notification_log():
    """Get the last notification events."""
    from notifications import get_notification_log

    return get_notification_log()


# Broker Connection Check
@router.post("/check-broker-connection")
async def check_broker_connection():
    """Check if broker is connected"""
    from routes.health import bot_status
    from order_execution import close_broker_client, get_configured_broker_client

    settings = await db.get_settings()
    if not settings:
        return {"connected": False, "broker": None, "error": "No settings configured"}
    if not isinstance(settings, dict):
        bot_status['broker_connected'] = False
        return {"connected": False, "broker": None, "error": "Settings are malformed"}

    active_broker = settings.get('active_broker', 'ibkr')
    broker_client = None
    try:
        broker_client = get_configured_broker_client(settings, active_broker)
        connected = await broker_client.check_connection()
        bot_status['broker_connected'] = connected
        return {"connected": connected, "broker": active_broker}
    except Exception as e:
        # M16 fix: never return str(e) directly — exception messages from broker
        # clients can contain API keys or auth tokens embedded in connection strings.
        import logging as _log
        _log.getLogger(__name__).error("Broker connection check failed for %s: %s", active_broker, e)
        return {"connected": False, "broker": active_broker, "error": "Connection check failed — see server logs for details"}
    finally:
        if broker_client is not None:
            await close_broker_client(broker_client)


async def check_and_trigger_shutdown(realized_pnl: float):
    """
    Check if auto shutdown should be triggered after a losing trade.

    C16 fix: counter increments now go through db.increment_loss_counters() which
             is a single atomic DB-level UPDATE -- no read-modify-write race.
    M6  fix: counters are read from db.get_runtime_state(), not the settings blob.
    """
    from routes.health import bot_status

    settings = await db.get_settings()
    if not isinstance(settings, dict):
        shutdown_reason = "Settings are malformed"
        await db.update_runtime_state({
            'shutdown_triggered': True,
            'shutdown_reason': shutdown_reason,
            'auto_trading_enabled': False,
        })
        await db.update_settings({'auto_trading_enabled': False})
        bot_status['auto_trading_enabled'] = False
        logger.error("AUTO SHUTDOWN TRIGGERED: %s", shutdown_reason)
        return shutdown_reason

    if not settings.get('auto_shutdown_enabled', False):
        return None

    # Reset daily counters if the calendar day has rolled over
    runtime = await db.get_runtime_state()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if runtime.get('last_loss_reset_date', '') != today:
        await db.update_runtime_state({
            'daily_losses': 0,
            'daily_loss_amount': 0.0,
            'last_loss_reset_date': today,
        })
        runtime['daily_losses'] = 0
        runtime['daily_loss_amount'] = 0.0

    if realized_pnl < 0:
        # C16: single atomic increment -- no race between concurrent trades
        runtime = await db.increment_loss_counters(abs(realized_pnl))

        max_consecutive = settings.get('max_consecutive_losses', 3)
        max_daily = settings.get('max_daily_losses', 5)
        max_daily_amount = settings.get('max_daily_loss_amount', 500.0)

        new_consecutive = runtime['consecutive_losses']
        new_daily = runtime['daily_losses']
        new_amount = runtime['daily_loss_amount']

        shutdown_reason = None
        if new_consecutive >= max_consecutive:
            shutdown_reason = f"Max consecutive losses reached ({new_consecutive}/{max_consecutive})"
        elif new_daily >= max_daily:
            shutdown_reason = f"Max daily losses reached ({new_daily}/{max_daily})"
        elif new_amount >= max_daily_amount:
            shutdown_reason = f"Max daily loss amount reached (${new_amount:.2f}/${max_daily_amount:.2f})"

        if shutdown_reason:
            await db.update_runtime_state({
                'shutdown_triggered': True,
                'shutdown_reason': shutdown_reason,
                'auto_trading_enabled': False,
            })
            await db.update_settings({'auto_trading_enabled': False})
            bot_status['auto_trading_enabled'] = False
            logger.warning("AUTO SHUTDOWN TRIGGERED: %s", shutdown_reason)
            return shutdown_reason
    else:
        # Winning trade resets consecutive counter only
        await db.update_runtime_state({'consecutive_losses': 0})

    return None
