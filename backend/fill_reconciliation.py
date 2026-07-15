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

    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "order_id": self.order_id,
            "side": self.side,
            "ticker": self.ticker,
            "strike": self.strike,
            "option_type": self.option_type,
            "expiration": self.expiration,
            "requested_quantity": self.requested_quantity,
            "broker": self.broker,
            "position_id": self.position_id,
            "alert_id": self.alert_id,
            "alert_price": self.alert_price,
            "simulated": self.simulated,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "OrderContext":
        return cls(
            trade_id=str(value["trade_id"]),
            order_id=str(value["order_id"]),
            side=str(value["side"]).upper(),
            ticker=str(value["ticker"]).upper(),
            strike=float(value["strike"]),
            option_type=str(value["option_type"]).upper(),
            expiration=str(value["expiration"]),
            requested_quantity=int(value["requested_quantity"]),
            broker=str(value.get("broker") or ""),
            position_id=value.get("position_id"),
            alert_id=value.get("alert_id"),
            alert_price=value.get("alert_price"),
            simulated=bool(value.get("simulated", False)),
        )


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
    applied_quantity: int = 0
    applied_price: float = 0.0


async def reconcile_order_update(
    db,
    context: OrderContext,
    update: BrokerOrderUpdate,
) -> ReconciliationResult:
    """Apply cumulative broker fill truth to trade and position state.

    ``filled_qty`` and ``avg_fill_price`` are cumulative broker values. The
    function stores how much has already been applied and mutates positions only
    by the newly observed delta, making repeated polls and restart recovery
    idempotent.
    """
    status = _normalise_status(update.status)

    if status in {"rejected", "cancelled", "expired"}:
        reason = update.reason or status
        trade = await _get_trade(db, context.trade_id)
        applied_qty = _int_value((trade or {}).get("applied_filled_qty"))
        terminal_status = "partial" if applied_qty > 0 else "failed"
        await db.update_trade(
            context.trade_id,
            {
                "status": terminal_status,
                "error_message": reason,
                "broker_status": status,
                "reconciliation_context": context.to_dict(),
            },
        )
        await _update_alert_status(
            db,
            context,
            trade_executed=applied_qty > 0,
            trade_result=(
                f"partial then {status}: {reason}"
                if applied_qty > 0
                else f"failed: {reason}"
            ),
        )
        return ReconciliationResult(
            trade_status=terminal_status,
            message=reason,
        )

    if status in {"unknown", "error", "unconfirmed", "working_unconfirmed"}:
        reason = update.reason or "Broker order status temporarily unavailable"
        await db.update_trade(
            context.trade_id,
            {
                "status": "working_unconfirmed",
                "error_message": reason,
                "broker_status": status,
                "reconciliation_context": context.to_dict(),
            },
        )
        return ReconciliationResult(
            trade_status="working_unconfirmed",
            message=reason,
        )

    if status in {"partial", "filled"}:
        _validate_fill_truth(update, context)
        trade_status = "executed" if status == "filled" else "partial"
        return await _apply_cumulative_fill(
            db,
            context,
            update,
            trade_status=trade_status,
        )

    await db.update_trade(
        context.trade_id,
        {
            "status": "pending",
            "broker_status": status or "pending",
            "reconciliation_context": context.to_dict(),
        },
    )
    return ReconciliationResult(trade_status="pending", message=status or "pending")


async def _apply_cumulative_fill(
    db,
    context: OrderContext,
    update: BrokerOrderUpdate,
    *,
    trade_status: str,
) -> ReconciliationResult:
    cumulative_qty = int(update.filled_qty)
    cumulative_avg = float(update.avg_fill_price)
    trade = await _get_trade(db, context.trade_id) or {}
    applied_qty = _int_value(trade.get("applied_filled_qty"))
    applied_notional = _float_value(trade.get("applied_fill_notional"))

    if cumulative_qty < applied_qty:
        raise ValueError(
            f"Broker cumulative fill moved backwards for {context.order_id}: "
            f"{cumulative_qty} < {applied_qty}"
        )
    if cumulative_qty > context.requested_quantity:
        raise ValueError(
            f"Broker cumulative fill exceeds requested quantity for {context.order_id}: "
            f"{cumulative_qty} > {context.requested_quantity}"
        )

    delta_qty = cumulative_qty - applied_qty
    cumulative_notional = cumulative_qty * cumulative_avg
    delta_notional = cumulative_notional - applied_notional
    if delta_qty > 0 and delta_notional <= 0:
        raise ValueError("Fill reconciliation requires positive incremental notional")
    delta_price = delta_notional / delta_qty if delta_qty > 0 else 0.0
    executed_at = _now()

    base_trade_update = {
        "status": trade_status,
        "quantity": cumulative_qty,
        "order_id": context.order_id,
        "broker_status": _normalise_status(update.status),
        "applied_filled_qty": cumulative_qty,
        "applied_fill_notional": cumulative_notional,
        "avg_fill_price": cumulative_avg,
        "executed_at": executed_at,
        "error_message": "",
        "reconciliation_context": context.to_dict(),
    }

    if context.side.upper() == "BUY":
        base_trade_update["entry_price"] = cumulative_avg
        await db.update_trade(context.trade_id, base_trade_update)
        position_id, position_status = await _apply_entry_delta(
            db,
            context,
            delta_qty=delta_qty,
            delta_price=delta_price,
            cumulative_qty=cumulative_qty,
            cumulative_avg=cumulative_avg,
        )
    else:
        position_id, position_status, cumulative_pnl = await _apply_exit_delta(
            db,
            context,
            delta_qty=delta_qty,
            delta_price=delta_price,
        )
        base_trade_update.update(
            {
                "side": "SELL",
                "exit_price": cumulative_avg,
                "realized_pnl": cumulative_pnl,
            }
        )
        await db.update_trade(context.trade_id, base_trade_update)

    await _update_alert_status(
        db,
        context,
        trade_executed=cumulative_qty > 0,
        trade_result=_fill_trade_result(trade_status),
    )
    return ReconciliationResult(
        trade_status=trade_status,
        position_status=position_status,
        position_id=position_id,
        applied_quantity=delta_qty,
        applied_price=delta_price,
    )


async def _apply_entry_delta(
    db,
    context: OrderContext,
    *,
    delta_qty: int,
    delta_price: float,
    cumulative_qty: int,
    cumulative_avg: float,
) -> tuple[str, str]:
    position_id = context.position_id or f"position:{context.trade_id}"
    position = await db.get_position_by_id(position_id)

    if position is None:
        position = _entry_position(context, position_id, cumulative_qty, cumulative_avg)
        await db.insert_position(position)
        return position_id, position["status"]

    if delta_qty > 0:
        existing_qty = _int_value(
            position.get("remaining_quantity") or position.get("original_quantity")
        )
        existing_cost = _float_value(position.get("total_cost"))
        new_qty = existing_qty + delta_qty
        new_cost = existing_cost + (delta_qty * delta_price * 100)
        new_entry = new_cost / (new_qty * 100) if new_qty > 0 else cumulative_avg
        trade_ids = list(position.get("trade_ids") or [])
        if context.trade_id not in trade_ids:
            trade_ids.append(context.trade_id)
        await db.update_position(
            position_id,
            {
                "$set": {
                    "entry_price": new_entry,
                    "current_price": cumulative_avg,
                    "original_quantity": new_qty,
                    "remaining_quantity": new_qty,
                    "total_cost": new_cost,
                    "status": "open",
                    "trade_ids": trade_ids,
                    "highest_price": max(
                        _float_value(position.get("highest_price")),
                        cumulative_avg,
                    ),
                }
            },
        )
    return position_id, "open"


async def _apply_exit_delta(
    db,
    context: OrderContext,
    *,
    delta_qty: int,
    delta_price: float,
) -> tuple[str, str, float]:
    if not context.position_id:
        raise ValueError("SELL fill reconciliation requires position_id")

    position = await db.get_position_by_id(context.position_id)
    if not position:
        raise ValueError(f"Position not found for sell fill: {context.position_id}")

    remaining_before = _int_value(
        position.get("remaining_quantity") or position.get("quantity")
    )
    if delta_qty > remaining_before:
        raise ValueError(
            f"Sell fill delta exceeds remaining position for {context.position_id}: "
            f"{delta_qty} > {remaining_before}"
        )

    entry_price = _float_value(position.get("entry_price"))
    delta_pnl = (delta_price - entry_price) * delta_qty * 100
    previous_pnl = _float_value(position.get("realized_pnl"))
    new_remaining = remaining_before - delta_qty
    cumulative_pnl = previous_pnl + delta_pnl
    position_status = "closed" if new_remaining <= 0 else "partial"
    trade_ids = list(position.get("trade_ids") or [])
    if context.trade_id not in trade_ids:
        trade_ids.append(context.trade_id)

    set_update = {
        "remaining_quantity": new_remaining,
        "realized_pnl": cumulative_pnl,
        "current_price": delta_price if delta_qty > 0 else position.get("current_price"),
        "status": position_status,
        "trade_ids": trade_ids,
    }
    if new_remaining <= 0:
        set_update["closed_at"] = _now()
    await db.update_position(context.position_id, {"$set": set_update})
    return context.position_id, position_status, cumulative_pnl


def _entry_position(
    context: OrderContext,
    position_id: str,
    quantity: int,
    fill_price: float,
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


def _validate_fill_truth(update: BrokerOrderUpdate, context: OrderContext) -> None:
    if int(update.filled_qty) <= 0:
        raise ValueError(
            f"{update.status} broker update for {context.order_id} requires positive filled_qty"
        )
    if float(update.avg_fill_price) <= 0:
        raise ValueError(
            f"{update.status} broker update for {context.order_id} requires positive avg_fill_price"
        )


def _normalise_status(value: str) -> str:
    status = str(value or "").strip().lower()
    return {
        "partially_filled": "partial",
        "partially filled": "partial",
        "canceled": "cancelled",
        "pending_new": "pending",
        "new": "pending",
        "accepted": "pending",
        "submitted": "pending",
        "open": "pending",
    }.get(status, status)


async def _get_trade(db, trade_id: str) -> Optional[dict]:
    if hasattr(db, "get_trade_by_id"):
        return await db.get_trade_by_id(trade_id)
    if hasattr(db, "get_trades"):
        for trade in await db.get_trades(1000):
            if str(trade.get("id")) == str(trade_id):
                return trade
    return None


def _int_value(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_value(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


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
