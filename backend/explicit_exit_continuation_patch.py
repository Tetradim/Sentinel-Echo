"""Continue explicit broker exits after cancellation or pre-submit rejection."""
from __future__ import annotations

from typing import Any

import option_position_supervisor as supervisor
from live_order_journal import journal


_original_exit_reason = supervisor._exit_reason
_original_submit_exit = supervisor._submit_exit
_TERMINAL_RETRYABLE = {"cancelled", "canceled", "rejected", "expired", "failed"}


def _integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _retryable_explicit_exit(position_id: str) -> dict | None:
    candidates = []
    for record in journal.records():
        if str(record.get("position_id") or "") != str(position_id):
            continue
        if str(record.get("side") or "").upper() != "SELL":
            continue
        status = str(record.get("status") or "").lower()
        if status not in _TERMINAL_RETRYABLE:
            continue
        client_id = str(record.get("client_order_id") or "")
        if client_id.startswith("echo-risk-") and not client_id.startswith(
            "echo-risk-requested_exit_retry-"
        ):
            # Stop/profit/trailing exits remain driven by the live threshold.
            continue
        requested = _integer(record.get("quantity"))
        filled = _integer(record.get("filled_qty"))
        outstanding = max(0, requested - filled)
        if outstanding <= 0:
            continue
        candidates.append(
            {
                **record,
                "outstanding_quantity": outstanding,
            }
        )
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda value: str(value.get("updated_at") or value.get("created_at") or ""),
    )


def _exit_reason_with_explicit_retry(position: dict, settings: dict, mark: float, highest: float):
    reason = _original_exit_reason(position, settings, mark, highest)
    if reason:
        return reason
    pending = _retryable_explicit_exit(str(position.get("id") or ""))
    return "requested_exit_retry" if pending else None


async def _submit_exit_with_requested_quantity(db, settings, position, reason, quote):
    if reason != "requested_exit_retry":
        return await _original_submit_exit(db, settings, position, reason, quote)
    pending = _retryable_explicit_exit(str(position.get("id") or ""))
    if not pending:
        return False
    outstanding = min(
        _integer(position.get("remaining_quantity")),
        _integer(pending.get("outstanding_quantity")),
    )
    if outstanding <= 0:
        return False
    continued = {
        **position,
        "remaining_quantity": outstanding,
        "continued_exit_client_order_id": pending.get("client_order_id"),
        "continued_exit_order_id": pending.get("broker_order_id"),
    }
    return await _original_submit_exit(
        db,
        settings,
        continued,
        reason,
        quote,
    )


supervisor._exit_reason = _exit_reason_with_explicit_retry
supervisor._submit_exit = _submit_exit_with_requested_quantity
