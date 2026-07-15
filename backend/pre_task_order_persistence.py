"""Close the broker-acknowledgement/task-scheduling durability gap.

``server.py`` submits a broker order, persists its pending trade, and then calls
``asyncio.create_task(monitor_fill(...))``. An abrupt process exit between the
broker acknowledgement and the monitor coroutine's first instruction could
leave an unrecoverable working order. This module patches the server's imported
``monitor_fill`` symbol with a synchronous wrapper that commits recovery
metadata before returning the coroutine to ``create_task``.
"""
from __future__ import annotations

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


def monitor_fill_with_pre_task_persistence(*args, **kwargs):
    order_context = kwargs.get("order_context")
    if order_context is None and args:
        order_context = args[0]
    if order_context is None:
        return _original_monitor_fill(*args, **kwargs)

    try:
        _persist_recovery_context_sync(order_context)
    except Exception as exc:
        # The broker order already exists, so monitoring it is more important
        # than failing the task creation. The coroutine repeats the persistence
        # asynchronously as its first instruction and logs any continuing DB
        # failure through the normal monitor path.
        logger.critical(
            "Could not synchronously persist recovery context for broker order %s: %s",
            order_context.order_id,
            exc,
            exc_info=True,
        )
    return _original_monitor_fill(*args, **kwargs)


server.monitor_fill = monitor_fill_with_pre_task_persistence
