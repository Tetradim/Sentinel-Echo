"""Poll broker order status and delegate state changes to fill reconciliation."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update


logger = logging.getLogger(__name__)

POLL_INTERVAL_SECS = 5
DEFAULT_CONFIRMATION_TIMEOUT_SECS = 180
BACKGROUND_POLL_INTERVAL_SECS = 15
PARTIAL_FILL_SECS = 60


async def _get_order_status_safe(broker_client, order_id: str) -> dict:
    if not hasattr(broker_client, "get_order_status"):
        return {"status": "unknown", "filled_qty": 0, "avg_fill_price": 0.0}
    try:
        return await broker_client.get_order_status(order_id)
    except Exception as exc:
        logger.warning("get_order_status error for %s: %s", order_id, exc)
        return {"status": "error", "filled_qty": 0, "avg_fill_price": 0.0, "reason": str(exc)}


async def _cancel_order_safe(broker_client, order_id: str) -> dict:
    if not hasattr(broker_client, "cancel_order"):
        return {
            "status": "cancel_unavailable",
            "cancel_requested": False,
            "reason": "Broker client does not support cancel_order",
        }
    try:
        return await broker_client.cancel_order(order_id)
    except Exception as exc:
        logger.warning("cancel_order error for %s: %s", order_id, exc)
        return {"status": "cancel_failed", "cancel_requested": False, "reason": str(exc)}


async def _reconcile_status_data(db, order_context: OrderContext, status_data: dict, settings: dict) -> bool:
    from notifications import notify_trade_filled, notify_trade_failed

    status = str(status_data.get("status", "unknown")).lower()
    filled_qty = int(status_data.get("filled_qty", 0) or 0)
    fill_price = float(status_data.get("avg_fill_price", 0.0) or 0.0)
    trade_id = order_context.trade_id
    expected_qty = order_context.requested_quantity

    if status == "filled" or (status == "partial" and filled_qty >= expected_qty):
        await reconcile_order_update(
            db,
            order_context,
            BrokerOrderUpdate(status="filled", filled_qty=filled_qty, avg_fill_price=fill_price),
            settings=settings,
        )
        await notify_trade_filled(
            trade_id,
            order_context.ticker,
            order_context.strike,
            order_context.option_type,
            filled_qty,
            fill_price,
            order_context.side,
            settings,
        )
        return True

    if status in {"rejected", "cancelled", "canceled", "expired"}:
        reason = str(status_data.get("reason") or status)
        await reconcile_order_update(
            db,
            order_context,
            BrokerOrderUpdate(
                status=status,
                filled_qty=filled_qty,
                avg_fill_price=fill_price,
                reason=reason,
            ),
            settings=settings,
        )
        await notify_trade_failed(
            trade_id,
            order_context.ticker,
            order_context.strike,
            order_context.option_type,
            reason,
            settings,
        )
        return True

    return False


async def monitor_fill(
    order_context: OrderContext,
    broker_client,
    db,
    settings: dict,
    poll_interval_secs: int = POLL_INTERVAL_SECS,
    max_polls: int | None = None,
    background_poll_interval_secs: int | None = None,
    max_background_polls: int | None = None,
    close_broker_client_when_done: bool = False,
):
    """Poll broker status and optionally close a caller-owned broker client."""
    try:
        confirmation_timeout = max(
            1,
            int(settings.get("fill_confirmation_timeout_seconds", DEFAULT_CONFIRMATION_TIMEOUT_SECS) or DEFAULT_CONFIRMATION_TIMEOUT_SECS),
        )
        resolved_max_polls = max_polls
        if resolved_max_polls is None:
            resolved_max_polls = max(1, (confirmation_timeout + max(1, poll_interval_secs) - 1) // max(1, poll_interval_secs))
        resolved_background_interval = background_poll_interval_secs
        if resolved_background_interval is None:
            resolved_background_interval = max(
                1,
                int(settings.get("fill_background_poll_interval_seconds", BACKGROUND_POLL_INTERVAL_SECS) or BACKGROUND_POLL_INTERVAL_SECS),
            )
        return await _monitor_fill(
            order_context=order_context,
            broker_client=broker_client,
            db=db,
            settings=settings,
            poll_interval_secs=poll_interval_secs,
            max_polls=resolved_max_polls,
            background_poll_interval_secs=resolved_background_interval,
            max_background_polls=max_background_polls,
        )
    finally:
        if close_broker_client_when_done:
            from order_execution import close_broker_client

            await close_broker_client(broker_client)


async def _monitor_fill(
    order_context: OrderContext,
    broker_client,
    db,
    settings: dict,
    poll_interval_secs: int = POLL_INTERVAL_SECS,
    max_polls: int = 1,
    background_poll_interval_secs: int = BACKGROUND_POLL_INTERVAL_SECS,
    max_background_polls: int | None = None,
):
    """Poll broker status until terminal, then reconcile trade and position state."""
    from notifications import notify_trade_filled, notify_trade_failed

    order_id = order_context.order_id
    trade_id = order_context.trade_id
    expected_qty = order_context.requested_quantity
    partial_since: Optional[datetime] = None

    logger.info("[fill_monitor] watching order %s for trade %s", order_id, trade_id[:8])

    for poll_num in range(max_polls):
        await asyncio.sleep(poll_interval_secs)
        status_data = await _get_order_status_safe(broker_client, order_id)
        status = str(status_data.get("status", "unknown")).lower()
        filled_qty = int(status_data.get("filled_qty", 0) or 0)
        fill_price = float(status_data.get("avg_fill_price", 0.0) or 0.0)

        logger.info(
            "[fill_monitor] order %s poll %s/%s: status=%s filled=%s/%s price=%s",
            order_id,
            poll_num + 1,
            max_polls,
            status,
            filled_qty,
            expected_qty,
            fill_price,
        )

        if await _reconcile_status_data(db, order_context, status_data, settings):
            return

        if status == "partial" and filled_qty > 0:
            if partial_since is None:
                partial_since = datetime.now(timezone.utc)
                continue
            elapsed = (datetime.now(timezone.utc) - partial_since).total_seconds()
            if elapsed >= PARTIAL_FILL_SECS:
                cancel_result = await _cancel_order_safe(broker_client, order_id)
                logger.warning(
                    "[fill_monitor] order %s remained partial; cancel result: %s",
                    order_id,
                    cancel_result,
                )
                final_status = await _get_order_status_safe(broker_client, order_id)
                final_filled_qty = int(final_status.get("filled_qty", 0) or 0)
                if final_filled_qty >= expected_qty and await _reconcile_status_data(
                    db, order_context, final_status, settings
                ):
                    return
                filled_qty = max(filled_qty, final_filled_qty)
                fill_price = float(final_status.get("avg_fill_price", 0.0) or fill_price)
                await reconcile_order_update(
                    db,
                    order_context,
                    BrokerOrderUpdate(
                        status="partial",
                        filled_qty=filled_qty,
                        avg_fill_price=fill_price,
                        reason=f"Partial fill: {filled_qty}/{expected_qty}",
                    ),
                    settings=settings,
                )
                await notify_trade_filled(
                    trade_id,
                    order_context.ticker,
                    order_context.strike,
                    order_context.option_type,
                    filled_qty,
                    fill_price,
                    f"{order_context.side} (PARTIAL)",
                    settings,
                )
                return

        if status in {"unknown", "error", "unconfirmed"}:
            logger.warning(
                "[fill_monitor] order %s status unresolved on poll %s/%s: %s",
                order_id,
                poll_num + 1,
                max_polls,
                status_data.get("reason") or status,
            )
            continue

    reason = f"Fill confirmation timed out after {max_polls * poll_interval_secs}s"
    if order_context.side.upper() == "SELL":
        reason = f"{reason}; sell exit order remains live and under broker reconciliation"
        logger.warning(
            "[fill_monitor] sell order %s timed out with unresolved status; leaving order live",
            order_id,
        )
        await reconcile_order_update(
            db,
            order_context,
            BrokerOrderUpdate(status="pending_broker", reason=reason),
        )
        background_polls = 0
        while max_background_polls is None or background_polls < max_background_polls:
            await asyncio.sleep(background_poll_interval_secs)
            status_data = await _get_order_status_safe(broker_client, order_id)
            if await _reconcile_status_data(db, order_context, status_data, settings):
                return
            background_polls += 1
        return

    cancel_result = await _cancel_order_safe(broker_client, order_id)
    logger.warning(
        "[fill_monitor] order %s timed out; cancel result: %s",
        order_id,
        cancel_result,
    )
    for _ in range(3):
        status_data = await _get_order_status_safe(broker_client, order_id)
        if await _reconcile_status_data(db, order_context, status_data, settings):
            return
        await asyncio.sleep(poll_interval_secs)

    cancel_reason = str(cancel_result.get("reason") or cancel_result.get("status") or "").strip()
    if cancel_reason:
        reason = f"{reason}; cancel follow-up unresolved: {cancel_reason}"
    await reconcile_order_update(
        db,
        order_context,
        BrokerOrderUpdate(status="unconfirmed", reason=reason),
    )
    await notify_trade_failed(
        trade_id,
        order_context.ticker,
        order_context.strike,
        order_context.option_type,
        reason,
        settings,
    )
