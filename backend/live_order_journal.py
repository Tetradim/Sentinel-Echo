"""Atomic pre-submit journal for live broker orders.

The journal is deliberately independent of the primary database so a database
outage cannot erase the fact that a broker-capable request is about to be sent.
Each deterministic client order id has one durable lifecycle record.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any


_ACTIVE_STATES = {
    "submitting",
    "ambiguous",
    "acknowledged",
    "submitted",
    "pending",
    "working",
    "partial",
    "working_unconfirmed",
}
_TERMINAL_STATES = {"filled", "cancelled", "canceled", "rejected", "expired", "failed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LiveOrderJournal:
    def __init__(self, path: Path | None = None):
        configured = os.getenv("LIVE_ORDER_JOURNAL_PATH", "data/live_order_journal.json")
        self.path = path or Path(configured)
        self._lock = threading.RLock()

    def _read(self) -> dict:
        if not self.path.exists():
            return {"version": 1, "orders": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {"version": 1, "orders": {}}
        if not isinstance(data, dict):
            return {"version": 1, "orders": {}}
        orders = data.get("orders")
        if not isinstance(orders, dict):
            orders = {}
        return {"version": 1, "orders": orders}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(data, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def get(self, client_order_id: str) -> dict | None:
        with self._lock:
            value = self._read()["orders"].get(str(client_order_id))
            return deepcopy(value) if isinstance(value, dict) else None

    def begin(self, client_order_id: str, **fields: Any) -> dict:
        key = str(client_order_id or "").strip()
        if not key:
            raise ValueError("Live order requires deterministic client_order_id")
        with self._lock:
            data = self._read()
            existing = data["orders"].get(key)
            if isinstance(existing, dict) and str(existing.get("status")) in _ACTIVE_STATES:
                return deepcopy(existing)
            now = _now()
            record = {
                "client_order_id": key,
                "status": "submitting",
                "created_at": now,
                "updated_at": now,
                **fields,
            }
            data["orders"][key] = record
            self._write(data)
            return deepcopy(record)

    def update(self, client_order_id: str, **fields: Any) -> dict:
        key = str(client_order_id or "").strip()
        if not key:
            raise ValueError("client_order_id is required")
        with self._lock:
            data = self._read()
            record = dict(data["orders"].get(key) or {"client_order_id": key, "created_at": _now()})
            record.update(fields)
            record["updated_at"] = _now()
            data["orders"][key] = record
            self._write(data)
            return deepcopy(record)

    def acknowledge(self, client_order_id: str, broker_order_id: str, **fields: Any) -> dict:
        return self.update(
            client_order_id,
            status=str(fields.pop("status", "acknowledged") or "acknowledged").lower(),
            broker_order_id=str(broker_order_id or ""),
            acknowledged_at=_now(),
            **fields,
        )

    def ambiguous(self, client_order_id: str, error: str, **fields: Any) -> dict:
        return self.update(
            client_order_id,
            status="ambiguous",
            last_error=str(error),
            reconciliation_required=True,
            **fields,
        )

    def fail(self, client_order_id: str, error: str, **fields: Any) -> dict:
        return self.update(
            client_order_id,
            status="failed",
            last_error=str(error),
            **fields,
        )

    def records(self, *, active_only: bool = False) -> list[dict]:
        with self._lock:
            values = [deepcopy(value) for value in self._read()["orders"].values() if isinstance(value, dict)]
        if not active_only:
            return values
        return [value for value in values if str(value.get("status") or "").lower() in _ACTIVE_STATES]

    def mark_from_broker(self, client_order_id: str, broker_update: dict) -> dict:
        status = str(broker_update.get("status") or "working_unconfirmed").lower()
        order_id = str(broker_update.get("order_id") or broker_update.get("broker_order_id") or "")
        fields = {
            "status": status,
            "broker_order_id": order_id,
            "filled_qty": broker_update.get("filled_qty", broker_update.get("filled_quantity", 0)),
            "avg_fill_price": broker_update.get("avg_fill_price", broker_update.get("filled_price", 0)),
            "last_error": broker_update.get("reason") or broker_update.get("error") or "",
            "reconciliation_required": status not in _TERMINAL_STATES,
        }
        return self.update(client_order_id, **fields)


journal = LiveOrderJournal()
