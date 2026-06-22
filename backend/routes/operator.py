"""Operator lab, safety controls, reconciliation, and event log endpoints."""
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from live_arming import arm_live_trading, disarm_live_trading
from live_readiness import evaluate_live_readiness
from operator_audit import record_operator_event
from readiness_status import readiness_ready_for_live, status_flag
from reconciliation import build_alert_chain_report, build_reconciliation_rows, summarize_reconciliation_rows
from routes.trading import create_test_alert_records
from settings_flags import coerce_bool

router = APIRouter(tags=["Operator"])

db = None


def set_db(database):
    """Set the database reference."""
    global db
    db = database


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _is_live_open_position(position: dict[str, Any]) -> bool:
    status = _clean_text(position.get("status") or "open").lower()
    broker = _clean_text(position.get("broker")).lower()
    if status not in {"open", "partial"}:
        return False
    if _positive_int(position.get("remaining_quantity") or position.get("quantity")) <= 0:
        return False
    if coerce_bool(position.get("simulated"), default=False):
        return False
    return not broker.endswith(":paper_shadow")


def _extract_order_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("order_id", "id", "client_order_id"):
            order_id = _clean_text(value.get(key))
            if order_id:
                return order_id
        return ""
    return _clean_text(value)


def _position_has_oco_exit_proof(position: dict[str, Any]) -> bool:
    if coerce_bool(position.get("oco_exit_protected"), default=False):
        return True
    plan = _dict_or_empty(position.get("oco_exit_plan") or position.get("exit_plan"))
    plan_status = _clean_text(plan.get("status")).lower()
    if plan_status and plan_status not in {"active", "armed", "protected", "submitted"}:
        return False

    take_profit_order_id = (
        _extract_order_id(plan.get("take_profit"))
        or _extract_order_id(plan.get("take_profit_order"))
        or _clean_text(plan.get("take_profit_order_id"))
        or _clean_text(position.get("take_profit_order_id"))
    )
    stop_loss_order_id = (
        _extract_order_id(plan.get("stop_loss"))
        or _extract_order_id(plan.get("stop_loss_order"))
        or _clean_text(plan.get("stop_loss_order_id"))
        or _clean_text(position.get("stop_loss_order_id"))
    )
    return bool(take_profit_order_id and stop_loss_order_id)


def _summarize_position_oco_protection(positions: list[dict[str, Any]]) -> dict[str, Any]:
    unprotected_ids = [
        _clean_text(position.get("id")) or _clean_text(position.get("_id"))
        for position in positions
        if _is_live_open_position(position) and not _position_has_oco_exit_proof(position)
    ]
    unprotected_ids = [position_id for position_id in unprotected_ids if position_id]
    return {
        "position_oco_unprotected_count": len(unprotected_ids),
        "position_oco_unprotected_ids": unprotected_ids,
    }


class OperatorSimulateExitRequest(BaseModel):
    position_id: Optional[str] = None
    sell_percentage: float = Field(default=50, ge=1, le=100)
    exit_price: float = Field(default=1.8, gt=0)


class LiveArmRequest(BaseModel):
    duration_minutes: int = Field(default=60, ge=1, le=480)
    confirmation: str
    reason: str = ""


async def _live_readiness_payload():
    from routes.health import get_bot_status
    from bridge_health import evaluate_bridge_health

    settings = await db.get_settings()
    runtime = await db.get_runtime_state() if hasattr(db, "get_runtime_state") else {}
    status = dict(get_bot_status())
    status["chrome_bridge_healthy"] = status_flag(evaluate_bridge_health(), "healthy")
    reconciliation = summarize_reconciliation_rows(await build_reconciliation_rows(db, limit=500))
    alert_chains = await build_alert_chain_report(db, limit=500)
    alert_chain_summary = _dict_or_empty(alert_chains.get("summary"))
    position_oco = _summarize_position_oco_protection(await db.get_positions())
    status["reconciliation_unresolved_count"] = reconciliation["unresolved_count"]
    status["reconciliation_unresolved_reasons"] = reconciliation["unresolved_reasons"]
    status["alert_chain_attention_count"] = alert_chain_summary.get("attention_count", 0)
    status["alert_chain_attention_reasons"] = alert_chain_summary.get("attention_reasons", [])
    status.update(position_oco)
    return evaluate_live_readiness(settings, runtime, status=status)


@router.get("/operator/events")
async def get_operator_events(limit: int = Query(default=100, ge=1, le=500)):
    """Return recent operator-visible events."""
    return await db.get_operator_events(limit)


@router.post("/operator/test-alert")
async def create_operator_test_alert():
    """Create a safe simulated alert/trade/position and log the action."""
    result = await create_test_alert_records(db, message="Operator test alert created")
    event = await record_operator_event(
        db,
        "test_lab",
        "test_alert_created",
        "Created simulated SPY alert, trade, and position.",
        details=result,
    )
    return {**result, "event_id": event["id"]}


@router.post("/operator/simulate-exit")
async def simulate_exit(request: OperatorSimulateExitRequest):
    """Sell a simulated/open position from the operator lab and log the action."""
    position_id = request.position_id
    if not position_id:
        positions = await db.get_positions()
        first_open = next(
            (
                position for position in positions
                if position.get("status") in {"open", "partial"} and int(position.get("remaining_quantity") or 0) > 0
            ),
            None,
        )
        if not first_open:
            raise HTTPException(status_code=404, detail="No open position is available to sell.")
        position_id = first_open["id"]

    from routes import trading as trading_route

    result = await trading_route.sell_position_from_operator(
        position_id,
        sell_percentage=request.sell_percentage,
        exit_price=request.exit_price,
    )
    event = await record_operator_event(
        db,
        "test_lab",
        "simulated_exit",
        f"Sold {result.get('sold_quantity', 0)} contract(s) from a test position.",
        details=result,
    )
    return {**result, "event_id": event["id"]}


@router.get("/operator/live-readiness")
async def get_live_readiness():
    """Return current live-trading readiness and runtime arming state."""
    return await _live_readiness_payload()


@router.post("/operator/live-arm")
async def live_arm(request: LiveArmRequest):
    """Arm live trading for a bounded runtime window after readiness passes."""
    readiness = _dict_or_empty(await _live_readiness_payload())
    if not readiness_ready_for_live(readiness):
        await record_operator_event(
            db,
            "live_safety",
            "live_trading_arm_blocked",
            "Live trading arm was blocked by readiness checks.",
            severity="warning",
            details={"blocking_issues": _list_or_empty(readiness.get("blocking_issues"))},
        )
        raise HTTPException(status_code=409, detail=readiness)
    try:
        runtime = await arm_live_trading(
            db,
            duration_minutes=request.duration_minutes,
            confirmation=request.confirmation,
            readiness=readiness,
            reason=request.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"runtime": runtime, "readiness": readiness}


@router.post("/operator/live-disarm")
async def live_disarm():
    """Disarm live trading immediately."""
    runtime = await disarm_live_trading(db)
    return {"runtime": runtime}


@router.post("/operator/panic-stop")
async def panic_stop():
    """Disable automated live trading and set runtime shutdown state."""
    from broker_capabilities import get_broker_capabilities, normalize_broker_id
    from routes.health import update_bot_status

    settings = await db.get_settings()
    settings = settings if isinstance(settings, dict) else {}
    active_broker = normalize_broker_id(settings.get("active_broker"), default="ibkr")
    capabilities = get_broker_capabilities(active_broker)

    settings_updates = {"auto_trading_enabled": False}
    runtime_updates = {
        "auto_trading_enabled": False,
        "live_trading_armed": False,
        "live_trading_armed_until": "",
        "shutdown_triggered": True,
        "shutdown_reason": "panic stop triggered by operator",
    }
    updated_settings = await db.update_settings(settings_updates)
    updated_settings = updated_settings if isinstance(updated_settings, dict) else settings_updates
    runtime = await db.update_runtime_state(runtime_updates)
    runtime = runtime if isinstance(runtime, dict) else runtime_updates
    update_bot_status("auto_trading_enabled", False)

    warnings = []
    cancellation_attempts = []
    if not capabilities.get("supports_cancel_order"):
        warnings.append(f"Broker '{active_broker}' does not advertise automated cancellation support.")
    else:
        warnings.append("No pending order registry is available; broker cancellations were not attempted.")

    event = await record_operator_event(
        db,
        "live_safety",
        "panic_stop",
        "Panic stop disabled automated trading and disarmed live trading.",
        severity="critical",
        details={
            "active_broker": active_broker,
            "cancellation_attempts": cancellation_attempts,
            "warnings": warnings,
        },
    )
    return {
        "auto_trading_enabled": coerce_bool(updated_settings.get("auto_trading_enabled"), default=False),
        "live_trading_armed": coerce_bool(runtime.get("live_trading_armed"), default=False),
        "shutdown_triggered": coerce_bool(runtime.get("shutdown_triggered"), default=False),
        "shutdown_reason": runtime.get("shutdown_reason", ""),
        "cancellation_attempts": cancellation_attempts,
        "warnings": warnings,
        "event_id": event["id"],
    }


@router.get("/operator/reconciliation")
async def get_reconciliation(limit: int = Query(default=100, ge=1, le=500)):
    """Return alert/trade/position reconciliation rows."""
    return await build_reconciliation_rows(db, limit=limit)


@router.get("/operator/alert-chains")
async def get_alert_chains(limit: int = Query(default=100, ge=1, le=500)):
    """Return deterministic alert chain rows from bridge observation through reconciliation."""
    return await build_alert_chain_report(db, limit=limit)
