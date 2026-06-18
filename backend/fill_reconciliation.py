from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional


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


async def reconcile_order_update(
    db,
    context: OrderContext,
    update: BrokerOrderUpdate,
) -> ReconciliationResult:
    """Apply broker fill truth to trade and position state."""
    status = str(update.status or "").lower()

    if status in {"rejected", "cancelled", "expired"}:
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
        return ReconciliationResult(trade_status="failed", message=reason)

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
        return await _apply_fill(db, context, update, trade_status="partial")

    if status == "filled" or (status == "partial" and update.filled_qty >= context.requested_quantity):
        return await _apply_fill(db, context, update, trade_status="executed")

    return ReconciliationResult(trade_status="pending", message=status or "pending")


async def _apply_fill(
    db,
    context: OrderContext,
    update: BrokerOrderUpdate,
    *,
    trade_status: str,
) -> ReconciliationResult:
    filled_qty = _filled_quantity(update, context)
    fill_price = _fill_price(update, context)
    executed_at = _now()

    if context.side.upper() == "BUY":
        await db.update_trade(
            context.trade_id,
            {
                "status": trade_status,
                "quantity": filled_qty,
                "entry_price": fill_price,
                "executed_at": executed_at,
                "order_id": context.order_id,
            },
        )
        position_id = _entry_position_id(context)
        existing_position = await _get_position_by_id(db, position_id)
        if existing_position:
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

        position = _entry_position(context, filled_qty, fill_price, position_id)
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
        },
    )

    position_status = "closed" if new_remaining <= 0 else "partial"
    set_update = {
        "remaining_quantity": new_remaining,
        "realized_pnl": float(position.get("realized_pnl") or 0.0) + realized_pnl,
        "current_price": fill_price,
        "status": position_status,
    }
    if new_remaining <= 0:
        set_update["closed_at"] = executed_at

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
    return context.position_id or f"position-{context.trade_id}"


async def _get_position_by_id(db, position_id: str) -> Optional[dict]:
    if not hasattr(db, "get_position_by_id"):
        return None
    return await db.get_position_by_id(position_id)


def _entry_position(
    context: OrderContext,
    quantity: int,
    fill_price: float,
    position_id: str,
) -> dict:
    return {
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
    }


def _filled_quantity(update: BrokerOrderUpdate, context: OrderContext) -> int:
    return max(1, int(update.filled_qty or context.requested_quantity))


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
    if not context.alert_id or not hasattr(db, "update_alert"):
        return
    await db.update_alert(
        context.alert_id,
        {
            "processed": True,
            "trade_executed": trade_executed,
            "trade_result": trade_result,
        },
    )


def _fill_trade_result(trade_status: str) -> str:
    return "partial" if trade_status == "partial" else "filled"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
