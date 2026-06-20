from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from zoneinfo import ZoneInfo
import json
import os


DEFAULT_CAPTURE_DIR = Path(__file__).resolve().parent / "data" / "alert-capture"
MARKET_TZ = ZoneInfo(os.environ.get("ALERT_CAPTURE_TIMEZONE", "America/New_York"))
_lock = Lock()


def record_alert_capture(
    *,
    event_id: str,
    channel_id: str,
    channel_name: str,
    author_name: str,
    raw_text: str,
    observed_at: str | None,
    parsed: dict[str, Any] | None,
    ingestion_result: dict[str, Any],
) -> Path:
    """Append a permanent human-readable market-day alert capture line."""

    captured_at = _parse_datetime(observed_at) or datetime.now(timezone.utc)
    market_day = captured_at.astimezone(MARKET_TZ).date().isoformat()
    root = Path(os.environ.get("ALERT_CAPTURE_DIR") or DEFAULT_CAPTURE_DIR)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{market_day}.txt"
    row = {
        "captured_at": captured_at.astimezone(timezone.utc).isoformat(),
        "market_day": market_day,
        "event_id": event_id,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "author_name": author_name,
        "raw_text": raw_text,
        "parsed": parsed,
        "ingestion_result": ingestion_result,
    }
    with _lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return path


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
