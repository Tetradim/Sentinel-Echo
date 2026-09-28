from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from order_execution import build_oco_exit_plan
from position_identity import contract_position_id


OrderSide = Literal["BUY", "SELL"]


@dataclass(frozen=True)
class OrderContext:
    trade_id: str
    order_id: str
    side: OrderSide
    ticker: str
    strike: float
    option_type: str
    expiration: str
    requested_quantity: int
    broker: str = ""
    position_id: Optional[str] = None
    alert_id: Optional[str] = None
    alert_price: Optional[float] = None
    simulated: bool = False
    sell_percentage: Optional[float] = None
    exit_trigger: Optional[str] = None
    exit_allocation_target: Optional[str] = None
    target_remaining_quantity: Optional[int] = None
    entry_risk_profile: str = "normal"
    entry_exit_profile: str = "standard"
    max_loss_budget: Optional[float] = None
    estimated_stop_loss_percent: Optional[float] = None
    update_alert_status: bool = True


@dataclass(frozen=True)
class BrokerOrderUpdate:
    status: str
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class ReconciliationResult:
    trade_status: str
    position_status: Optional[str] = None
    position_id: Optional[str] = None
    message: str = ""


def trade_owns_alert_status(trade: dict[str, Any]) -> bool:
    explicit = trade.get("alert_status_owned")
    if explicit is not None:
        return bool(explicit)
    side = str(trade.get("side") or "").upper()
    exit_trigger = str(trade.get("exit_trigger") or "").strip().lower()
    analyst_triggers = {"sell_alert", "trim_alert", "close_alert", "discord_sell_alert"}
    return not (side == "SELL" and exit_trigger and exit_trigger not in analyst_triggers)


async def reconcile_order_update(
    db,
    context: OrderContext,
    update: BrokerOrderUpdate,
    settings: dict[str, Any] | None = None,
) -> ReconciliationResult:
    """Apply broker fill truth to trade and position state."""
    status = str(update.status or "").lower()

    if status in {"rejected", "cancelled", "canceled", "expired"} and update.filled_qty > 0:
        result = await _apply_fill(db, context, update, trade_status="partial", settings=settings)
        if context.side.upper() == "SELL" and context.position_id:
            await _clear_exit_reservation(db, context.position_id)
        return result

    if status in {"rejected", "cancelled", "canceled", "expired"}:
        reason = update.reason or status
        await db.update_trade(
            context.trade_id,
            {
                "status": "failed",
                "error_message": reason,
            },
        )
        await _update_alert_status(
            db,
            context,
            trade_executed=False,
            trade_result=f"failed: {reason}",
        )
        if context.side.upper() == "SELL" and context.position_id:
            await _clear_exit_reservation(db, context.position_id)
        return ReconciliationResult(trade_status="failed", message=reason)

    if status == "pending_broker":
        reason = update.reason or "Order remains active at broker after confirmation window"
        await db.update_trade(
            context.trade_id,
            {
                "status": "pending_broker",
                "quantity": context.requested_quantity,
                "error_message": reason,
            },
        )
        return ReconciliationResult(trade_status="pending_broker", message=reason)

    if status in {"unknown", "error", "unconfirmed"}:
        reason = update.reason or "Fill unconfirmed"
        await db.update_trade(
            context.trade_id,
            {
                "status": "unconfirmed",
                "quantity": context.requested_quantity,
                "error_message": reason,
            },
        )
        await _update_alert_status(
            db,
            context,
            trade_executed=False,
            trade_result=f"unconfirmed: {reason}",
        )
        return ReconciliationResult(trade_status="unconfirmed", message=reason)

    if status == "partial" and update.filled_qty > 0:
        return await _apply_fill(db, context, update, trade_status="partial", settings=settings)

    if status == "filled" or (status == "partial" and update.filled_qty >= context.requested_quantity):
        return await _apply_fill(db, context, update, trade_status="executed", settings=settings)

    return ReconciliationResult(trade_status="pending", message=status or "pending")


async def _apply_fill(
    db,
    context: OrderContext,
    update: BrokerOrderUpdate,
    *,
    trade_status: str,
    settings: dict[str, Any] | None = None,
) -> ReconciliationResult:
    filled_qty = _filled_quantity(update, context)
    fill_price = _fill_price(update, context)
    executed_at = _now()

    if context.side.upper() == "BUY":
        await db.update_trade(
            context.trade_id,
            {
                "status": trade_status,
                "side": "BUY",
                "quantity": filled_qty,
                "entry_price": fill_price,
                "executed_at": executed_at,
                "order_id": context.order_id,
                "error_message": "",
            },
        )
        position_id = _entry_position_id(context)
        existing_position = await _get_position_by_id(db, position_id)
        if existing_position:
            if context.trade_id not in (existing_position.get("trade_ids") or []):
                if str(existing_position.get("status") or "").strip().lower() == "closed":
                    await _reopen_closed_position(
                        db,
                        position_id,
                        context,
                        filled_qty,
                        fill_price,
                        settings=settings,
                    )
                    await _update_alert_status(
                        db,
                        context,
                        trade_executed=True,
                        trade_result=_fill_trade_result(trade_status),
                    )
                    return ReconciliationResult(
                        trade_status=trade_status,
                        position_status="open",
                        position_id=position_id,
                    )
                if _is_unlinked_broker_reconciled_position(existing_position):
                    position_status = await _attach_trade_to_broker_reconciled_position(
                        db,
                        position_id,
                        existing_position,
                        context,
                        filled_qty,
                        fill_price,
                    )
                    await _update_alert_status(
                        db,
                        context,
                        trade_executed=True,
                        trade_result=_fill_trade_result(trade_status),
                    )
                    return ReconciliationResult(
                        trade_status=trade_status,
                        position_status=position_status,
                        position_id=position_id,
                    )
                position_status = await _add_to_existing_position(
                    db,
                    position_id,
                    existing_position,
                    context.trade_id,
                    filled_qty,
                    fill_price,
                )
                await _update_alert_status(
                    db,
                    context,
                    trade_executed=True,
                    trade_result=_fill_trade_result(trade_status),
                )
                return ReconciliationResult(
                    trade_status=trade_status,
                    position_status=position_status,
                    position_id=position_id,
                )
            await _update_alert_status(
                db,
                context,
                trade_executed=True,
                trade_result=_fill_trade_result(trade_status),
            )
            return ReconciliationResult(
                trade_status=trade_status,
                position_status=existing_position.get("status"),
                position_id=position_id,
                message="already reconciled",
            )

        position = _entry_position(context, filled_qty, fill_price, position_id, settings=settings)
        position_id = await db.insert_position(position)
        await _update_alert_status(
            db,
            context,
            trade_executed=True,
            trade_result=_fill_trade_result(trade_status),
        )
        return ReconciliationResult(
            trade_status=trade_status,
            position_status=position["status"],
            position_id=position_id,
        )

    if not context.position_id:
        raise ValueError("SELL fill reconciliation requires position_id")

    position = await db.get_position_by_id(context.position_id)
    if not position:
        raise ValueError(f"Position not found for sell fill: {context.position_id}")

    if context.trade_id in (position.get("trade_ids") or []):
        if trade_status == "executed" and (
            bool(position.get("exit_order_pending")) or position.get("exit_order_id")
        ):
            await _clear_exit_reservation(db, context.position_id)
        await _update_alert_status(
            db,
            context,
            trade_executed=True,
            trade_result=_fill_trade_result(trade_status),
        )
        return ReconciliationResult(
            trade_status=trade_status,
            position_status=position.get("status"),
            position_id=context.position_id,
            message="already reconciled",
        )

    remaining_before = int(position.get("remaining_quantity") or position.get("quantity") or 0)
    exit_qty = min(filled_qty, remaining_before)
    new_remaining = max(0, remaining_before - exit_qty)
    entry_price = float(position.get("entry_price") or 0.0)
    realized_pnl = (fill_price - entry_price) * exit_qty * 100

    await db.update_trade(
        context.trade_id,
        {
            "status": trade_status,
            "side": "SELL",
            "quantity": exit_qty,
            "exit_price": fill_price,
            "realized_pnl": realized_pnl,
            "executed_at": executed_at,
            "order_id": context.order_id,
            "error_message": "",
        },
    )

    position_status = "closed" if new_remaining <= 0 else "partial"
    set_update = {
        "remaining_quantity": new_remaining,
        "realized_pnl": float(position.get("realized_pnl") or 0.0) + realized_pnl,
        "current_price": fill_price,
        "status": position_status,
    }
    set_update.update(
        _runner_allocation_after_sell(
            position,
            exit_qty=exit_qty,
            new_remaining=new_remaining,
            allocation_target=(
                context.exit_allocation_target
                or position.get("exit_target_allocation_target")
                or "entire_position"
            ),
        )
    )
    if trade_status == "executed":
        set_update.update(
            {
                "exit_order_pending": False,
                "exit_order_id": None,
                "exit_reservation_token": None,
            }
        )
        target_remaining = _optional_non_negative_int(
            position.get("exit_target_remaining_quantity")
        )
        if target_remaining is not None and new_remaining <= target_remaining:
            set_update.update(
                {
                    "exit_target_remaining_quantity": None,
                    "exit_target_trigger": None,
                    "exit_target_allocation_target": None,
                    "exit_target_updated_at": None,
                }
            )
    if trade_status == "executed" and context.exit_trigger == "take_profit":
        set_update["take_profit_stage_completed"] = True
        set_update["take_profit_stage_completed_at"] = executed_at
    if trade_status == "executed" and context.exit_trigger == "profit_stage_1":
        set_update["profit_stage_1_completed"] = True
        set_update["profit_stage_1_completed_at"] = executed_at
        set_update["profit_floor_armed"] = True
        set_update["profit_floor_price"] = round(entry_price + 0.01, 2)
        set_update["profit_floor_armed_at"] = executed_at
    if trade_status == "executed" and context.exit_trigger == "profit_stage_2":
        set_update["profit_stage_2_completed"] = True
        set_update["profit_stage_2_completed_at"] = executed_at
    if trade_status == "executed" and context.exit_trigger in {"reversal_warning", "reversal_reduce"}:
        set_update["reversal_warning_completed"] = True
        set_update["reversal_warning_completed_at"] = executed_at
        set_update["reversal_reduce_completed"] = True
        set_update["reversal_reduce_completed_at"] = executed_at
    if trade_status == "executed" and str(context.exit_trigger or "").startswith("loss_ladder_"):
        try:
            completed_step = max(0, int(str(context.exit_trigger).rsplit("_", 1)[1]) - 1)
        except (TypeError, ValueError):
            completed_step = None
        if completed_step is not None:
            completed_steps = {
                int(value)
                for value in (position.get("coordinated_loss_ladder_completed_steps") or [])
                if str(value).isdigit()
            }
            completed_steps.add(completed_step)
            set_update["coordinated_loss_ladder_completed_steps"] = sorted(completed_steps)
            set_update["coordinated_loss_ladder_pending_step"] = None
    if new_remaining <= 0:
        set_update["closed_at"] = executed_at
        set_update["unrealized_pnl"] = 0.0

    await db.update_position(
        context.position_id,
        {
            "$set": set_update,
            "$push": {"trade_ids": context.trade_id},
        },
    )
    await _update_alert_status(
        db,
        context,
        trade_executed=True,
        trade_result=_fill_trade_result(trade_status),
    )
    return ReconciliationResult(
        trade_status=trade_status,
        position_status=position_status,
        position_id=context.position_id,
    )


def _entry_position_id(context: OrderContext) -> str:
    if context.position_id:
        return context.position_id
    return contract_position_id(
        context.broker,
        context.ticker,
        context.strike,
        context.option_type,
        context.expiration,
    )


async def _get_position_by_id(db, position_id: str) -> Optional[dict]:
    if not hasattr(db, "get_position_by_id"):
        return None
    return await db.get_position_by_id(position_id)


def _entry_position(
    context: OrderContext,
    quantity: int,
    fill_price: float,
    position_id: str,
    *,
    settings: dict[str, Any] | None = None,
) -> dict:
    position = {
        "id": position_id,
        "alert_id": context.alert_id,
        "ticker": context.ticker,
        "strike": context.strike,
        "option_type": context.option_type,
        "expiration": context.expiration,
        "entry_price": fill_price,
        "current_price": fill_price,
        "original_quantity": quantity,
        "remaining_quantity": quantity,
        "total_cost": fill_price * quantity * 100,
        "broker": context.broker,
        "status": "open",
        "opened_at": _now(),
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
        "simulated": context.simulated,
        "trade_ids": [context.trade_id],
        "highest_price": fill_price,
        "highest_executable_bid": fill_price,
        "entry_risk_profile": context.entry_risk_profile or "normal",
        "entry_exit_profile": context.entry_exit_profile or "standard",
        "max_loss_budget": context.max_loss_budget,
        "estimated_stop_loss_percent": context.estimated_stop_loss_percent,
    }
    position.update(fresh_position_lifecycle_state(fill_price))
    oco_exit_plan = _build_fill_oco_exit_plan(settings, context, quantity, fill_price, position_id)
    if oco_exit_plan:
        position["oco_exit_plan"] = oco_exit_plan
        position["oco_exit_status"] = "metadata_only"
        position["oco_exit_protected"] = False
    return position


def fresh_position_lifecycle_state(fill_price: float) -> dict[str, Any]:
    """Return a complete clean lifecycle for a newly opened contract."""
    return {
        "initial_entry_price": fill_price,
        "average_down_count": 0,
        "closed_at": None,
        "exit_trigger": None,
        "reconciled_from_broker_only": False,
        "broker_reconciled_entry_attached": False,
        "reversal_state": "",
        "reversal_conflict_count": 0,
        "reversal_alignment_score": 0.0,
        "reversal_premium_drawdown_percent": 0.0,
        "reversal_warning_completed": False,
        "reversal_warning_completed_at": None,
        "max_favorable_excursion_percent": 0.0,
        "max_adverse_excursion_percent": 0.0,
        "counterfactual_stop_hits": {},
        "counterfactual_trailing_hits": {},
        "premium_mark_history": [],
        "adaptive_trailing_percent": None,
        "profit_stage_1_completed": False,
        "profit_stage_1_completed_at": None,
        "profit_stage_2_completed": False,
        "profit_stage_2_completed_at": None,
        "profit_floor_armed": False,
        "profit_floor_price": None,
        "profit_floor_armed_at": None,
        "coordinated_trailing_armed": False,
        "coordinated_trailing_floor": None,
        "coordinated_trailing_distance": None,
        "coordinated_trailing_step": 0,
        "coordinated_effective_trailing_percent": None,
        "coordinated_premium_volatility_percent": 0.0,
        "coordinated_break_even_armed": False,
        "coordinated_break_even_floor": None,
        "coordinated_break_even_confirmation_count": 0,
        "coordinated_break_even_last_quote_observed_at": None,
        "coordinated_break_even_last_confirmation_at": None,
        "coordinated_break_even_runner_reserved": False,
        "coordinated_break_even_runner_high": None,
        "coordinated_stop_confirmation_count": 0,
        "coordinated_stop_last_quote_observed_at": None,
        "coordinated_stop_last_confirmation_at": None,
        "coordinated_loss_ladder_completed_steps": [],
        "coordinated_loss_ladder_pending_step": None,
        "coordinated_loss_ladder_confirmation_count": 0,
        "core_runner_allocation_initialized": False,
        "core_runner_original_quantity": None,
        "core_runner_candidate_quantity": 0,
        "core_runner_dedicated_quantity": 0,
        "core_runner_core_quantity": 0,
        "core_runner_activated": False,
        "core_runner_activated_at": None,
        "core_runner_activation_mfe_percent": None,
        "core_runner_activation_high": None,
        "core_runner_mfe_percent": 0.0,
        "core_runner_highest_executable_bid": None,
        "core_runner_trailing_armed": False,
        "core_runner_trailing_tier_mfe_percent": None,
        "core_runner_trailing_percent": None,
        "core_runner_trailing_distance": None,
        "core_runner_trailing_floor": None,
        "core_runner_trailing_confirmation_count": 0,
        "core_runner_trailing_last_quote_observed_at": None,
        "core_runner_trailing_last_confirmation_at": None,
        "core_runner_catastrophic_confirmation_count": 0,
        "core_runner_catastrophic_last_quote_observed_at": None,
        "core_runner_catastrophic_last_confirmation_at": None,
        "core_runner_suppressed_trigger": None,
        "exit_order_pending": False,
        "exit_order_id": None,
        "exit_reservation_token": None,
        "exit_reservation_trigger": None,
        "exit_reservation_created_at": None,
        "exit_target_remaining_quantity": None,
        "exit_target_trigger": None,
        "exit_target_allocation_target": None,
        "exit_target_updated_at": None,
        "oco_exit_plan": {},
        "oco_exit_status": "",
        "oco_exit_protected": False,
    }


def _runner_allocation_after_sell(
    position: dict[str, Any],
    *,
    exit_qty: int,
    new_remaining: int,
    allocation_target: Any,
) -> dict[str, Any]:
    runner_keys_present = any(
        key in position
        for key in (
            "core_runner_candidate_quantity",
            "core_runner_dedicated_quantity",
            "core_runner_core_quantity",
            "core_runner_activated",
        )
    )
    if not runner_keys_present:
        return {}

    candidate = max(0, int(position.get("core_runner_candidate_quantity") or 0))
    dedicated = max(0, int(position.get("core_runner_dedicated_quantity") or 0))
    activated = bool(position.get("core_runner_activated"))
    target = str(allocation_target or "entire_position").strip().lower()

    if target == "runners_only":
        dedicated = max(0, dedicated - exit_qty)
        candidate = max(0, candidate - exit_qty)
    elif target in {"core_then_runners", "entire_position"}:
        protected_before = dedicated if activated else candidate
        remaining_before = new_remaining + exit_qty
        core_before = max(0, remaining_before - protected_before)
        runner_consumed = max(0, exit_qty - core_before)
        dedicated = max(0, dedicated - runner_consumed)
        candidate = max(0, candidate - runner_consumed)

    candidate = min(candidate, new_remaining)
    dedicated = min(dedicated, candidate, new_remaining)
    protected = dedicated if activated else candidate
    return {
        "core_runner_candidate_quantity": candidate,
        "core_runner_dedicated_quantity": dedicated,
        "core_runner_core_quantity": max(0, new_remaining - protected),
    }


def _build_fill_oco_exit_plan(
    settings: dict[str, Any] | None,
    context: OrderContext,
    quantity: int,
    fill_price: float,
    position_id: str,
) -> dict[str, Any]:
    if not isinstance(settings, dict):
        return {}
    return build_oco_exit_plan(
        settings,
        alert_id=context.alert_id or context.trade_id,
        position_id=position_id,
        entry_price=fill_price,
        quantity=quantity,
    )


async def _add_to_existing_position(
    db,
    position_id: str,
    position: dict,
    trade_id: str,
    quantity: int,
    fill_price: float,
) -> str:
    remaining_before = max(0, int(position.get("remaining_quantity") or position.get("quantity") or 0))
    original_before = max(remaining_before, int(position.get("original_quantity") or remaining_before))
    new_remaining = remaining_before + quantity
    new_original = original_before + quantity
    current_basis = float(position.get("entry_price") or 0.0) * remaining_before * 100
    added_cost = fill_price * quantity * 100
    new_total_cost = current_basis + added_cost
    new_entry_price = new_total_cost / (new_remaining * 100)
    current_price = fill_price
    highest_price = max(float(position.get("highest_price") or 0.0), current_price)
    initial_entry_price = position.get("initial_entry_price") or position.get("entry_price")

    await db.update_position(
        position_id,
        {
            "$set": {
                "entry_price": new_entry_price,
                "current_price": current_price,
                "original_quantity": new_original,
                "remaining_quantity": new_remaining,
                "total_cost": round(new_total_cost, 2),
                "average_down_count": int(position.get("average_down_count") or 0) + 1,
                "initial_entry_price": initial_entry_price,
                "highest_price": highest_price,
                "status": "open",
            },
            "$push": {"trade_ids": trade_id},
        },
    )
    return "open"


async def _reopen_closed_position(
    db,
    position_id: str,
    context: OrderContext,
    quantity: int,
    fill_price: float,
    *,
    settings: dict[str, Any] | None = None,
) -> None:
    reopened = _entry_position(context, quantity, fill_price, position_id, settings=settings)
    reopened["highest_executable_bid"] = fill_price
    reopened.setdefault("oco_exit_plan", {})
    reopened.setdefault("oco_exit_status", "")
    reopened.setdefault("oco_exit_protected", False)
    await db.update_position(position_id, {"$set": reopened})


def _is_unlinked_broker_reconciled_position(position: dict) -> bool:
    return bool(position.get("reconciled_from_broker_only")) and not (position.get("trade_ids") or [])


async def _attach_trade_to_broker_reconciled_position(
    db,
    position_id: str,
    position: dict,
    context: OrderContext,
    quantity: int,
    fill_price: float,
) -> str:
    broker_quantity = max(0, int(position.get("remaining_quantity") or position.get("quantity") or 0))
    reconciled_quantity = broker_quantity if broker_quantity > 0 else quantity
    lifecycle = fresh_position_lifecycle_state(fill_price)
    lifecycle.update(
        {
            "alert_id": context.alert_id,
            "entry_price": fill_price,
            "current_price": fill_price,
            "original_quantity": reconciled_quantity,
            "remaining_quantity": reconciled_quantity,
            "total_cost": round(fill_price * reconciled_quantity * 100, 2),
            "highest_price": fill_price,
            "highest_executable_bid": fill_price,
            "opened_at": _now(),
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "entry_risk_profile": context.entry_risk_profile or "normal",
            "entry_exit_profile": context.entry_exit_profile or "standard",
            "max_loss_budget": context.max_loss_budget,
            "estimated_stop_loss_percent": context.estimated_stop_loss_percent,
            "status": "open",
            "broker_reconciled_entry_attached": True,
        }
    )
    await db.update_position(
        position_id,
        {
            "$set": lifecycle,
            "$push": {"trade_ids": context.trade_id},
        },
    )
    return "open"


def _filled_quantity(update: BrokerOrderUpdate, context: OrderContext) -> int:
    return max(1, int(update.filled_qty or context.requested_quantity))


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return None


def _fill_price(update: BrokerOrderUpdate, context: OrderContext) -> float:
    price = float(update.avg_fill_price or context.alert_price or 0.0)
    if price <= 0:
        raise ValueError("Fill reconciliation requires a positive fill price")
    return price


async def _update_alert_status(
    db,
    context: OrderContext,
    *,
    trade_executed: bool,
    trade_result: str,
) -> None:
    if not context.update_alert_status or not context.alert_id or not hasattr(db, "update_alert"):
        return
    updates = {
        "processed": True,
        "trade_executed": trade_executed,
        "trade_result": trade_result,
    }
    if context.exit_trigger:
        updates["exit_trigger"] = context.exit_trigger
    if context.sell_percentage is not None:
        updates["sell_percentage"] = context.sell_percentage
    await db.update_alert(context.alert_id, updates)


def _fill_trade_result(trade_status: str) -> str:
    return "partial" if trade_status == "partial" else "filled"


async def _clear_exit_reservation(db, position_id: str) -> None:
    if not hasattr(db, "update_position"):
        return
    await db.update_position(
        position_id,
        {
            "$set": {
                "exit_order_pending": False,
                "exit_order_id": None,
                "exit_reservation_token": None,
            }
        },
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
