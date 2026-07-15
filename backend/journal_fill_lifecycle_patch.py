"""Mirror broker reconciliation states into the pre-submit order journal."""
from __future__ import annotations

try:
    from . import fill_monitor
    from .live_order_journal import journal
except ImportError:  # direct backend path execution
    import fill_monitor
    from live_order_journal import journal


_original_reconcile = fill_monitor.reconcile_order_update


async def _reconcile_and_close_journal(db, context, update):
    result = await _original_reconcile(db, context, update)
    record = journal.find_by_broker_order_id(context.order_id, context.broker)
    if record:
        journal.mark_from_broker(
            str(record.get("client_order_id") or ""),
            {
                "order_id": context.order_id,
                "status": update.status,
                "filled_qty": update.filled_qty,
                "avg_fill_price": update.avg_fill_price,
                "reason": update.reason,
            },
        )
    return result


fill_monitor.reconcile_order_update = _reconcile_and_close_journal
