from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os


EDGE_SR_DIRECTIVE_EVENT = "edge.sr.directive.v1"
DEFAULT_EVENT_DIR = Path(__file__).resolve().parent / "data" / "event-bus"


def recent_edge_sr_directive_events(
    *,
    root: Path | None = None,
    limit: int = 100,
    target_bot: str = "consolidation",
) -> list[dict[str, Any]]:
    """Read recent Edge S/R directive events from the shared JSONL event bus."""
    event_root = _event_root(root)
    if not event_root.exists():
        return []

    normalized_target = str(target_bot or "").strip().lower()
    max_items = max(1, min(int(limit or 100), 1000))
    events: list[dict[str, Any]] = []
    for path in sorted(event_root.glob("*.jsonl"), reverse=True):
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("event_type") != EDGE_SR_DIRECTIVE_EVENT:
                continue
            targets = [str(item).strip().lower() for item in event.get("target_bots") or []]
            if normalized_target and normalized_target not in targets:
                continue
            events.append(event)
            if len(events) >= max_items:
                return events
    return events


def _event_root(root: Path | None) -> Path:
    if root is not None:
        return Path(root)
    configured = os.environ.get("BOT_EVENT_BUS_DIR")
    return Path(configured) if configured else DEFAULT_EVENT_DIR
