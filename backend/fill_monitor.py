"""Poll broker order status and delegate state changes to fill reconciliation."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update


logger = logging.getLogger(__name__)

POLL_INTERVAL_SECS = 5
MAX_POLLS = 24
PARTIAL_FILL_SECS = 60


async def _get_order_status_safe(broker_client, order_id: str) -> dict:
    if not hasattr(broker_client, "get_order_status"):
        return {"status": "unknown", "filled_qty": 0, "avg_fill_price": 0.0}
    try:
        return await broker_client.get_order_status(order_id)
    except Exception as exc:
        logger.warning("get_order_status error for %s: %s", order_id, exc)
        return {"status": "error", "filled_qty": 0, "avg_fill_price": 0.0, "reason": str(exc)}


async def monitor_fill(
    order_context: OrderContext,
    broker_client,
    db,
    settings: dict,
    poll_interval_secs: int = POLL_INTERVAL_SECS,
    max_polls: int = MAX_POLLS,
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

        if status == "filled" or (status == "partial" and filled_qty >= expected_qty):
            await reconcile_order_update(
                db,
                order_context,
                BrokerOrderUpdate(status="filled", filled_qty=filled_qty, avg_fill_price=fill_price),
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
            return

        if status == "partial" and filled_qty > 0:
            if partial_since is None:
                partial_since = datetime.now(timezone.utc)
                continue
            elapsed = (datetime.now(timezone.utc) - partial_since).total_seconds()
            if elapsed >= PARTIAL_FILL_SECS:
                await reconcile_order_update(
                    db,
                    order_context,
                    BrokerOrderUpdate(
                        status="partial",
                        filled_qty=filled_qty,
                        avg_fill_price=fill_price,
                        reason=f"Partial fill: {filled_qty}/{expected_qty}",
                    ),
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

        if status in {"rejected", "cancelled", "expired"}:
            reason = str(status_data.get("reason") or status)
            await reconcile_order_update(
                db,
                order_context,
                BrokerOrderUpdate(status=status, reason=reason),
            )
            await notify_trade_failed(
                trade_id,
                order_context.ticker,
                order_context.strike,
                order_context.option_type,
                reason,
                settings,
            )
            return

        if status in {"unknown", "error", "unconfirmed"}:
            reason = str(status_data.get("reason") or "Fill unconfirmed")
            await reconcile_order_update(
                db,
                order_context,
                BrokerOrderUpdate(status="unconfirmed", reason=reason),
            )
            return

    reason = f"Fill confirmation timed out after {max_polls * poll_interval_secs}s"
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
