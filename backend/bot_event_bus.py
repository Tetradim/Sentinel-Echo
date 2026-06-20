from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4
import json
import os

from pydantic import BaseModel, Field


EVENT_SCHEMA_VERSION = "bot-event.v1"
DEFAULT_EVENT_DIR = Path(__file__).resolve().parent / "data" / "event-bus"


class BotEvent(BaseModel):
    version: str = EVENT_SCHEMA_VERSION
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str = Field(..., min_length=1, max_length=120)
    source_bot: str = Field(..., min_length=1, max_length=80)
    source_instance: str = Field(default="local", max_length=120)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: str | None = Field(default=None, max_length=240)
    dedupe_key: str | None = Field(default=None, max_length=240)
    target_bots: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)


class EventBusStore:
    """Small local-first append-only bus used as the shared bot contract.

    Each bot can publish the same event shape without waiting on Sentinel Edge.
    Edge can consume the stream and publish strategic action/state events back.
    """

    def __init__(self, root: Path | None = None):
        self.root = root or DEFAULT_EVENT_DIR
        self._lock = Lock()

    def publish(self, event: BotEvent) -> BotEvent:
        root = self._root()
        root.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.model_dump(mode="json"), sort_keys=True)
        with self._lock:
            with self._path_for(event.created_at).open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return event

    def recent(self, limit: int = 100, event_type: str | None = None) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 1000))
        events: list[dict[str, Any]] = []
        files = sorted(self._root().glob("*.jsonl"), reverse=True)
        for path in files:
            for line in reversed(path.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event_type and event.get("event_type") != event_type:
                    continue
                events.append(event)
                if len(events) >= limit:
                    return events
        return events

    def _path_for(self, created_at: str) -> Path:
        day = str(created_at or "")[:10]
        if not day or len(day) != 10:
            day = datetime.now(timezone.utc).date().isoformat()
        return self._root() / f"{day}.jsonl"

    def _root(self) -> Path:
        configured_root = os.environ.get("BOT_EVENT_BUS_DIR")
        return Path(configured_root) if configured_root else self.root


event_bus = EventBusStore()


def publish_event(
    event_type: str,
    *,
    source_bot: str,
    payload: dict[str, Any] | None = None,
    source_instance: str = "local",
    correlation_id: str | None = None,
    dedupe_key: str | None = None,
    target_bots: list[str] | None = None,
    trace: dict[str, Any] | None = None,
) -> BotEvent:
    event = BotEvent(
        event_type=event_type,
        source_bot=source_bot,
        source_instance=source_instance,
        correlation_id=correlation_id,
        dedupe_key=dedupe_key,
        target_bots=target_bots or [],
        payload=payload or {},
        trace=trace or {},
    )
    return event_bus.publish(event)
