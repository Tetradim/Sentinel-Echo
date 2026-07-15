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

    def find_by_broker_order_id(self, broker_order_id: str, broker: str = "") -> dict | None:
        target = str(broker_order_id or "").strip()
        if not target:
            return None
        broker = str(broker or "").strip().lower()
        with self._lock:
            for value in self._read()["orders"].values():
                if not isinstance(value, dict):
                    continue
                if str(value.get("broker_order_id") or "") != target:
                    continue
                if broker and str(value.get("broker") or "").lower() != broker:
                    continue
                return deepcopy(value)
        return None

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

    def reserve_exit(
        self,
        client_order_id: str,
        *,
        position_id: str,
        quantity: int,
        position_remaining_quantity: int,
        **fields: Any,
    ) -> dict:
        key = str(client_order_id or "").strip()
        position_id = str(position_id or "").strip()
        quantity = int(quantity)
        remaining = int(position_remaining_quantity)
        if not key or not position_id or quantity <= 0:
            raise ValueError("Exit reservation requires client_order_id, position_id and positive quantity")

        with self._lock:
            data = self._read()
            existing = data["orders"].get(key)
            if isinstance(existing, dict):
                return deepcopy(existing)

            reserved = 0
            for record in data["orders"].values():
                if not isinstance(record, dict):
                    continue
                if str(record.get("position_id") or "") != position_id:
                    continue
                if str(record.get("side") or "").upper() != "SELL":
                    continue
                if str(record.get("status") or "").lower() not in _ACTIVE_STATES:
                    continue
                requested = int(float(record.get("quantity") or 0))
                filled = int(float(record.get("filled_qty") or 0))
                reserved += max(0, requested - filled)

            available = remaining - reserved
            if available < quantity:
                raise RuntimeError(
                    f"Exit reservation for position {position_id} exceeds available contracts: "
                    f"available={available}, requested={quantity}, already_reserved={reserved}"
                )

            now = _now()
            record = {
                "client_order_id": key,
                "status": "submitting",
                "created_at": now,
                "updated_at": now,
                "position_id": position_id,
                "quantity": quantity,
                "exit_reserved_quantity": quantity,
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
        status = str(fields.pop("status", "acknowledged") or "acknowledged").lower()
        if status in {"", "unknown"}:
            status = "submitted"
        return self.update(
            client_order_id,
            status=status,
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
            reconciliation_required=False,
            exit_reserved_quantity=0,
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
        status = {"partially_filled": "partial", "canceled": "cancelled"}.get(status, status)
        order_id = str(broker_update.get("order_id") or broker_update.get("broker_order_id") or "")
        filled_qty = int(float(broker_update.get("filled_qty", broker_update.get("filled_quantity", 0)) or 0))
        record = self.get(client_order_id) or {}
        requested_qty = int(float(record.get("quantity") or 0))
        fields = {
            "status": status,
            "broker_order_id": order_id,
            "filled_qty": filled_qty,
            "avg_fill_price": broker_update.get("avg_fill_price", broker_update.get("filled_price", 0)),
            "last_error": broker_update.get("reason") or broker_update.get("error") or "",
            "reconciliation_required": status not in _TERMINAL_STATES,
            "exit_reserved_quantity": (
                max(0, requested_qty - filled_qty)
                if str(record.get("side") or "").upper() == "SELL" and status in _ACTIVE_STATES
                else 0
            ),
        }
        return self.update(client_order_id, **fields)


journal = LiveOrderJournal()
