from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any
import os

from bot_event_bus import publish_event
from settings_flags import coerce_bool


_lock = Lock()
_last_heartbeat: dict[str, Any] | None = None
_last_attention_key: str | None = None


def record_bridge_heartbeat(payload: dict[str, Any]) -> dict[str, Any]:
    global _last_heartbeat
    heartbeat = {
        "status": str(payload.get("status") or "ok"),
        "bridge_enabled": coerce_bool(payload.get("bridge_enabled"), default=False),
        "url": payload.get("url") or "",
        "channel_id": payload.get("channel_id") or "",
        "channel_name": payload.get("channel_name") or "",
        "channel_url": payload.get("channel_url") or "",
        "bridge_target_id": payload.get("bridge_target_id") or "",
        "bridge_target_name": payload.get("bridge_target_name") or "",
        "observed_at": payload.get("observed_at") or datetime.now(timezone.utc).isoformat(),
        "last_forward_at": payload.get("last_forward_at") or "",
        "last_forward_status": payload.get("last_forward_status") or "",
        "details": payload.get("details") or {},
    }
    with _lock:
        _last_heartbeat = heartbeat
    publish_event(
        "bridge.health",
        source_bot="chrome-discord-bridge",
        payload=heartbeat,
        dedupe_key=f"chrome-bridge-health:{heartbeat['status']}:{heartbeat['channel_id']}",
        target_bots=["sentinel-edge", "openclaw"],
    )
    return evaluate_bridge_health()


def evaluate_bridge_health() -> dict[str, Any]:
    heartbeat = get_last_heartbeat()
    stale_after_seconds = int(os.environ.get("CHROME_BRIDGE_STALE_SECONDS", "90"))
    now = datetime.now(timezone.utc)
    issues: list[str] = []
    if heartbeat is None:
        issues.append("chrome bridge has not sent a heartbeat")
        age_seconds = None
    else:
        observed = _parse_datetime(heartbeat.get("observed_at"))
        age_seconds = (now - observed).total_seconds() if observed else None
        if age_seconds is None:
            issues.append("chrome bridge heartbeat timestamp is invalid")
        elif age_seconds > stale_after_seconds:
            issues.append(f"chrome bridge heartbeat is stale ({int(age_seconds)}s old)")
        if heartbeat.get("status") not in {"ok", "disabled"}:
            issues.append(f"chrome bridge reported {heartbeat.get('status')}")
        if not heartbeat.get("bridge_enabled", False):
            issues.append("chrome bridge is disabled")

    healthy = not issues
    status = {
        "healthy": healthy,
        "status": "healthy" if healthy else "unhealthy",
        "issues": issues,
        "last_heartbeat": heartbeat,
        "age_seconds": age_seconds,
        "stale_after_seconds": stale_after_seconds,
    }
    if not healthy:
        _request_openclaw_attention(status)
    return status


def get_last_heartbeat() -> dict[str, Any] | None:
    with _lock:
        return dict(_last_heartbeat) if _last_heartbeat else None


def _request_openclaw_attention(status: dict[str, Any]) -> None:
    global _last_attention_key
    attention_key = "|".join(status.get("issues") or [])
    if not attention_key:
        return
    with _lock:
        if _last_attention_key == attention_key:
            return
        _last_attention_key = attention_key
    publish_event(
        "openclaw.attention.requested",
        source_bot="sentinel-echo",
        payload={
            "severity": "warning",
            "reason": "bridge health failure",
            "status": status,
        },
        target_bots=["openclaw", "sentinel-edge"],
        dedupe_key=f"openclaw:bridge-health:{attention_key}",
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
