"""
Fill Monitor — polls the broker for order status after placement.

Why this exists
---------------
place_order() on every broker client returns immediately after the HTTP
request with status="submitted".  The order may then be:
  - filled       → update trade to "executed", create/update position
  - partial fill → store partial qty, keep polling
  - rejected     → mark trade "failed", send SMS
  - expired      → treat as failed after timeout

Architecture
------------
After process_trade() places a real (non-simulated) order it calls
monitor_fill() which runs as a background asyncio task.  It polls
get_order_status() on the broker client up to MAX_POLLS times with
POLL_INTERVAL_SECS between each attempt.

Broker client interface required
---------------------------------
Each broker client must expose:

    async def get_order_status(self, order_id: str) -> dict:
        Returns:
          {
            "status": "filled" | "partial" | "cancelled" | "rejected" | "pending",
            "filled_qty": int,       # how many contracts filled so far
            "avg_fill_price": float, # average fill price (0.0 if not yet filled)
          }

This module provides a default implementation that returns {"status": "pending"}
so brokers without the method yet don't crash — they just time out and are marked
as unconfirmed rather than failed.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECS = 5     # how often to poll
MAX_POLLS          = 24    # 24 × 5s = 2 min timeout
PARTIAL_FILL_SECS  = 60    # after this long with a partial fill, accept it


async def _get_order_status_safe(broker_client, order_id: str) -> dict:
    """
    Call broker_client.get_order_status() if it exists.
    Falls back to {"status": "unknown"} so legacy clients degrade gracefully.
    """
    if not hasattr(broker_client, "get_order_status"):
        return {"status": "unknown", "filled_qty": 0, "avg_fill_price": 0.0}
    try:
        return await broker_client.get_order_status(order_id)
    except Exception as e:
        logger.warning(f"get_order_status error for {order_id}: {e}")
        return {"status": "error", "filled_qty": 0, "avg_fill_price": 0.0}


async def monitor_fill(
    trade_id: str,
    order_id: str,
    expected_qty: int,
    broker_client,
    db,
    settings: dict,
    poll_interval_secs: int = POLL_INTERVAL_SECS,
    max_polls: int = MAX_POLLS,
):
    """
    Background task: poll broker until the order resolves, then update the
    trade record and fire notifications.

    Parameters
    ----------
    trade_id       : the UUID of the Trade record already in the database
    order_id       : broker-assigned order reference from place_order()
    expected_qty   : quantity we asked to fill
    broker_client  : an instance of BaseBrokerClient
    db             : the database abstraction object
    settings       : the app settings dict (for SMS credentials)
    """
    from notifications import notify_trade_filled, notify_trade_failed

    logger.info(f"[fill_monitor] watching order {order_id} for trade {trade_id[:8]}")

    partial_since: Optional[datetime] = None

    for poll_num in range(max_polls):
        await asyncio.sleep(poll_interval_secs)

        status_data = await _get_order_status_safe(broker_client, order_id)
        status      = status_data.get("status", "unknown")
        filled_qty  = int(status_data.get("filled_qty", 0))
        fill_price  = float(status_data.get("avg_fill_price", 0.0))

        logger.info(
            f"[fill_monitor] order {order_id} poll {poll_num+1}/{max_polls}: "
            f"status={status} filled={filled_qty}/{expected_qty} price={fill_price}"
        )

        # ── Fully filled ────────────────────────────────────────────────────
        if status == "filled" or (status == "partial" and filled_qty >= expected_qty):
            final_price = fill_price if fill_price > 0 else None
            await _mark_trade_executed(db, trade_id, filled_qty, final_price)
            await notify_trade_filled(
                trade_id, "", 0, "", filled_qty,
                final_price or 0.0, "BUY", settings
            )
            logger.info(f"[fill_monitor] order {order_id} FILLED qty={filled_qty} price={final_price}")
            return

        # ── Partial fill — wait up to PARTIAL_FILL_SECS then accept ─────────
        if status == "partial" and filled_qty > 0:
            if partial_since is None:
                partial_since = datetime.now(timezone.utc)
            else:
                elapsed = (datetime.now(timezone.utc) - partial_since).total_seconds()
                if elapsed >= PARTIAL_FILL_SECS:
                    logger.warning(
                        f"[fill_monitor] order {order_id} partial fill timeout "
                        f"({filled_qty}/{expected_qty}) — accepting partial"
                    )
                    await _mark_trade_executed(db, trade_id, filled_qty, fill_price or None,
                                               note=f"Partial fill: {filled_qty}/{expected_qty}")
                    await notify_trade_filled(
                        trade_id, "", 0, "", filled_qty,
                        fill_price or 0.0, "BUY", settings
                    )
                    return

        # ── Rejected or cancelled ────────────────────────────────────────────
        if status in ("rejected", "cancelled"):
            reason = status_data.get("reason", status)
            await _mark_trade_failed(db, trade_id, reason)
            await notify_trade_failed(trade_id, "", 0, "", reason, settings)
            logger.warning(f"[fill_monitor] order {order_id} {status}: {reason}")
            return

        # ── Unknown/broker-not-implemented — give up after one attempt ───────
        if status == "unknown":
            logger.info(
                f"[fill_monitor] broker does not support get_order_status — "
                f"marking trade {trade_id[:8]} as unconfirmed"
            )
            await _mark_trade_unconfirmed(
                db,
                trade_id,
                expected_qty,
                note="Fill unconfirmed: broker lacks get_order_status",
            )
            return

    # ── Timed out ────────────────────────────────────────────────────────────
    reason = f"Fill confirmation timed out after {max_polls * poll_interval_secs}s"
    await _mark_trade_failed(db, trade_id, reason)
    await notify_trade_failed(trade_id, "", 0, "", reason, settings)
    logger.error(f"[fill_monitor] order {order_id} TIMED OUT — marked failed")


# ── Database helpers ──────────────────────────────────────────────────────────

async def _mark_trade_executed(db, trade_id: str, filled_qty: int,
                                fill_price: Optional[float], note: str = ""):
    update = {
        "status": "executed",
        "quantity": filled_qty,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
    if fill_price is not None:
        update["entry_price"] = fill_price
    if note:
        update["error_message"] = note  # repurpose for informational notes
    try:
        await db.update_trade(trade_id, update)
    except Exception as e:
        logger.error(f"[fill_monitor] failed to mark trade {trade_id[:8]} executed: {e}")


async def _mark_trade_failed(db, trade_id: str, reason: str):
    update = {
        "status": "failed",
        "error_message": reason,
    }
    try:
        await db.update_trade(trade_id, update)
    except Exception as e:
        logger.error(f"[fill_monitor] failed to mark trade {trade_id[:8]} failed: {e}")


async def _mark_trade_unconfirmed(db, trade_id: str, quantity: int, note: str):
    update = {
        "status": "unconfirmed",
        "quantity": quantity,
        "error_message": note,
    }
    try:
        await db.update_trade(trade_id, update)
    except Exception as e:
        logger.error(f"[fill_monitor] failed to mark trade {trade_id[:8]} unconfirmed: {e}")
