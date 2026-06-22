"""Append-only operator audit helpers."""
from __future__ import annotations

from typing import Any, Dict

from models import OperatorEvent
from utils.credentials import SENSITIVE_FIELDS


_EXTRA_SENSITIVE_FIELDS = {
    "token",
    "secret",
    "password",
    "api_secret",
    "api_key",
    "access_token",
    "refresh_token",
    "trade_token",
    "credential_key",
    "discord_token",
}


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key or "").lower()
    return normalized in SENSITIVE_FIELDS or any(marker in normalized for marker in _EXTRA_SENSITIVE_FIELDS)


def sanitize_audit_details(value: Any) -> Any:
    """Return audit details with credentials redacted recursively."""
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            sanitized[key] = "[redacted]" if _is_sensitive_key(key) else sanitize_audit_details(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_audit_details(item) for item in value]
    return value


async def record_operator_event(
    db,
    category: str,
    action: str,
    summary: str,
    *,
    severity: str = "info",
    details: dict | None = None,
) -> dict:
    """Append a sanitized operator event and return the stored event payload."""
    event = OperatorEvent(
        category=category,
        action=action,
        summary=summary,
        severity=severity,
        details=sanitize_audit_details(details or {}),
    ).model_dump(mode="json")
    if hasattr(db, "insert_operator_event"):
        await db.insert_operator_event(event)
    return event
