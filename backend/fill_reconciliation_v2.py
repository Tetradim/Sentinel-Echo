"""Broker-authoritative cumulative fill reconciliation.

Broker quantities/prices are cumulative. Trade rows and position rows each keep
independent cumulative application state so a failure between those writes can
be retried without duplicating quantity or realized P&L.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fill_reconciliation import BrokerOrderUpdate, OrderContext, ReconciliationResult


_POSITION_LOCKS: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def reconcile_order_update(
    db,
    context: OrderContext,
    update: BrokerOrderUpdate,
) -> ReconciliationResult:
    status = _normalise_status(update.status)
    trade = await _get_trade(db, context.trade_id) or {}
    applied_qty = _int(trade.get("applied_filled_qty"))

    if status in {"rejected", "cancelled", "expired"}:
        # Some brokers return a terminal state with a final cumulative partial
        # fill. Apply that fill before closing the order lifecycle.
        fill_result = ReconciliationResult(trade_status="pending")
        if _int(update.filled_qty) > applied_qty:
            _validate_fill("partial", _int(update.filled_qty), _float(update.avg_fill_price), context)
            fill_result = await _apply_cumulative_fill(
                db,
                context,
                BrokerOrderUpdate(
                    status="partial",
                    filled_qty=_int(update.filled_qty),
                    avg_fill_price=_float(update.avg_fill_price),
                    reason=update.reason,
                ),
                trade_status=(
                    "executed"
                    if _int(update.filled_qty) == context.requested_quantity
                    else "partial"
                ),
            )
            trade = await _get_trade(db, context.trade_id) or trade
            applied_qty = _int(trade.get("applied_filled_qty"))

        reason = update.reason or status
        terminal_status = (
            "executed"
            if applied_qty >= context.requested_quantity
            else "partial"
            if applied_qty > 0
            else "failed"
        )
        await db.update_trade(
            context.trade_id,
            {
                "status": terminal_status,
                "error_message": "" if terminal_status == "executed" else reason,
                "broker_status": status,
                "reconciliation_context": context.to_dict(),
                "monitor_state": "terminal",
            },
        )
        await _update_alert(
            db,
            context,
            trade_executed=applied_qty > 0,
            result=(
                "filled"
                if terminal_status == "executed"
                else f"partial then {status}: {reason}"
                if terminal_status == "partial"
                else f"failed: {reason}"
            ),
        )
        return ReconciliationResult(
            trade_status=terminal_status,
            position_status=fill_result.position_status,
            position_id=fill_result.position_id,
            message=reason,
            applied_quantity=fill_result.applied_quantity,
            applied_price=fill_result.applied_price,
        )

    if status in {"unknown", "error", "unconfirmed", "working_unconfirmed"}:
        reason = update.reason or "Broker order status temporarily unavailable"
        await db.update_trade(
            context.trade_id,
            {
                "status": "partial" if applied_qty > 0 else "working_unconfirmed",
                "error_message": reason,
                "broker_status": status,
                "reconciliation_context": context.to_dict(),
            },
        )
        return ReconciliationResult(
            trade_status="partial" if applied_qty > 0 else "working_unconfirmed",
            message=reason,
        )

    if status not in {"partial", "filled"}:
        await db.update_trade(
            context.trade_id,
            {
                "status": "partial" if applied_qty > 0 else "pending",
                "broker_status": status or "pending",
                "reconciliation_context": context.to_dict(),
            },
        )
        return ReconciliationResult(
            trade_status="partial" if applied_qty > 0 else "pending",
            message=status or "pending",
        )

    cumulative_qty = _int(update.filled_qty)
    cumulative_avg = _float(update.avg_fill_price)
    _validate_fill(status, cumulative_qty, cumulative_avg, context)
    if status == "filled" and cumulative_qty != context.requested_quantity:
        raise ValueError(
            f"Filled broker update for {context.order_id} is inconsistent: "
            f"filled {cumulative_qty}, requested {context.requested_quantity}"
        )
    if cumulative_qty > context.requested_quantity:
        raise ValueError(
            f"Broker cumulative fill exceeds requested quantity for {context.order_id}: "
            f"{cumulative_qty} > {context.requested_quantity}"
        )

    return await _apply_cumulative_fill(
        db,
        context,
        update,
        trade_status="executed" if status == "filled" else "partial",
    )


async def _apply_cumulative_fill(
    db,
    context: OrderContext,
    update: BrokerOrderUpdate,
    *,
    trade_status: str,
) -> ReconciliationResult:
    lock_key = context.position_id or f"position:{context.trade_id}"
    async with _POSITION_LOCKS[lock_key]:
        trade = await _get_trade(db, context.trade_id) or {}
        cumulative_qty = _int(update.filled_qty)
        cumulative_avg = _float(update.avg_fill_price)
        trade_applied_qty = _int(trade.get("applied_filled_qty"))
        if cumulative_qty < trade_applied_qty:
            raise ValueError(
                f"Broker cumulative fill moved backwards for {context.order_id}: "
                f"{cumulative_qty} < {trade_applied_qty}"
            )

        if context.side.upper() == "BUY":
            position_id, position_status, position_delta_qty, position_delta_price = await _apply_buy_position(
                db,
                context,
                cumulative_qty=cumulative_qty,
                cumulative_avg=cumulative_avg,
            )
            order_pnl = None
        else:
            position_id, position_status, position_delta_qty, position_delta_price, order_pnl = await _apply_sell_position(
                db,
                context,
                cumulative_qty=cumulative_qty,
                cumulative_avg=cumulative_avg,
            )

        common = {
            "status": trade_status,
            "quantity": cumulative_qty,
            "order_id": context.order_id,
            "broker_status": _normalise_status(update.status),
            "applied_filled_qty": cumulative_qty,
            "applied_fill_notional": cumulative_qty * cumulative_avg,
            "avg_fill_price": cumulative_avg,
            "executed_at": trade.get("executed_at") or _now(),
            "error_message": "",
            "reconciliation_context": context.to_dict(),
        }
        if context.side.upper() == "BUY":
            common["entry_price"] = cumulative_avg
        else:
            common.update(
                {
                    "side": "SELL",
                    "exit_price": cumulative_avg,
                    "realized_pnl": order_pnl,
                }
            )
        await db.update_trade(context.trade_id, common)
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
            applied_quantity=position_delta_qty,
            applied_price=position_delta_price,
        )


async def _apply_buy_position(
    db,
    context: OrderContext,
    *,
    cumulative_qty: int,
    cumulative_avg: float,
) -> tuple[str, str, int, float]:
    position_id = context.position_id or f"position:{context.trade_id}"
    position = await db.get_position_by_id(position_id)
    cumulative_notional = cumulative_qty * cumulative_avg

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
            "total_cost": cumulative_notional * 100,
            "broker": context.broker,
            "status": "open",
            "opened_at": _now(),
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "simulated": context.simulated,
            "trade_ids": [context.trade_id],
            "highest_price": cumulative_avg,
            "applied_entry_orders": {
                context.order_id: {
                    "quantity": cumulative_qty,
                    "notional": cumulative_notional,
                }
            },
        }
        await db.insert_position(position)
        return position_id, "open", cumulative_qty, cumulative_avg

    applied_orders = dict(position.get("applied_entry_orders") or {})
    previous_order = dict(applied_orders.get(context.order_id) or {})
    previous_qty = _int(previous_order.get("quantity"))
    previous_notional = _float(previous_order.get("notional"))
    if cumulative_qty < previous_qty:
        raise ValueError(
            f"Entry fill moved backwards for {context.order_id}: "
            f"{cumulative_qty} < {previous_qty}"
        )
    delta_qty = cumulative_qty - previous_qty
    delta_notional = cumulative_notional - previous_notional
    if delta_qty > 0 and delta_notional <= 0:
        raise ValueError("Entry fill requires positive incremental notional")
    delta_price = delta_notional / delta_qty if delta_qty > 0 else 0.0

    if delta_qty > 0:
        original_quantity = _int(position.get("original_quantity")) + delta_qty
        remaining_quantity = _int(position.get("remaining_quantity")) + delta_qty
        total_cost = _float(position.get("total_cost")) + (delta_notional * 100)
        applied_orders[context.order_id] = {
            "quantity": cumulative_qty,
            "notional": cumulative_notional,
        }
        trade_ids = list(position.get("trade_ids") or [])
        if context.trade_id not in trade_ids:
            trade_ids.append(context.trade_id)
        await db.update_position(
            position_id,
            {
                "$set": {
                    "entry_price": total_cost / (original_quantity * 100),
                    "current_price": cumulative_avg,
                    "original_quantity": original_quantity,
                    "remaining_quantity": remaining_quantity,
                    "total_cost": total_cost,
                    "status": "open",
                    "trade_ids": trade_ids,
                    "highest_price": max(_float(position.get("highest_price")), cumulative_avg),
                    "applied_entry_orders": applied_orders,
                }
            },
        )
    return position_id, "open", delta_qty, delta_price


async def _apply_sell_position(
    db,
    context: OrderContext,
    *,
    cumulative_qty: int,
    cumulative_avg: float,
) -> tuple[str, str, int, float, float]:
    if not context.position_id:
        raise ValueError("SELL fill reconciliation requires position_id")
    position = await db.get_position_by_id(context.position_id)
    if not position:
        raise ValueError(f"Position not found for sell fill: {context.position_id}")

    applied_orders = dict(position.get("applied_exit_orders") or {})
    previous_order = dict(applied_orders.get(context.order_id) or {})
    previous_qty = _int(previous_order.get("quantity"))
    previous_notional = _float(previous_order.get("notional"))
    cumulative_notional = cumulative_qty * cumulative_avg
    if cumulative_qty < previous_qty:
        raise ValueError(
            f"Exit fill moved backwards for {context.order_id}: "
            f"{cumulative_qty} < {previous_qty}"
        )
    delta_qty = cumulative_qty - previous_qty
    delta_notional = cumulative_notional - previous_notional
    if delta_qty > 0 and delta_notional <= 0:
        raise ValueError("Exit fill requires positive incremental notional")
    delta_price = delta_notional / delta_qty if delta_qty > 0 else 0.0

    remaining_before = _int(position.get("remaining_quantity") or position.get("quantity"))
    if delta_qty > remaining_before:
        raise ValueError(
            f"Sell fill delta exceeds remaining position for {context.position_id}: "
            f"{delta_qty} > {remaining_before}"
        )

    entry_price = _float(position.get("entry_price"))
    if delta_qty > 0:
        delta_pnl = (delta_price - entry_price) * delta_qty * 100
        remaining = remaining_before - delta_qty
        position_pnl = _float(position.get("realized_pnl")) + delta_pnl
        position_status = "closed" if remaining <= 0 else "partial"
        applied_orders[context.order_id] = {
            "quantity": cumulative_qty,
            "notional": cumulative_notional,
        }
        trade_ids = list(position.get("trade_ids") or [])
        if context.trade_id not in trade_ids:
            trade_ids.append(context.trade_id)
        position_update = {
            "remaining_quantity": remaining,
            "realized_pnl": position_pnl,
            "current_price": delta_price,
            "status": position_status,
            "trade_ids": trade_ids,
            "applied_exit_orders": applied_orders,
        }
        if remaining <= 0:
            position_update["closed_at"] = _now()
        await db.update_position(context.position_id, {"$set": position_update})
    else:
        position_status = str(position.get("status") or "open")

    order_pnl = (cumulative_avg - entry_price) * cumulative_qty * 100
    return context.position_id, position_status, delta_qty, delta_price, order_pnl


def _validate_fill(status: str, quantity: int, price: float, context: OrderContext) -> None:
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
