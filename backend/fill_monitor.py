"""Durable broker order monitoring and restart recovery."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fill_reconciliation import (
    BrokerOrderUpdate,
    OrderContext,
    ReconciliationResult,
    reconcile_order_update,
)


logger = logging.getLogger(__name__)

POLL_INTERVAL_SECS = 5
MAX_POLLS = 720  # one hour at the default interval; restart recovery resumes later
TRANSIENT_ERROR_REPORT_THRESHOLD = 3
_ACTIVE_MONITORS: dict[str, asyncio.Task] = {}


async def _get_order_status_safe(broker_client, order_id: str) -> dict:
    if not hasattr(broker_client, "get_order_status"):
        return {
            "status": "error",
            "filled_qty": 0,
            "avg_fill_price": 0.0,
            "reason": "Configured broker does not expose order status",
        }
    try:
        result = await broker_client.get_order_status(order_id)
        return result if isinstance(result, dict) else {
            "status": "error",
            "reason": "Broker returned a non-object order status",
        }
    except Exception as exc:
        logger.warning("get_order_status error for %s: %s", order_id, exc)
        return {
            "status": "error",
            "filled_qty": 0,
            "avg_fill_price": 0.0,
            "reason": str(exc),
        }


async def monitor_fill(
    order_context: OrderContext,
    broker_client,
    db,
    settings: dict,
    poll_interval_secs: int = POLL_INTERVAL_SECS,
    max_polls: Optional[int] = MAX_POLLS,
):
    """Poll a broker order until terminal while applying cumulative fill deltas.

    Partial fills do not end monitoring. Temporary status failures do not mark
    the order failed. If the polling window ends, the order remains
    ``working_unconfirmed`` and is resumed by startup recovery.
    """
    from notifications import notify_trade_filled, notify_trade_failed

    order_id = order_context.order_id
    trade_id = order_context.trade_id
    monitor_key = f"{order_context.broker}:{order_id}"
    current_task = asyncio.current_task()
    existing = _ACTIVE_MONITORS.get(monitor_key)
    if existing is not None and existing is not current_task and not existing.done():
        logger.info("[fill_monitor] order %s is already monitored", order_id)
        return
    if current_task is not None:
        _ACTIVE_MONITORS[monitor_key] = current_task

    await db.update_trade(
        trade_id,
        {
            "status": "pending",
            "order_id": order_id,
            "broker": order_context.broker,
            "requested_quantity": order_context.requested_quantity,
            "reconciliation_context": order_context.to_dict(),
            "monitor_state": "active",
        },
    )

    logger.info("[fill_monitor] watching order %s for trade %s", order_id, trade_id[:8])
    transient_errors = 0
    poll_num = 0

    try:
        while max_polls is None or poll_num < max_polls:
            status_data = await _get_order_status_safe(broker_client, order_id)
            status = _normalise_status(status_data.get("status"))
            filled_qty = _int_value(
                status_data.get("filled_qty")
                or status_data.get("filled_quantity")
            )
            fill_price = _float_value(
                status_data.get("avg_fill_price")
                or status_data.get("filled_price")
            )
            reason = str(
                status_data.get("reason")
                or status_data.get("error")
                or ""
            )
            poll_num += 1

            logger.info(
                "[fill_monitor] order %s poll %s%s: status=%s filled=%s/%s price=%s",
                order_id,
                poll_num,
                f"/{max_polls}" if max_polls is not None else "",
                status,
                filled_qty,
                order_context.requested_quantity,
                fill_price,
            )

            if status in {"partial", "filled"}:
                transient_errors = 0
                result = await reconcile_order_update(
                    db,
                    order_context,
                    BrokerOrderUpdate(
                        status=status,
                        filled_qty=filled_qty,
                        avg_fill_price=fill_price,
                        reason=reason,
                    ),
                )
                await _notify_new_fill(
                    result,
                    order_context,
                    settings,
                    notify_trade_filled,
                )
                if status == "filled":
                    await db.update_trade(trade_id, {"monitor_state": "terminal"})
                    return

            elif status in {"rejected", "cancelled", "expired"}:
                result = await reconcile_order_update(
                    db,
                    order_context,
                    BrokerOrderUpdate(status=status, reason=reason or status),
                )
                await db.update_trade(trade_id, {"monitor_state": "terminal"})
                await notify_trade_failed(
                    trade_id,
                    order_context.ticker,
                    order_context.strike,
                    order_context.option_type,
                    result.message or status,
                    settings,
                )
                return

            elif status in {"unknown", "error", "unconfirmed"}:
                transient_errors += 1
                if transient_errors >= TRANSIENT_ERROR_REPORT_THRESHOLD:
                    await reconcile_order_update(
                        db,
                        order_context,
                        BrokerOrderUpdate(
                            status="working_unconfirmed",
                            reason=reason or "Broker order status temporarily unavailable",
                        ),
                    )
                    await db.update_trade(
                        trade_id,
                        {
                            "monitor_state": "retrying",
                            "status_lookup_failures": transient_errors,
                        },
                    )
                # Continue polling: a temporary API outage is not a terminal order state.

            else:
                transient_errors = 0
                await reconcile_order_update(
                    db,
                    order_context,
                    BrokerOrderUpdate(status=status or "pending"),
                )

            if max_polls is None or poll_num < max_polls:
                await asyncio.sleep(poll_interval_secs)

        reason = (
            f"Order remains working/unconfirmed after "
            f"{poll_num * poll_interval_secs}s of monitoring"
        )
        await reconcile_order_update(
            db,
            order_context,
            BrokerOrderUpdate(status="working_unconfirmed", reason=reason),
        )
        await db.update_trade(
            trade_id,
            {
                "monitor_state": "paused_for_recovery",
                "error_message": reason,
            },
        )
        logger.error("[fill_monitor] %s: %s", order_id, reason)
    finally:
        if _ACTIVE_MONITORS.get(monitor_key) is current_task:
            _ACTIVE_MONITORS.pop(monitor_key, None)
        await _close_broker_client(broker_client)


async def resume_pending_fill_monitors(db, settings: dict) -> int:
    """Rehydrate non-terminal broker orders from persisted trade context."""
    from order_execution import get_configured_broker_client

    resumed = 0
    trades = await db.get_trades(1000)
    for trade in trades:
        status = str(trade.get("status") or "").lower()
        if status not in {"pending", "partial", "working_unconfirmed", "unconfirmed"}:
            continue
        order_id = str(trade.get("order_id") or "").strip()
        if not order_id:
            continue
        context_data = trade.get("reconciliation_context")
        if not isinstance(context_data, dict):
            logger.error(
                "[fill_monitor] cannot recover trade %s: reconciliation context missing",
                trade.get("id"),
            )
            continue
        try:
            context = OrderContext.from_dict(context_data)
            monitor_key = f"{context.broker}:{context.order_id}"
            active = _ACTIVE_MONITORS.get(monitor_key)
            if active is not None and not active.done():
                continue
            broker_client = get_configured_broker_client(
                settings,
                context.broker,
                require_order_status=True,
            )
            task = asyncio.create_task(
                monitor_fill(
                    order_context=context,
                    broker_client=broker_client,
                    db=db,
                    settings=settings,
                ),
                name=f"fill-monitor:{context.broker}:{context.order_id}",
            )
            _ACTIVE_MONITORS[monitor_key] = task
            resumed += 1
        except Exception as exc:
            logger.exception(
                "[fill_monitor] failed to recover trade %s: %s",
                trade.get("id"),
                exc,
            )
    return resumed


async def stop_fill_monitors() -> None:
    """Cancel active monitor tasks during application shutdown."""
    tasks = [task for task in _ACTIVE_MONITORS.values() if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _ACTIVE_MONITORS.clear()


async def _notify_new_fill(
    result: ReconciliationResult,
    context: OrderContext,
    settings: dict,
    notify_trade_filled,
) -> None:
    if result.applied_quantity <= 0:
        return
    side = context.side if result.trade_status == "executed" else f"{context.side} (PARTIAL)"
    await notify_trade_filled(
        context.trade_id,
        context.ticker,
        context.strike,
        context.option_type,
        result.applied_quantity,
        result.applied_price,
        side,
        settings,
    )


async def _close_broker_client(broker_client) -> None:
    close = getattr(broker_client, "close", None)
    if not callable(close):
        return
    try:
        result = close()
        if asyncio.iscoroutine(result):
            await result
    except Exception as exc:
        logger.warning("Failed to close broker client: %s", exc)


def _normalise_status(value) -> str:
    status = str(value or "unknown").strip().lower()
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


def _int_value(value) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _float_value(value) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
