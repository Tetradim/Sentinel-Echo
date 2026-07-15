"""Broker-authoritative cumulative fill reconciliation.

This module contains the production reconciler used by the fill monitor. Broker
fill quantities and prices are cumulative; only newly observed deltas are
applied to positions and trade P&L.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fill_reconciliation import (
    BrokerOrderUpdate,
    OrderContext,
    ReconciliationResult,
)


async def reconcile_order_update(
    db,
    context: OrderContext,
    update: BrokerOrderUpdate,
) -> ReconciliationResult:
    status = _normalise_status(update.status)
    trade = await _get_trade(db, context.trade_id) or {}
    applied_qty = _int(trade.get("applied_filled_qty"))

    if status in {"rejected", "cancelled", "expired"}:
        reason = update.reason or status
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
        await _update_alert(
            db,
            context,
            trade_executed=applied_qty > 0,
            result=(
                f"partial then {status}: {reason}"
                if applied_qty > 0
                else f"failed: {reason}"
            ),
        )
        return ReconciliationResult(trade_status=terminal_status, message=reason)

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

    if status not in {"partial", "filled"}:
        await db.update_trade(
            context.trade_id,
            {
                "status": "pending",
                "broker_status": status or "pending",
                "reconciliation_context": context.to_dict(),
            },
        )
        return ReconciliationResult(trade_status="pending", message=status or "pending")

    cumulative_qty = _int(update.filled_qty)
    cumulative_avg = _float(update.avg_fill_price)
    _validate_fill(status, cumulative_qty, cumulative_avg, context)
    if status == "filled" and cumulative_qty != context.requested_quantity:
        raise ValueError(
            f"Filled broker update for {context.order_id} is inconsistent: "
            f"filled {cumulative_qty}, requested {context.requested_quantity}"
        )

    previous_qty = _int(trade.get("applied_filled_qty"))
    previous_notional = _float(trade.get("applied_fill_notional"))
    if cumulative_qty < previous_qty:
        raise ValueError(
            f"Broker cumulative fill moved backwards for {context.order_id}: "
            f"{cumulative_qty} < {previous_qty}"
        )
    if cumulative_qty > context.requested_quantity:
        raise ValueError(
            f"Broker cumulative fill exceeds requested quantity for {context.order_id}: "
            f"{cumulative_qty} > {context.requested_quantity}"
        )

    cumulative_notional = cumulative_qty * cumulative_avg
    delta_qty = cumulative_qty - previous_qty
    delta_notional = cumulative_notional - previous_notional
    if delta_qty > 0 and delta_notional <= 0:
        raise ValueError("Fill reconciliation requires positive incremental notional")
    delta_price = delta_notional / delta_qty if delta_qty > 0 else 0.0
    trade_status = "executed" if status == "filled" else "partial"

    common = {
        "status": trade_status,
        "quantity": cumulative_qty,
        "order_id": context.order_id,
        "broker_status": status,
        "applied_filled_qty": cumulative_qty,
        "applied_fill_notional": cumulative_notional,
        "avg_fill_price": cumulative_avg,
        "executed_at": _now(),
        "error_message": "",
        "reconciliation_context": context.to_dict(),
    }

    if context.side.upper() == "BUY":
        position_id, position_status = await _apply_buy(
            db,
            context,
            delta_qty=delta_qty,
            delta_price=delta_price,
            cumulative_qty=cumulative_qty,
            cumulative_avg=cumulative_avg,
        )
        await db.update_trade(
            context.trade_id,
            {**common, "entry_price": cumulative_avg},
        )
    else:
        position_id, position_status, delta_pnl = await _apply_sell(
            db,
            context,
            delta_qty=delta_qty,
            delta_price=delta_price,
        )
        prior_trade_pnl = _float(trade.get("realized_pnl"))
        order_pnl = prior_trade_pnl + delta_pnl
        await db.update_trade(
            context.trade_id,
            {
                **common,
                "side": "SELL",
                "exit_price": cumulative_avg,
                "realized_pnl": order_pnl,
            },
        )

    await _update_alert(
        db,
        context,
        trade_executed=cumulative_qty > 0,
        result="filled" if trade_status == "executed" else "partial",
    )
    return ReconciliationResult(
        trade_status=trade_status,
        position_status=position_status,
        position_id=position_id,
        applied_quantity=delta_qty,
        applied_price=delta_price,
    )


async def _apply_buy(
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
        position = {
            "id": position_id,
            "alert_id": context.alert_id,
            "ticker": context.ticker,
            "strike": context.strike,
            "option_type": context.option_type,
            "expiration": context.expiration,
            "entry_price": cumulative_avg,
            "current_price": cumulative_avg,
            "original_quantity": cumulative_qty,
            "remaining_quantity": cumulative_qty,
            "total_cost": cumulative_avg * cumulative_qty * 100,
            "broker": context.broker,
            "status": "open",
            "opened_at": _now(),
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "simulated": context.simulated,
            "trade_ids": [context.trade_id],
            "highest_price": cumulative_avg,
        }
        await db.insert_position(position)
        return position_id, "open"

    if delta_qty <= 0:
        return position_id, str(position.get("status") or "open")

    existing_qty = _int(
        position.get("remaining_quantity") or position.get("original_quantity")
    )
    existing_cost = _float(position.get("total_cost"))
    new_qty = existing_qty + delta_qty
    new_cost = existing_cost + (delta_qty * delta_price * 100)
    new_entry = new_cost / (new_qty * 100)
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
                "highest_price": max(_float(position.get("highest_price")), cumulative_avg),
            }
        },
    )
    return position_id, "open"


async def _apply_sell(
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

    remaining_before = _int(
        position.get("remaining_quantity") or position.get("quantity")
    )
    if delta_qty > remaining_before:
        raise ValueError(
            f"Sell fill delta exceeds remaining position for {context.position_id}: "
            f"{delta_qty} > {remaining_before}"
        )

    entry_price = _float(position.get("entry_price"))
    delta_pnl = (delta_price - entry_price) * delta_qty * 100
    position_pnl = _float(position.get("realized_pnl")) + delta_pnl
    remaining = remaining_before - delta_qty
    position_status = "closed" if remaining <= 0 else "partial"
    trade_ids = list(position.get("trade_ids") or [])
    if context.trade_id not in trade_ids:
        trade_ids.append(context.trade_id)
    update = {
        "remaining_quantity": remaining,
        "realized_pnl": position_pnl,
        "status": position_status,
        "trade_ids": trade_ids,
    }
    if delta_qty > 0:
        update["current_price"] = delta_price
    if remaining <= 0:
        update["closed_at"] = _now()
    await db.update_position(context.position_id, {"$set": update})
    return context.position_id, position_status, delta_pnl


def _validate_fill(
    status: str,
    quantity: int,
    price: float,
    context: OrderContext,
) -> None:
    if quantity <= 0:
        raise ValueError(
            f"{status} broker update for {context.order_id} requires positive filled_qty"
        )
    if price <= 0:
        raise ValueError(
            f"{status} broker update for {context.order_id} requires positive avg_fill_price"
        )


async def _get_trade(db, trade_id: str) -> Optional[dict]:
    if hasattr(db, "get_trade_by_id"):
        return await db.get_trade_by_id(trade_id)
    if hasattr(db, "get_trades"):
        for trade in await db.get_trades(1000):
            if str(trade.get("id")) == str(trade_id):
                return trade
    return None


async def _update_alert(
    db,
    context: OrderContext,
    *,
    trade_executed: bool,
    result: str,
) -> None:
    if context.alert_id and hasattr(db, "update_alert"):
        await db.update_alert(
            context.alert_id,
            {
                "processed": True,
                "trade_executed": trade_executed,
                "trade_result": result,
            },
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


def _int(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _float(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
