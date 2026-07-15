"""Close the broker-acknowledgement/task-scheduling durability gap.

The pre-submit journal now records intent before the network call. This wrapper
persists the final routed broker and reconciliation context synchronously before
``asyncio.create_task`` receives the monitor coroutine.
"""
from __future__ import annotations

from dataclasses import replace
import logging
from typing import Any

try:
    from . import server
except ImportError:  # direct backend path execution
    import server


logger = logging.getLogger(__name__)
_original_monitor_fill = server.monitor_fill


def _recovery_fields(order_context) -> dict[str, Any]:
    return {
        "order_id": order_context.order_id,
        "broker": order_context.broker,
        "requested_quantity": order_context.requested_quantity,
        "reconciliation_context": order_context.to_dict(),
        "monitor_state": "scheduled",
    }


def _persist_recovery_context_sync(order_context) -> None:
    updates = _recovery_fields(order_context)
    if server.USE_SQLITE:
        from database_sqlite import update_trade

        update_trade(order_context.trade_id, updates)
        return

    if server.sync_mongo_db is None:
        raise RuntimeError("Synchronous MongoDB client is unavailable")
    result = server.sync_mongo_db.trades.update_one(
        {"id": order_context.trade_id},
        {"$set": updates},
    )
    if result.matched_count != 1:
        raise RuntimeError(
            f"Pending trade not found while scheduling broker monitor: "
            f"{order_context.trade_id}"
        )


def _route_context(order_context, broker_client):
    routed_broker = str(getattr(broker_client, "routed_broker_id", "") or "")
    if not routed_broker or routed_broker == order_context.broker:
        return order_context
    return replace(order_context, broker=routed_broker)


def monitor_fill_with_pre_task_persistence(*args, **kwargs):
    order_context = kwargs.get("order_context")
    if order_context is None and args:
        order_context = args[0]
    if order_context is None:
        return _original_monitor_fill(*args, **kwargs)

    broker_client = kwargs.get("broker_client")
    if broker_client is None and len(args) > 1:
        broker_client = args[1]
    order_context = _route_context(order_context, broker_client)

    if "order_context" in kwargs:
        kwargs = {**kwargs, "order_context": order_context}
    elif args:
        args = (order_context, *args[1:])

    try:
        _persist_recovery_context_sync(order_context)
    except Exception as exc:
        # The pre-submit journal still preserves the broker-capable intent. The
        # monitor repeats database persistence asynchronously as its first step.
        logger.critical(
            "Could not synchronously persist recovery context for broker order %s: %s",
            order_context.order_id,
            exc,
            exc_info=True,
        )
    return _original_monitor_fill(*args, **kwargs)


server.monitor_fill = monitor_fill_with_pre_task_persistence
