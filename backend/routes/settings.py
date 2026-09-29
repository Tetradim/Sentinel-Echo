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
from readiness_status import readiness_ready_for_live
from settings_flags import coerce_bool
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

_BOOLEAN_SETTING_DEFAULTS = {
    "auto_trading_enabled": True,
    "sell_alert_listening_enabled": True,
    "trim_alert_listening_enabled": True,
    "smart_sizing_enabled": True,
    "entry_slippage_sizing_enabled": True,
    "coordinated_loss_ladder_enabled": True,
    "core_runner_enabled": False,
    "core_runner_allow_single_contract": False,
    "core_runner_reserve_candidates_from_profit": True,
    "core_runner_loss_ladder_consumes_candidates": True,
    "core_runner_protect_loss_ladder": True,
    "core_runner_protect_hard_stop": True,
    "core_runner_protect_break_even": True,
    "core_runner_protect_profit_stages": True,
    "core_runner_protect_ordinary_trailing": True,
    "core_runner_protect_reversal_warning": True,
    "core_runner_protect_contextual_trims": True,
    "core_runner_confirmed_reversal_exits": True,
    "core_runner_trailing_enabled": True,
    "core_runner_require_fresh_high": False,
    "core_runner_allow_floor_to_move_down": False,
    "core_runner_explicit_full_exit_overrides": True,
    "core_runner_contextual_full_exit_overrides": False,
    "core_runner_zero_dte_liquidation_enabled": True,
    "marketable_entry_enabled": True,
    "premium_buffer_enabled": False,
    "simulation_mode": False,
    "averaging_down_enabled": False,
    "take_profit_enabled": False,
    "bracket_order_enabled": False,
    "break_even_enabled": False,
    "stop_loss_enabled": False,
    "trailing_stop_enabled": False,
    "reversal_exit_enabled": True,
    "adaptive_trailing_enabled": True,
    "zero_dte_liquidation_enabled": True,
    "auto_shutdown_enabled": False,
    "shutdown_triggered": False,
    "sms_enabled": False,
}


def set_db(database):
    """Set the database reference"""
    global db
    db = database


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_loss_ladder(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > 10:
        raise ValueError("loss ladder must contain between 1 and 10 steps")
    normalized = []
    previous_loss = 0.0
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"loss ladder step {index + 1} must be an object")
        try:
            loss_percent = float(raw.get("loss_percent"))
            quantity = float(raw.get("quantity"))
            confirmations = int(raw.get("confirmations", 2))
        except (TypeError, ValueError):
            raise ValueError(f"loss ladder step {index + 1} contains an invalid number")
        quantity_mode = str(raw.get("quantity_mode") or "percent_original").strip().lower()
        allocation_target = str(raw.get("allocation_target") or "core_only").strip().lower()
        if not 0 < loss_percent <= 100 or loss_percent <= previous_loss:
            raise ValueError("loss ladder loss percentages must increase and stay within 0-100")
        if quantity_mode not in {"fixed", "percent_original", "percent_remaining"}:
            raise ValueError(f"loss ladder step {index + 1} has an invalid quantity mode")
        if allocation_target not in {"core_only", "runners_only", "core_then_runners", "entire_position"}:
            raise ValueError(f"loss ladder step {index + 1} has an invalid allocation target")
        if quantity <= 0 or (quantity_mode != "fixed" and quantity > 100):
            raise ValueError(f"loss ladder step {index + 1} has an invalid quantity")
        if not 1 <= confirmations <= 10:
            raise ValueError(f"loss ladder step {index + 1} confirmations must be 1-10")
        normalized.append(
            {
                "loss_percent": loss_percent,
                "quantity_mode": quantity_mode,
                "quantity": quantity,
                "confirmations": confirmations,
                "allocation_target": allocation_target,
            }
        )
        previous_loss = loss_percent
    return normalized


def _normalize_runner_trailing_tiers(value: Any) -> list[dict[str, float]]:
    if not isinstance(value, list) or not value or len(value) > 10:
        raise ValueError("runner trailing tiers must contain between 1 and 10 rows")
    normalized: list[dict[str, float]] = []
    previous_mfe = -1.0
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"runner trailing tier {index + 1} must be an object")
        try:
            mfe_percent = float(raw.get("mfe_percent"))
            trail_percent = float(raw.get("trail_percent"))
        except (TypeError, ValueError):
            raise ValueError(f"runner trailing tier {index + 1} contains an invalid number")
        if mfe_percent < 0 or mfe_percent <= previous_mfe:
            raise ValueError("runner trailing MFE thresholds must strictly increase")
        if not 1 <= trail_percent <= 100:
            raise ValueError("runner trailing widths must stay within 1-100")
        normalized.append({"mfe_percent": mfe_percent, "trail_percent": trail_percent})
        previous_mfe = mfe_percent
    return normalized


def _settings_response(settings: Dict[str, Any] | None) -> Dict[str, Any]:
    """Return settings safe for API clients: no plaintext broker credentials."""
    stored = settings if isinstance(settings, dict) else {}
    response = {**Settings().model_dump(), **stored}
    for field, default in _BOOLEAN_SETTING_DEFAULTS.items():
        if field in response:
            response[field] = coerce_bool(response.get(field), default=default)
    response["simulation_mode"] = False
    discord_token = str(response.get("discord_token") or "").strip()
    response["discord_token_configured"] = bool(discord_token)
    if discord_token:
        response["discord_token"] = "********"
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
    update_dict.pop("simulation_mode", None)
    existing_settings = _dict_or_empty(await db.get_settings())
    if "coordinated_loss_ladder" in update_dict:
        try:
            update_dict["coordinated_loss_ladder"] = _normalize_loss_ladder(
                update_dict["coordinated_loss_ladder"]
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    if "core_runner_trailing_tiers" in update_dict:
        try:
            update_dict["core_runner_trailing_tiers"] = _normalize_runner_trailing_tiers(
                update_dict["core_runner_trailing_tiers"]
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    candidate = {**Settings().model_dump(), **existing_settings, **update_dict}
    if candidate["reversal_confirmed_confirmations"] <= candidate["reversal_warning_confirmations"]:
        raise HTTPException(
            status_code=400,
            detail="reversal_confirmed_confirmations must be greater than reversal_warning_confirmations",
        )
    if candidate["adaptive_trailing_max_percent"] < candidate["adaptive_trailing_min_percent"]:
        raise HTTPException(
            status_code=400,
            detail="adaptive_trailing_max_percent must be at least adaptive_trailing_min_percent",
        )
    if candidate["coordinated_elastic_trailing_max_percent"] < candidate["coordinated_elastic_trailing_start_percent"]:
        raise HTTPException(
            status_code=400,
            detail="elastic trailing maximum must be at least its starting width",
        )
    if candidate["entry_slippage_severe_percent"] <= candidate["entry_slippage_warning_percent"]:
        raise HTTPException(
            status_code=400,
            detail="entry_slippage_severe_percent must be greater than entry_slippage_warning_percent",
        )
    if (
        candidate["coordinated_fast_scalp_profit_stage_2_percent"]
        <= candidate["coordinated_fast_scalp_profit_stage_1_percent"]
    ):
        raise HTTPException(
            status_code=400,
            detail="fast-scalp second profit target must be greater than the first",
        )
    if candidate["coordinated_emergency_stop_loss_percent"] < candidate["coordinated_normal_stop_loss_percent"]:
        raise HTTPException(
            status_code=400,
            detail="emergency stop loss must not be tighter than the normal stop loss",
        )
    if (
        candidate["core_runner_max_contracts"] > 0
        and candidate["core_runner_min_contracts"] > candidate["core_runner_max_contracts"]
    ):
        raise HTTPException(
            status_code=400,
            detail="core runner minimum contracts must not exceed its maximum",
        )
    if "source_overrides" in update_dict:
        try:
            update_dict["source_overrides"] = normalize_source_overrides(update_dict["source_overrides"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    if is_masked_secret(update_dict.get("discord_token")):
        update_dict.pop("discord_token", None)
    # C4: broker screens save one config at a time, so merge before encryption.
    if 'broker_configs' in update_dict:
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
    settings = _dict_or_empty(await db.get_settings())
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
    current = coerce_bool((settings or {}).get("auto_trading_enabled"), default=True)
    new_state = not current
    if new_state and not coerce_bool((settings or {}).get("simulation_mode"), default=False):
        from live_readiness import evaluate_live_readiness
        from routes.health import get_bot_status

        candidate_settings = dict(settings or {})
        candidate_settings["auto_trading_enabled"] = True
        runtime = await db.get_runtime_state() if hasattr(db, "get_runtime_state") else {}
        readiness = _dict_or_empty(evaluate_live_readiness(candidate_settings, runtime, status=get_bot_status()))
        if not readiness_ready_for_live(readiness):
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
    settings = _dict_or_empty(await db.get_settings())
    new_state = not coerce_bool(settings.get('premium_buffer_enabled'), default=False)
    await db.update_settings({'premium_buffer_enabled': new_state})
    return {"premium_buffer_enabled": new_state}


@router.get("/premium-buffer-settings")
async def get_premium_buffer_settings():
    """Get premium buffer settings"""
    settings = _dict_or_empty(await db.get_settings())
    return {
        "premium_buffer_enabled": coerce_bool(settings.get('premium_buffer_enabled'), default=False),
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
    settings = {**update_dict, **_dict_or_empty(await db.get_settings())}
    return {
        "premium_buffer_enabled": coerce_bool(settings.get('premium_buffer_enabled'), default=False),
        "premium_buffer_amount": settings.get('premium_buffer_amount', premium_buffer_amount),
    }


# Averaging Down
@router.post("/toggle-averaging-down")
async def toggle_averaging_down():
    """Toggle averaging down"""
    settings = _dict_or_empty(await db.get_settings())
    new_state = not coerce_bool(settings.get('averaging_down_enabled'), default=False)
    await db.update_settings({'averaging_down_enabled': new_state})
    return {"averaging_down_enabled": new_state}


@router.get("/averaging-down-settings")
async def get_averaging_down_settings():
    """Get averaging down settings"""
    settings = _dict_or_empty(await db.get_settings())
    return {
        "averaging_down_enabled": coerce_bool(settings.get('averaging_down_enabled'), default=False),
        "averaging_down_threshold": settings.get('averaging_down_threshold', 10.0),
        "averaging_down_percentage": settings.get('averaging_down_percentage', 25.0),
        "averaging_down_max_buys": settings.get('averaging_down_max_buys', 3)
    }


@router.put("/averaging-down-settings")
async def update_averaging_down_settings(update: AveragingDownSettingsUpdate):
    """Update averaging down settings"""
    update_dict = {k: v for k, v in update.model_dump().items() if v is not None}
    await db.update_settings(update_dict)
    settings = {**update_dict, **_dict_or_empty(await db.get_settings())}
    return {
        "averaging_down_enabled": coerce_bool(settings.get('averaging_down_enabled'), default=False),
        "averaging_down_threshold": settings.get('averaging_down_threshold', 10.0),
        "averaging_down_percentage": settings.get('averaging_down_percentage', 25.0),
        "averaging_down_max_buys": settings.get('averaging_down_max_buys', 3)
    }


# Take Profit / Stop Loss
@router.post("/toggle-take-profit")
async def toggle_take_profit():
    """Toggle take profit"""
    settings = _dict_or_empty(await db.get_settings())
    new_state = not coerce_bool(settings.get('take_profit_enabled'), default=False)
    await db.update_settings({'take_profit_enabled': new_state})
    return {"take_profit_enabled": new_state}


@router.post("/toggle-stop-loss")
async def toggle_stop_loss():
    """Toggle stop loss"""
    settings = _dict_or_empty(await db.get_settings())
    new_state = not coerce_bool(settings.get('stop_loss_enabled'), default=False)
    await db.update_settings({'stop_loss_enabled': new_state})
    return {"stop_loss_enabled": new_state}


@router.get("/risk-management-settings")
async def get_risk_management_settings():
    """Get risk management settings"""
    settings = _dict_or_empty(await db.get_settings())
    return {
        "take_profit_enabled": coerce_bool(settings.get('take_profit_enabled'), default=False),
        "take_profit_percentage": settings.get('take_profit_percentage', 50.0),
        "take_profit_sell_percentage": settings.get('take_profit_sell_percentage', 100.0),
        "bracket_order_enabled": coerce_bool(settings.get('bracket_order_enabled'), default=False),
        "break_even_enabled": coerce_bool(settings.get('break_even_enabled'), default=False),
        "break_even_activation_type": settings.get('break_even_activation_type', 'percent'),
        "break_even_activation_percentage": settings.get('break_even_activation_percentage', 10.0),
        "break_even_activation_cents": settings.get('break_even_activation_cents', 10.0),
        "stop_loss_enabled": coerce_bool(settings.get('stop_loss_enabled'), default=False),
        "stop_loss_percentage": settings.get('stop_loss_percentage', 25.0),
        "stop_loss_order_type": settings.get('stop_loss_order_type', 'market')
    }


@router.put("/risk-management-settings")
async def update_risk_management_settings(update: RiskManagementSettingsUpdate):
    """Update risk management settings"""
    update_dict = {k: v for k, v in update.model_dump().items() if v is not None}
    if 'stop_loss_order_type' in update_dict and update_dict['stop_loss_order_type'] not in ['market', 'limit']:
        raise HTTPException(status_code=400, detail="stop_loss_order_type must be 'market' or 'limit'")
    if 'break_even_activation_type' in update_dict and update_dict['break_even_activation_type'] not in ['percent', 'cents']:
        raise HTTPException(status_code=400, detail="break_even_activation_type must be 'percent' or 'cents'")
    await db.update_settings(update_dict)
    settings = {**update_dict, **_dict_or_empty(await db.get_settings())}
    return {
        "take_profit_enabled": coerce_bool(settings.get('take_profit_enabled'), default=False),
        "take_profit_percentage": settings.get('take_profit_percentage', 50.0),
        "take_profit_sell_percentage": settings.get('take_profit_sell_percentage', 100.0),
        "bracket_order_enabled": coerce_bool(settings.get('bracket_order_enabled'), default=False),
        "break_even_enabled": coerce_bool(settings.get('break_even_enabled'), default=False),
        "break_even_activation_type": settings.get('break_even_activation_type', 'percent'),
        "break_even_activation_percentage": settings.get('break_even_activation_percentage', 10.0),
        "break_even_activation_cents": settings.get('break_even_activation_cents', 10.0),
        "stop_loss_enabled": coerce_bool(settings.get('stop_loss_enabled'), default=False),
        "stop_loss_percentage": settings.get('stop_loss_percentage', 25.0),
        "stop_loss_order_type": settings.get('stop_loss_order_type', 'market')
    }


# Trailing Stop
@router.post("/toggle-trailing-stop")
async def toggle_trailing_stop():
    """Toggle trailing stop"""
    settings = _dict_or_empty(await db.get_settings())
    new_state = not coerce_bool(settings.get('trailing_stop_enabled'), default=False)
    await db.update_settings({'trailing_stop_enabled': new_state})
    return {"trailing_stop_enabled": new_state}


@router.get("/trailing-stop-settings")
async def get_trailing_stop_settings():
    """Get trailing stop settings"""
    settings = _dict_or_empty(await db.get_settings())
    return {
        "trailing_stop_enabled": coerce_bool(settings.get('trailing_stop_enabled'), default=False),
        "trailing_stop_type": settings.get('trailing_stop_type', 'percent'),
        "trailing_stop_percent": settings.get('trailing_stop_percent', 10.0),
        "trailing_stop_activation_percent": settings.get('trailing_stop_activation_percent', 10.0),
        "trailing_stop_cents": settings.get('trailing_stop_cents', 50.0)
    }


@router.put("/trailing-stop-settings")
async def update_trailing_stop_settings(update: TrailingStopSettingsUpdate):
    """Update trailing stop settings"""
    update_dict = {k: v for k, v in update.model_dump().items() if v is not None}
    if 'trailing_stop_type' in update_dict and update_dict['trailing_stop_type'] not in ['percent', 'premium']:
        raise HTTPException(status_code=400, detail="trailing_stop_type must be 'percent' or 'premium'")
    await db.update_settings(update_dict)
    settings = {**update_dict, **_dict_or_empty(await db.get_settings())}
    return {
        "trailing_stop_enabled": coerce_bool(settings.get('trailing_stop_enabled'), default=False),
        "trailing_stop_type": settings.get('trailing_stop_type', 'percent'),
        "trailing_stop_percent": settings.get('trailing_stop_percent', 10.0),
        "trailing_stop_activation_percent": settings.get('trailing_stop_activation_percent', 10.0),
        "trailing_stop_cents": settings.get('trailing_stop_cents', 50.0)
    }


# Auto Shutdown
@router.post("/toggle-auto-shutdown")
async def toggle_auto_shutdown():
    """Toggle auto shutdown"""
    settings = _dict_or_empty(await db.get_settings())
    new_state = not coerce_bool(settings.get('auto_shutdown_enabled'), default=False)
    await db.update_settings({'auto_shutdown_enabled': new_state})
    return {"auto_shutdown_enabled": new_state}


@router.get("/auto-shutdown-settings")
async def get_auto_shutdown_settings():
    """Get auto shutdown settings (config) merged with current runtime counters."""
    settings = _dict_or_empty(await db.get_settings())
    # M6: live counters come from runtime_state, not the settings blob
    runtime = _dict_or_empty(await db.get_runtime_state())
    return {
        "auto_shutdown_enabled": coerce_bool(settings.get('auto_shutdown_enabled'), default=False),
        "max_consecutive_losses": settings.get('max_consecutive_losses', 3),
        "max_daily_losses": settings.get('max_daily_losses', 5),
        "max_daily_loss_amount": settings.get('max_daily_loss_amount', 500.0),
        "consecutive_losses": runtime.get('consecutive_losses', 0),
        "daily_losses": runtime.get('daily_losses', 0),
        "daily_loss_amount": runtime.get('daily_loss_amount', 0.0),
        "shutdown_triggered": coerce_bool(runtime.get('shutdown_triggered'), default=False),
        "shutdown_reason": runtime.get('shutdown_reason', ''),
    }


@router.put("/auto-shutdown-settings")
async def update_auto_shutdown_settings(update: AutoShutdownSettingsUpdate):
    """Update auto shutdown settings"""
    update_dict = {k: v for k, v in update.model_dump().items() if v is not None}
    await db.update_settings(update_dict)
    settings = {**update_dict, **_dict_or_empty(await db.get_settings())}
    return {
        "auto_shutdown_enabled": coerce_bool(settings.get('auto_shutdown_enabled'), default=False),
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
    if not coerce_bool((settings or {}).get("simulation_mode"), default=False):
        from live_readiness import evaluate_live_readiness

        candidate_settings = dict(settings or {})
        candidate_settings["auto_trading_enabled"] = True
        runtime = await db.get_runtime_state() if hasattr(db, "get_runtime_state") else {}
        readiness = _dict_or_empty(evaluate_live_readiness(candidate_settings, runtime, status=get_bot_status()))
        if not readiness_ready_for_live(readiness):
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
    settings = _dict_or_empty(await db.get_settings())
    return {
        "sms_enabled": coerce_bool(settings.get("sms_enabled"), default=False),
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

    settings = _dict_or_empty(await db.get_settings())
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
    runtime = _dict_or_empty(await db.get_runtime_state())
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
