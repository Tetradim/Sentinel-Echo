"""Cancel aged live option orders so exits can be re-priced."""
from __future__ import annotations

from datetime import datetime, timezone
import os
import time
from typing import Any

from live_order_journal import journal
import live_order_execution_runtime as routing


_current_get_order_status = routing.JournalledRoutingBrokerClient.get_order_status
_ACTIVE = {"submitted", "pending", "working", "partial", "partially_filled", "working_unconfirmed", "new", "accepted", "open"}


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _positive_env(name: str, default: float) -> float:
    value = _num(os.getenv(name, default))
    return value if value > 0 else default


def _epoch(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _ttl(record: dict) -> float:
    return _positive_env(
        "ECHO_EXIT_ORDER_TTL_SECONDS"
        if str(record.get("side") or "").upper() == "SELL"
        else "ECHO_ENTRY_ORDER_TTL_SECONDS",
        30.0 if str(record.get("side") or "").upper() == "SELL" else 120.0,
    )


async def _status_with_expiry(self, order_id: str) -> dict:
    result = await _current_get_order_status(self, order_id)
    if not isinstance(result, dict):
        return result
    status = str(result.get("status") or "unknown").lower()
    status = {"partially_filled": "partial", "canceled": "cancelled"}.get(status, status)
    if status not in _ACTIVE:
        return result

    broker = str(result.get("broker") or getattr(self, "routed_broker_id", "") or "")
    record = journal.find_by_broker_order_id(order_id, broker)
    if not record:
        return result
    started = _epoch(record.get("acknowledged_at") or record.get("created_at"))
    if not started or time.time() - started < _ttl(record):
        return result

    last_request = _num(record.get("cancel_requested_at_epoch"))
    retry_seconds = _positive_env("ECHO_CANCEL_RETRY_SECONDS", 10.0)
    accepted_before = bool(record.get("cancel_request_accepted"))
    if accepted_before or (last_request and time.time() - last_request < retry_seconds):
        return {
            **result,
            "reason": result.get("reason") or "Order cancellation requested after execution TTL",
        }

    accepted = False
    error = ""
    try:
        accepted = bool(await self.cancel_order(order_id))
    except Exception as exc:
        error = str(exc)
    journal.update(
        str(record.get("client_order_id") or ""),
        cancel_requested_at=datetime.now(timezone.utc).isoformat(),
        cancel_requested_at_epoch=time.time(),
        cancel_request_accepted=accepted,
        cancel_request_error=error,
    )
    if accepted:
        # Fetch once more so a terminal cancellation or race-to-fill is visible
        # to the fill monitor immediately.
        follow_up = await _current_get_order_status(self, order_id)
        if isinstance(follow_up, dict):
            follow_up.setdefault("reason", "Order exceeded execution TTL and cancellation was requested")
            return follow_up
    return {
        **result,
        "reason": error or result.get("reason") or "Order cancellation request failed",
    }


routing.JournalledRoutingBrokerClient.get_order_status = _status_with_expiry
