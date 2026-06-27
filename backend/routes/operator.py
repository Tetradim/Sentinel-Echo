"""Operator lab, safety controls, reconciliation, and event log endpoints."""
from datetime import datetime, timezone
import inspect
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update
from live_arming import arm_live_trading, disarm_live_trading
from live_readiness import evaluate_live_readiness, required_readiness_gate_definitions
from order_execution import BrokerConfigurationError, close_broker_client, get_configured_broker_client
from operator_audit import record_operator_event
from readiness_evidence import (
    current_market_session,
    paper_session_snapshots,
    readiness_gate_states_from_events,
    record_readiness_gate_evidence as record_gate_evidence,
    snapshot_counts_for_multi_session,
    snapshot_is_healthy,
    transition_snapshot,
)
from readiness_status import readiness_ready_for_live, status_flag
from reconciliation import build_alert_chain_report, build_reconciliation_rows, summarize_reconciliation_rows
from routes.trading import create_test_alert_records
from settings_flags import coerce_bool
from trailing_stop_engine import evaluate_trailing_stop as build_trailing_stop_decision

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


def _pending_trade_order_id(trade: dict[str, Any]) -> str:
    return (
        _clean_text(trade.get("order_id"))
        or _clean_text(trade.get("broker_order_id"))
        or _extract_broker_order_id(trade.get("broker_order"))
    )


def _broker_id_text(value: Any) -> str:
    return _clean_text(getattr(value, "value", value)).lower()


def _pending_live_broker_orders(
    trades: list[Any],
    *,
    active_broker: str,
) -> list[dict[str, str]]:
    pending_statuses = {"pending", "submitted", "unconfirmed"}
    orders: list[dict[str, str]] = []
    seen_order_ids: set[str] = set()
    for value in trades:
        if not isinstance(value, dict):
            continue
        status = _clean_text(value.get("status")).lower()
        order_id = _pending_trade_order_id(value)
        if status not in pending_statuses or not order_id:
            continue
        if coerce_bool(value.get("simulated"), default=False):
            continue
        broker = _broker_id_text(value.get("broker"))
        if broker.endswith(":paper_shadow"):
            continue
        if broker and broker != active_broker:
            continue
        if order_id in seen_order_ids:
            continue
        seen_order_ids.add(order_id)
        orders.append(
            {
                "trade_id": _clean_text(value.get("id") or value.get("_id")),
                "order_id": order_id,
                "source": "local_registry",
            }
        )
    return orders


def _pending_live_broker_trades(
    trades: list[Any],
    *,
    active_broker: str,
) -> list[dict[str, Any]]:
    pending_order_ids = {
        order["order_id"]
        for order in _pending_live_broker_orders(trades, active_broker=active_broker)
    }
    pending_trades: list[dict[str, Any]] = []
    seen_order_ids: set[str] = set()
    for value in trades:
        if not isinstance(value, dict):
            continue
        order_id = _pending_trade_order_id(value)
        if not order_id or order_id not in pending_order_ids or order_id in seen_order_ids:
            continue
        seen_order_ids.add(order_id)
        pending_trades.append(value)
    return pending_trades


def _order_context_from_trade(trade: dict[str, Any], *, order_id: str) -> OrderContext:
    return OrderContext(
        trade_id=_clean_text(trade.get("id") or trade.get("_id")),
        order_id=order_id,
        side=_clean_text(trade.get("side") or "BUY").upper() or "BUY",
        ticker=_clean_text(trade.get("ticker")),
        strike=float(trade.get("strike") or 0.0),
        option_type=_clean_text(trade.get("option_type")),
        expiration=_clean_text(trade.get("expiration")),
        requested_quantity=max(int(trade.get("quantity") or 1), 1),
        broker=_clean_text(trade.get("broker")),
        position_id=_clean_text(trade.get("position_id")) or None,
        alert_id=_clean_text(trade.get("alert_id")) or None,
        alert_price=float(trade.get("entry_price") or trade.get("exit_price") or 0.0) or None,
        simulated=coerce_bool(trade.get("simulated"), default=False),
    )


def _broker_update_from_status(status_data: dict[str, Any]) -> BrokerOrderUpdate:
    return BrokerOrderUpdate(
        status=_clean_text(status_data.get("status") or "unknown").lower(),
        filled_qty=_positive_int(status_data.get("filled_qty")),
        avg_fill_price=float(status_data.get("avg_fill_price") or 0.0),
        reason=_clean_text(status_data.get("reason")),
    )


def _broker_open_order_cancellation_targets(orders: Any) -> list[dict[str, str]]:
    if not isinstance(orders, list):
        return []

    terminal_statuses = {"filled", "cancelled", "canceled", "expired", "rejected", "failed", "done", "closed"}
    targets: list[dict[str, str]] = []
    for value in orders:
        if not isinstance(value, dict):
            continue
        order_id = _extract_broker_order_id(value)
        if not order_id:
            continue
        status = _clean_text(value.get("status") or "open").lower()
        if status in terminal_statuses:
            continue
        targets.append(
            {
                "trade_id": "",
                "order_id": order_id,
                "source": "broker_open_orders",
                "broker_status": status or "open",
            }
        )
    return targets


def _dedupe_cancellation_targets(targets: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen_order_ids: set[str] = set()
    for target in targets:
        order_id = _clean_text(target.get("order_id"))
        if not order_id or order_id in seen_order_ids:
            continue
        seen_order_ids.add(order_id)
        deduped.append(target)
    return deduped


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


def _extract_broker_order_id(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("broker_order_id", "order_id", "id"):
            order_id = _clean_text(value.get(key))
            if order_id:
                return order_id
        return ""
    return _clean_text(value)


def _extract_client_order_id(value: Any) -> str:
    if isinstance(value, dict):
        return _clean_text(value.get("client_order_id"))
    return ""


def _position_has_oco_exit_proof(position: dict[str, Any]) -> bool:
    plan = _dict_or_empty(position.get("oco_exit_plan") or position.get("exit_plan"))
    plan_status = _clean_text(plan.get("status")).lower()
    if plan_status and plan_status not in {"active", "armed", "protected", "submitted"}:
        return False

    take_profit_order_id = (
        _extract_broker_order_id(plan.get("take_profit"))
        or _extract_broker_order_id(plan.get("take_profit_order"))
        or _clean_text(plan.get("take_profit_order_id"))
        or _clean_text(position.get("take_profit_order_id"))
    )
    stop_loss_order_id = (
        _extract_broker_order_id(plan.get("stop_loss"))
        or _extract_broker_order_id(plan.get("stop_loss_order"))
        or _clean_text(plan.get("stop_loss_order_id"))
        or _clean_text(position.get("stop_loss_order_id"))
    )
    return bool(take_profit_order_id and stop_loss_order_id)


def _position_has_metadata_only_oco(position: dict[str, Any]) -> bool:
    if _position_has_oco_exit_proof(position):
        return False
    if coerce_bool(position.get("oco_exit_protected"), default=False):
        return True

    plan = _dict_or_empty(position.get("oco_exit_plan") or position.get("exit_plan"))
    take_profit_client_id = (
        _extract_client_order_id(plan.get("take_profit"))
        or _extract_client_order_id(plan.get("take_profit_order"))
        or _clean_text(plan.get("take_profit_client_order_id"))
        or _clean_text(position.get("take_profit_client_order_id"))
    )
    stop_loss_client_id = (
        _extract_client_order_id(plan.get("stop_loss"))
        or _extract_client_order_id(plan.get("stop_loss_order"))
        or _clean_text(plan.get("stop_loss_client_order_id"))
        or _clean_text(position.get("stop_loss_client_order_id"))
    )
    return bool(take_profit_client_id or stop_loss_client_id)


def _summarize_position_oco_protection(positions: list[dict[str, Any]]) -> dict[str, Any]:
    live_positions = [position for position in positions if _is_live_open_position(position)]
    unprotected_ids = [
        _clean_text(position.get("id")) or _clean_text(position.get("_id"))
        for position in live_positions
        if not _position_has_oco_exit_proof(position)
    ]
    unprotected_ids = [position_id for position_id in unprotected_ids if position_id]
    metadata_only_ids = [
        _clean_text(position.get("id")) or _clean_text(position.get("_id"))
        for position in live_positions
        if _position_has_metadata_only_oco(position)
    ]
    metadata_only_ids = [position_id for position_id in metadata_only_ids if position_id]
    return {
        "position_oco_unprotected_count": len(unprotected_ids),
        "position_oco_unprotected_ids": unprotected_ids,
        "position_oco_metadata_only_count": len(metadata_only_ids),
        "position_oco_metadata_only_ids": metadata_only_ids,
    }


class OperatorSimulateExitRequest(BaseModel):
    position_id: Optional[str] = None
    sell_percentage: float = Field(default=50, ge=1, le=100)
    exit_price: float = Field(default=1.8, gt=0)


class OperatorTrailingStopRequest(BaseModel):
    position_id: Optional[str] = None
    current_price: float = Field(gt=0)
    sell_percentage: float = Field(default=100, ge=1, le=100)


class LiveArmRequest(BaseModel):
    duration_minutes: int = Field(default=60, ge=1, le=480)
    confirmation: str
    reason: str = ""


class ReadinessGateEvidenceRequest(BaseModel):
    status: str = Field(default="passed")
    summary: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)
    operator: str = "local_operator"


class PaperSessionSnapshotRequest(BaseModel):
    market_session: Optional[str] = None
    market_is_open: Optional[bool] = None
    note: str = ""


async def _record_readiness_gate_evidence(
    gate_key: str,
    request: ReadinessGateEvidenceRequest,
    *,
    default_summary: str = "",
    evidence_source: str = "manual",
) -> dict[str, Any]:
    return await record_gate_evidence(
        db,
        gate_key,
        request,
        default_summary=default_summary,
        evidence_source=evidence_source,
    )


async def _broker_client_connected(client: Any) -> bool:
    checker = getattr(client, "check_connection", None)
    if not callable(checker):
        return False
    result = checker()
    if inspect.isawaitable(result):
        result = await result
    return bool(result)


async def _refresh_active_broker_health(settings: dict[str, Any], active_broker: str) -> dict[str, Any]:
    from routes.health import update_bot_status

    broker_connected = False
    broker_check_error = ""
    broker_checked_at = datetime.now(timezone.utc).isoformat()
    broker_client = None
    try:
        broker_client = get_configured_broker_client(settings, active_broker)
        broker_connected = await _broker_client_connected(broker_client)
    except Exception as exc:  # pragma: no cover - exercised by integration failure paths
        broker_check_error = str(exc)
    finally:
        if broker_client is not None:
            result = close_broker_client(broker_client)
            if inspect.isawaitable(result):
                await result

    update_bot_status("active_broker", active_broker)
    update_bot_status("broker_connected", broker_connected)
    return {
        "broker_connected": broker_connected,
        "broker_checked_at": broker_checked_at,
        "broker_check_error": broker_check_error,
    }


def _now_id_fragment() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")


async def _partial_fill_drill_position(settings: dict[str, Any]) -> dict[str, Any]:
    positions = await db.get_positions() if hasattr(db, "get_positions") else []
    positions = positions if isinstance(positions, list) else []
    for position in positions:
        if not isinstance(position, dict):
            continue
        if _clean_text(position.get("status") or "open").lower() not in {"open", "partial"}:
            continue
        if _positive_int(position.get("remaining_quantity") or position.get("quantity")) >= 2:
            return position

    if not hasattr(db, "insert_position"):
        raise HTTPException(status_code=409, detail="Database cannot create a partial-fill drill position.")
    active_broker = _broker_id_text(settings.get("active_broker") or "alpaca")
    position_id = f"partial-fill-drill-position-{_now_id_fragment()}"
    position = {
        "id": position_id,
        "ticker": "SPY",
        "strike": 500.0,
        "option_type": "CALL",
        "expiration": "2026-06-26",
        "entry_price": 2.0,
        "current_price": 2.0,
        "original_quantity": 2,
        "remaining_quantity": 2,
        "realized_pnl": 0.0,
        "status": "open",
        "broker": active_broker,
        "simulated": True,
        "trade_ids": [],
    }
    await db.insert_position(position)
    return position


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
    status["alert_chain_live_blocking_attention_count"] = alert_chain_summary.get(
        "live_blocking_attention_count",
        alert_chain_summary.get("attention_count", 0),
    )
    status["alert_chain_live_blocking_attention_reasons"] = alert_chain_summary.get(
        "live_blocking_attention_reasons",
        alert_chain_summary.get("attention_reasons", []),
    )
    status.update(position_oco)
    status["readiness_gates"] = await readiness_gate_states_from_events(db)
    return evaluate_live_readiness(settings, runtime, status=status)


@router.get("/operator/events")
async def get_operator_events(limit: int = Query(default=100, ge=1, le=500)):
    """Return recent operator-visible events."""
    return await db.get_operator_events(limit)


@router.get("/operator/readiness-gates")
async def get_readiness_gates():
    """Return live-readiness gate definitions and latest recorded evidence state."""
    return {
        "definitions": required_readiness_gate_definitions(),
        "states": await readiness_gate_states_from_events(db),
    }


@router.post("/operator/readiness-gates/{gate_key}/evidence")
async def record_readiness_gate_evidence(gate_key: str, request: ReadinessGateEvidenceRequest):
    """Record operator/drill evidence for a specific live-readiness gate."""
    return await _record_readiness_gate_evidence(gate_key, request)


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
        exit_trigger="operator_sell",
    )
    event = await record_operator_event(
        db,
        "test_lab",
        "simulated_exit",
        f"Sold {result.get('sold_quantity', 0)} contract(s) from a test position.",
        details=result,
    )
    return {**result, "event_id": event["id"]}


@router.post("/operator/trailing-stop/evaluate")
async def evaluate_trailing_stop(request: OperatorTrailingStopRequest):
    """Evaluate one mark against a position trailing stop and sell when it triggers in simulation."""
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
            raise HTTPException(status_code=404, detail="No open position is available for trailing-stop evaluation.")
        position_id = first_open["id"]

    position = await db.get_position_by_id(position_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found.")

    settings = _dict_or_empty(await db.get_settings())
    decision = build_trailing_stop_decision(
        position,
        settings,
        current_price=request.current_price,
    )
    await db.update_position(
        position_id,
        {
            "$set": {
                "current_price": decision["current_price"],
                "highest_price": decision["highest_price"],
            }
        },
    )

    if decision["triggered"]:
        simulation_mode = coerce_bool(settings.get("simulation_mode"), default=True)
        simulated_position = coerce_bool(position.get("simulated"), default=False)
        if not simulation_mode and not simulated_position:
            event = await record_operator_event(
                db,
                "position",
                "trailing_stop_live_blocked",
                f"Trailing stop triggered for position {position_id}, but live auto-sell is not supported.",
                severity="warning",
                details={"decision": decision},
            )
            return {"decision": {**decision, "action": "blocked_live"}, "sell_result": None, "event_id": event["id"]}

        from routes import trading as trading_route

        sell_result = await trading_route.sell_position_from_operator(
            position_id,
            sell_percentage=request.sell_percentage,
            exit_price=request.current_price,
            exit_trigger="trailing_stop",
        )
        event = await record_operator_event(
            db,
            "position",
            "trailing_stop_triggered",
            f"Trailing stop sold position {position_id}.",
            severity="warning",
            details={"decision": decision, "sell_result": sell_result},
        )
        return {"decision": decision, "sell_result": sell_result, "event_id": event["id"]}

    event = await record_operator_event(
        db,
        "position",
        "trailing_stop_evaluated",
        f"Trailing stop evaluated for position {position_id}.",
        details={"decision": decision},
    )
    return {"decision": decision, "sell_result": None, "event_id": event["id"]}


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


@router.post("/operator/drills/reconnect")
async def run_reconnect_drill():
    """Verify the active broker can be closed and reconnected, then record readiness evidence."""
    settings = await db.get_settings()
    settings = settings if isinstance(settings, dict) else {}
    active_broker = _broker_id_text(settings.get("active_broker") or "ibkr")
    before_connected = False
    after_connected = False
    errors: list[str] = []

    first_client = None
    second_client = None
    try:
        first_client = get_configured_broker_client(settings, active_broker)
        before_connected = await _broker_client_connected(first_client)
    except Exception as exc:  # pragma: no cover - exercised in integration failure paths
        errors.append(f"initial connection failed: {exc}")
    finally:
        if first_client is not None:
            result = close_broker_client(first_client)
            if inspect.isawaitable(result):
                await result

    try:
        second_client = get_configured_broker_client(settings, active_broker)
        after_connected = await _broker_client_connected(second_client)
    except Exception as exc:  # pragma: no cover - exercised in integration failure paths
        errors.append(f"reconnect failed: {exc}")
    finally:
        if second_client is not None:
            result = close_broker_client(second_client)
            if inspect.isawaitable(result):
                await result

    status = "passed" if before_connected and after_connected and not errors else "failed"
    evidence = {
        "active_broker": active_broker,
        "before_connected": before_connected,
        "after_connected": after_connected,
        "errors": errors,
    }
    recorded = await _record_readiness_gate_evidence(
        "disconnect_reconnect_drill",
        ReadinessGateEvidenceRequest(
            status=status,
            summary=f"Broker reconnect drill {status}.",
            evidence=evidence,
            operator="operator_drill",
        ),
        evidence_source="drill",
    )
    return {
        **recorded,
        "active_broker": active_broker,
        "before_connected": before_connected,
        "after_connected": after_connected,
        "errors": errors,
    }


@router.post("/operator/drills/partial-fill")
async def run_partial_fill_drill():
    """Apply a synthetic broker partial-fill update through reconciliation and record readiness evidence."""
    settings = await db.get_settings()
    settings = settings if isinstance(settings, dict) else {}
    active_broker = _broker_id_text(settings.get("active_broker") or "alpaca")
    position = await _partial_fill_drill_position(settings)
    position_id = _clean_text(position.get("id") or position.get("_id"))
    if not position_id:
        raise HTTPException(status_code=409, detail="Partial-fill drill position has no id.")

    requested_quantity = max(2, _positive_int(position.get("remaining_quantity") or position.get("quantity")))
    drill_id = _now_id_fragment()
    trade_id = f"partial-fill-drill-trade-{drill_id}"
    order_id = f"partial-fill-drill-order-{drill_id}"
    if hasattr(db, "insert_trade"):
        await db.insert_trade(
            {
                "id": trade_id,
                "position_id": position_id,
                "ticker": _clean_text(position.get("ticker")) or "SPY",
                "strike": float(position.get("strike") or 0.0),
                "option_type": _clean_text(position.get("option_type")) or "CALL",
                "expiration": _clean_text(position.get("expiration")),
                "side": "SELL",
                "quantity": requested_quantity,
                "status": "pending",
                "order_id": order_id,
                "broker": active_broker,
                "simulated": True,
            }
        )

    result = await reconcile_order_update(
        db,
        OrderContext(
            trade_id=trade_id,
            order_id=order_id,
            side="SELL",
            ticker=_clean_text(position.get("ticker")) or "SPY",
            strike=float(position.get("strike") or 0.0),
            option_type=_clean_text(position.get("option_type")) or "CALL",
            expiration=_clean_text(position.get("expiration")),
            requested_quantity=requested_quantity,
            broker=active_broker,
            position_id=position_id,
            alert_price=float(position.get("entry_price") or 2.0),
            simulated=True,
        ),
        BrokerOrderUpdate(status="partial", filled_qty=1, avg_fill_price=float(position.get("current_price") or 2.4)),
    )

    status = "passed" if result.trade_status == "partial" and result.position_status == "partial" else "failed"
    evidence = {
        "active_broker": active_broker,
        "position_id": position_id,
        "trade_id": trade_id,
        "order_id": order_id,
        "broker_update": {"status": "partial", "filled_qty": 1},
        "reconciliation": {
            "trade_status": result.trade_status,
            "position_status": result.position_status,
            "position_id": result.position_id,
            "message": result.message,
        },
    }
    recorded = await _record_readiness_gate_evidence(
        "partial_fill_broker_behavior",
        ReadinessGateEvidenceRequest(
            status=status,
            summary=f"Partial-fill reconciliation drill {status}.",
            evidence=evidence,
            operator="operator_drill",
        ),
        evidence_source="drill",
    )
    return {
        **recorded,
        "active_broker": active_broker,
        "reconciliation": evidence["reconciliation"],
        "position_id": position_id,
        "trade_id": trade_id,
        "order_id": order_id,
    }


@router.post("/operator/monitoring/paper-session-snapshot")
async def record_paper_session_snapshot(request: PaperSessionSnapshotRequest = PaperSessionSnapshotRequest()):
    """Record a paper monitoring snapshot and promote session/transition gates when evidence is sufficient."""
    from routes.health import get_bot_status

    settings = await db.get_settings()
    settings = settings if isinstance(settings, dict) else {}
    status = dict(get_bot_status())
    market_session = _clean_text(request.market_session) or current_market_session()
    active_broker = _broker_id_text(settings.get("active_broker") or status.get("active_broker") or "alpaca")
    broker_health = _dict_or_empty(await _refresh_active_broker_health(settings, active_broker))
    snapshot_details = {
        "market_session": market_session,
        "market_is_open": request.market_is_open,
        "active_broker": active_broker,
        "broker_connected": status_flag(broker_health, "broker_connected"),
        "broker_checked_at": _clean_text(broker_health.get("broker_checked_at")),
        "broker_check_error": _clean_text(broker_health.get("broker_check_error")),
        "discord_connected": status_flag(status, "discord_connected"),
        "auto_trading_enabled": coerce_bool(settings.get("auto_trading_enabled"), default=True),
        "simulation_mode": coerce_bool(settings.get("simulation_mode"), default=True),
        "note": _clean_text(request.note),
    }

    previous_snapshots = await paper_session_snapshots(db)
    event = await record_operator_event(
        db,
        "readiness_monitor",
        "paper_session_snapshot",
        "Paper session snapshot recorded.",
        details=snapshot_details,
    )
    current_snapshot = {
        "timestamp": event.get("timestamp", ""),
        **snapshot_details,
    }
    snapshots = [current_snapshot, *previous_snapshots]
    session_summary = snapshot_counts_for_multi_session(snapshots)
    recorded_gate_keys: list[str] = []

    if snapshot_is_healthy(current_snapshot):
        recorded = await _record_readiness_gate_evidence(
            "paper_mode_burn_in",
            ReadinessGateEvidenceRequest(
                status="passed",
                summary="Paper-mode burn-in snapshot is healthy.",
                evidence={
                    "snapshot_event_id": event["id"],
                    "market_session": current_snapshot.get("market_session"),
                    "market_is_open": current_snapshot.get("market_is_open"),
                    "active_broker": current_snapshot.get("active_broker"),
                    "broker_connected": current_snapshot.get("broker_connected"),
                    "broker_checked_at": current_snapshot.get("broker_checked_at"),
                    "discord_connected": current_snapshot.get("discord_connected"),
                    "auto_trading_enabled": current_snapshot.get("auto_trading_enabled"),
                    "simulation_mode": current_snapshot.get("simulation_mode"),
                },
                operator="paper_session_monitor",
            ),
            evidence_source="monitor",
        )
        recorded_gate_keys.append(recorded["gate_key"])
        recorded = await _record_readiness_gate_evidence(
            "live_monitoring_evidence",
            ReadinessGateEvidenceRequest(
                status="passed",
                summary="Operator monitoring snapshot is healthy.",
                evidence={
                    "snapshot_event_id": event["id"],
                    "market_session": current_snapshot.get("market_session"),
                    "market_is_open": current_snapshot.get("market_is_open"),
                    "active_broker": current_snapshot.get("active_broker"),
                    "broker_connected": current_snapshot.get("broker_connected"),
                    "broker_checked_at": current_snapshot.get("broker_checked_at"),
                    "broker_check_error": current_snapshot.get("broker_check_error"),
                    "discord_connected": current_snapshot.get("discord_connected"),
                    "auto_trading_enabled": current_snapshot.get("auto_trading_enabled"),
                    "simulation_mode": current_snapshot.get("simulation_mode"),
                },
                operator="paper_session_monitor",
            ),
            evidence_source="monitor",
        )
        recorded_gate_keys.append(recorded["gate_key"])

    if session_summary["session_count"] >= 2:
        recorded = await _record_readiness_gate_evidence(
            "multi_session_paper_monitoring",
            ReadinessGateEvidenceRequest(
                status="passed",
                summary="Paper monitoring covered at least two market sessions.",
                evidence={
                    "session_count": session_summary["session_count"],
                    "sessions": session_summary["sessions"],
                },
                operator="paper_session_monitor",
            ),
            evidence_source="monitor",
        )
        recorded_gate_keys.append(recorded["gate_key"])

    previous_transition_snapshot = transition_snapshot(previous_snapshots, current_snapshot)
    if previous_transition_snapshot:
        recorded = await _record_readiness_gate_evidence(
            "market_transition_validation",
            ReadinessGateEvidenceRequest(
                status="passed",
                summary="Market open/closed transition was observed during paper monitoring.",
                evidence={
                    "from_timestamp": previous_transition_snapshot.get("timestamp"),
                    "to_timestamp": current_snapshot.get("timestamp"),
                    "from_market_is_open": previous_transition_snapshot.get("market_is_open"),
                    "to_market_is_open": current_snapshot.get("market_is_open"),
                    "from_market_session": previous_transition_snapshot.get("market_session"),
                    "to_market_session": current_snapshot.get("market_session"),
                    "from_broker_connected": previous_transition_snapshot.get("broker_connected"),
                    "to_broker_connected": current_snapshot.get("broker_connected"),
                    "from_discord_connected": previous_transition_snapshot.get("discord_connected"),
                    "to_discord_connected": current_snapshot.get("discord_connected"),
                    "from_auto_trading_enabled": previous_transition_snapshot.get("auto_trading_enabled"),
                    "to_auto_trading_enabled": current_snapshot.get("auto_trading_enabled"),
                    "from_simulation_mode": previous_transition_snapshot.get("simulation_mode"),
                    "to_simulation_mode": current_snapshot.get("simulation_mode"),
                    "from_broker_checked_at": previous_transition_snapshot.get("broker_checked_at"),
                    "to_broker_checked_at": current_snapshot.get("broker_checked_at"),
                },
                operator="paper_session_monitor",
            ),
            evidence_source="monitor",
        )
        recorded_gate_keys.append(recorded["gate_key"])

    return {
        "snapshot_event_id": event["id"],
        "snapshot": snapshot_details,
        "session_count": session_summary["session_count"],
        "sessions": session_summary["sessions"],
        "recorded_gate_keys": recorded_gate_keys,
    }


@router.post("/operator/panic-stop")
async def panic_stop():
    """Disable automated live trading and set runtime shutdown state."""
    from broker_capabilities import get_broker_capabilities, normalize_broker_id
    from order_execution import BrokerConfigurationError, close_broker_client, get_configured_broker_client
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
        pending_orders = []
        get_trades = getattr(db, "get_trades", None)
        if not callable(get_trades):
            warnings.append("No pending order registry is available; broker cancellations were not attempted.")
        else:
            trades = await get_trades(limit=1000)
            trades = trades if isinstance(trades, list) else []
            pending_orders.extend(_pending_live_broker_orders(trades, active_broker=active_broker))

        broker_client = None
        try:
            broker_client = get_configured_broker_client(
                settings,
                active_broker,
                require_cancel_order=True,
            )
            list_open_orders = getattr(broker_client, "list_open_orders", None)
            if callable(list_open_orders):
                broker_orders = list_open_orders()
                if inspect.isawaitable(broker_orders):
                    broker_orders = await broker_orders
                pending_orders.extend(_broker_open_order_cancellation_targets(broker_orders))
            else:
                warnings.append("Broker client does not expose open-order discovery; only local pending orders were considered.")

            pending_orders = _dedupe_cancellation_targets(pending_orders)
            if not pending_orders:
                warnings.append("No pending live broker orders were found locally or at the broker.")

            for pending_order in pending_orders:
                order_id = pending_order["order_id"]
                attempt = dict(pending_order)
                try:
                    result = broker_client.cancel_order(order_id)
                    if inspect.isawaitable(result):
                        result = await result
                    result = result if isinstance(result, dict) else {}
                    attempt.update(
                        {
                            "status": _clean_text(result.get("status")) or "cancel_requested",
                            "cancel_requested": coerce_bool(
                                result.get("cancel_requested"),
                                default=True,
                            ),
                        }
                    )
                except Exception as exc:  # pragma: no cover - exercised via integration failure paths
                    attempt.update(
                        {
                            "status": "cancel_failed",
                            "cancel_requested": False,
                            "error": str(exc),
                        }
                    )
                    warnings.append(f"Broker cancellation failed for order {order_id}: {exc}")
                cancellation_attempts.append(attempt)
        except BrokerConfigurationError as exc:
            warnings.append(f"Broker cancellation was not attempted: {exc}")
        finally:
            if broker_client is not None:
                await close_broker_client(broker_client)

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


@router.post("/operator/refresh-broker-orders")
async def refresh_broker_orders():
    """Refresh pending local broker orders from the active broker and reconcile terminal states."""
    settings = await db.get_settings()
    settings = settings if isinstance(settings, dict) else {}
    active_broker = _broker_id_text(settings.get("active_broker") or "ibkr")
    trades = await db.get_trades(limit=1000) if hasattr(db, "get_trades") else []
    trades = trades if isinstance(trades, list) else []
    pending_trades = _pending_live_broker_trades(trades, active_broker=active_broker)

    checked = []
    reconciled = []
    errors = []
    broker_client = None
    try:
        broker_client = get_configured_broker_client(
            settings,
            active_broker,
            require_order_status=True,
        )
        for trade in pending_trades:
            order_id = _pending_trade_order_id(trade)
            trade_id = _clean_text(trade.get("id") or trade.get("_id"))
            status_reader = getattr(broker_client, "get_order_status", None)
            if not callable(status_reader):
                errors.append({"trade_id": trade_id, "order_id": order_id, "error": "broker lacks order status"})
                continue
            status_data = status_reader(order_id)
            if inspect.isawaitable(status_data):
                status_data = await status_data
            status_data = status_data if isinstance(status_data, dict) else {"status": "unknown"}
            status = _clean_text(status_data.get("status") or "unknown").lower()
            row = {"trade_id": trade_id, "order_id": order_id, "status": status}
            checked.append(row)
            if status in {"filled", "partial", "rejected", "cancelled", "canceled", "expired", "unknown", "error", "unconfirmed"}:
                try:
                    result = await reconcile_order_update(
                        db,
                        _order_context_from_trade(trade, order_id=order_id),
                        _broker_update_from_status(status_data),
                        settings=settings,
                    )
                    reconciled.append({**row, "trade_status": result.trade_status, "message": result.message})
                except Exception as exc:
                    errors.append({"trade_id": trade_id, "order_id": order_id, "error": str(exc)})
    except BrokerConfigurationError as exc:
        errors.append({"error": str(exc), "broker": active_broker})
    finally:
        if broker_client is not None:
            result = close_broker_client(broker_client)
            if inspect.isawaitable(result):
                await result

    event = await record_operator_event(
        db,
        "reconciliation",
        "broker_order_refresh",
        "Refreshed pending local broker orders from the active broker.",
        severity="warning" if errors else "info",
        details={
            "active_broker": active_broker,
            "checked": checked,
            "reconciled": reconciled,
            "errors": errors,
        },
    )
    return {
        "active_broker": active_broker,
        "checked_count": len(checked),
        "reconciled_count": len(reconciled),
        "error_count": len(errors),
        "checked": checked,
        "reconciled": reconciled,
        "errors": errors,
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
