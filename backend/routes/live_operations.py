"""Operator-facing status for Echo's repaired live execution lifecycle."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query


router = APIRouter(tags=["Live Operations"])
db = None


def set_db(database):
    global db
    db = database


def _journal_records() -> list[dict]:
    from live_order_journal import journal

    records = journal.records()
    records.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return records


def _monitor_snapshot() -> list[dict]:
    import fill_monitor

    rows = []
    for key, task in dict(fill_monitor._ACTIVE_MONITORS).items():
        rows.append({
            "monitor_key": key,
            "active": not task.done(),
            "done": task.done(),
            "cancelled": task.cancelled(),
            "task_name": task.get_name() if hasattr(task, "get_name") else "",
        })
    return rows


def _supervisor_status() -> dict:
    import option_position_supervisor

    task = option_position_supervisor._SUPERVISOR_TASK
    return {
        "running": bool(task is not None and not task.done()),
        "done": bool(task is not None and task.done()),
        "cancelled": bool(task is not None and task.cancelled()),
        "task_name": task.get_name() if task is not None and hasattr(task, "get_name") else "",
    }


@router.get("/live-operations")
async def get_live_operations(limit: int = Query(100, ge=1, le=1000)):
    """Return journal, monitor, supervisor, and broker-inventory state."""
    records = _journal_records()
    active_states = {
        "submitting", "ambiguous", "acknowledged", "submitted", "pending",
        "working", "partial", "working_unconfirmed",
    }
    terminal_states = {"filled", "cancelled", "canceled", "rejected", "expired", "failed"}
    statuses = Counter(str(record.get("status") or "unknown").lower() for record in records)
    active_records = [record for record in records if str(record.get("status") or "").lower() in active_states]
    unresolved = [
        record for record in records
        if bool(record.get("reconciliation_required"))
        or str(record.get("status") or "").lower() in {"ambiguous", "working_unconfirmed"}
    ]

    positions = await db.get_positions()
    live_positions = [position for position in positions if not position.get("simulated")]
    latest_inventory = max(
        [str(position.get("broker_reconciled_at") or "") for position in live_positions],
        default="",
    )
    imported_positions = sum(1 for position in live_positions if position.get("broker_inventory_imported"))
    broker_closed_positions = sum(
        1 for position in live_positions
        if position.get("broker_reconciliation_reason") == "position_absent_at_broker"
    )

    trades = await db.get_trades(1000)
    working_trades = [
        trade for trade in trades
        if str(trade.get("status") or "").lower()
        in {"submitting", "pending", "partial", "working_unconfirmed", "unconfirmed"}
    ]

    monitors = _monitor_snapshot()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "supported_live_brokers": ["alpaca", "tradier"],
        "summary": {
            "journal_total": len(records),
            "journal_active": len(active_records),
            "journal_terminal": sum(statuses[state] for state in terminal_states),
            "ambiguous_or_unconfirmed": len(unresolved),
            "working_trades": len(working_trades),
            "active_fill_monitors": sum(1 for monitor in monitors if monitor["active"]),
            "live_positions": len([position for position in live_positions if position.get("status") in {"open", "partial"}]),
            "broker_inventory_imported_positions": imported_positions,
            "broker_inventory_closed_positions": broker_closed_positions,
        },
        "status_counts": dict(statuses),
        "position_supervisor": _supervisor_status(),
        "fill_monitors": monitors,
        "journal": records[:limit],
        "unresolved_orders": unresolved[:limit],
        "working_trades": working_trades[:limit],
        "broker_inventory": {
            "latest_reconciled_at": latest_inventory or None,
            "imported_positions": imported_positions,
            "positions_closed_as_absent": broker_closed_positions,
        },
    }


@router.get("/live-operations/order/{client_order_id}")
async def get_live_order(client_order_id: str):
    from live_order_journal import journal

    record: Optional[dict] = journal.get(client_order_id)
    if not record:
        return {"found": False, "client_order_id": client_order_id}
    return {"found": True, "order": record}
