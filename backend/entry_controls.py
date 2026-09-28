from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from position_identity import canonical_expiration_yyyymmdd, same_option_contract


_SCALE_IN_PATTERNS = (
    re.compile(r"\b(?:avg|average)\s+down\b", re.IGNORECASE),
    re.compile(r"\b(?:add|adding|scale)\s+(?:to|in|into)\b", re.IGNORECASE),
    re.compile(r"\bre-?entry\b", re.IGNORECASE),
    re.compile(r"\breload(?:ing)?\b", re.IGNORECASE),
)
_NON_ACTIONABLE_AVERAGE_FILL = re.compile(r"\b(?:avg|average)\s+fill\b", re.IGNORECASE)
_EXPLICIT_REENTRY_PATTERNS = (
    re.compile(r"\bre-?ent(?:er|ry|ering)\b", re.IGNORECASE),
    re.compile(r"\bre-?add(?:ing|ed)?\b", re.IGNORECASE),
    re.compile(r"\bback\s+in\b", re.IGNORECASE),
    re.compile(r"\bnew\s+entry\b", re.IGNORECASE),
)
_DEFERRED_REENTRY_RE = re.compile(
    r"\b(?:will|may|might|could|plan(?:ning)?\s+to|looking\s+to|waiting\s+to)\s+"
    r"(?:re-?ent(?:er|ry|ering)|re-?add(?:ing|ed)?|get\s+back\s+in)\b",
    re.IGNORECASE,
)
_FAST_SCALP_PATTERNS = (
    re.compile(r"\bsudden\s+profit\b", re.IGNORECASE),
    re.compile(r"\bquick\s+scalp\b", re.IGNORECASE),
    re.compile(r"\bscalp(?:ing)?\b", re.IGNORECASE),
)
_HIGH_RISK_ENTRY_PATTERNS = (
    ("high risk", re.compile(r"\bhigh[\s-]+risk\b", re.IGNORECASE)),
    ("lotto", re.compile(r"\blotto\b", re.IGNORECASE)),
    ("size for zero", re.compile(r"\bsize(?:d)?\s+for\s+\$?\s*0\b", re.IGNORECASE)),
    ("full loss", re.compile(r"\bfull\s+loss\b", re.IGNORECASE)),
    ("designed to go to zero", re.compile(r"\bdesigned\s+to\s+go\s+to\s+\$?\s*0\b", re.IGNORECASE)),
    ("profits only", re.compile(r"\bonly\s+use\s+profits\b", re.IGNORECASE)),
    (
        "not expected in the money",
        re.compile(r"\b(?:won['\u2019]?t|will\s+not|not\s+expected\s+to)\s+(?:go|finish)\s+ITM\b", re.IGNORECASE),
    ),
)


def alert_risk_size_cap(raw_text: Any, *, cap_percent: float = 25.0) -> tuple[float | None, list[str]]:
    """Return a reduced size cap when an analyst explicitly labels an entry as disposable risk."""
    text = str(raw_text or "")
    reasons = [label for label, pattern in _HIGH_RISK_ENTRY_PATTERNS if pattern.search(text)]
    if not reasons:
        return None, []
    return max(1.0, min(100.0, float(cap_percent))), reasons


def alert_exit_profile(raw_text: Any) -> str:
    text = str(raw_text or "")
    return "fast_scalp" if any(pattern.search(text) for pattern in _FAST_SCALP_PATTERNS) else "standard"


def explicit_scale_in_allowed(raw_text: Any) -> bool:
    text = str(raw_text or "")
    if _NON_ACTIONABLE_AVERAGE_FILL.search(text):
        return False
    return any(pattern.search(text) for pattern in _SCALE_IN_PATTERNS)


def explicit_reentry_allowed(raw_text: Any) -> bool:
    text = str(raw_text or "")
    if _DEFERRED_REENTRY_RE.search(text):
        return False
    return any(pattern.search(text) for pattern in _EXPLICIT_REENTRY_PATTERNS)


def existing_contract_entry_block_reason(
    positions: list[dict[str, Any]],
    alert_contract: dict[str, Any],
    raw_text: Any,
    *,
    alert_id: str | None = None,
    allow_fresh_entry_after_close: bool = False,
    now: datetime | None = None,
) -> str | None:
    """Block accidental adds and same-session reopens of an option contract."""
    scale_in_allowed = explicit_scale_in_allowed(raw_text)

    for position in positions or []:
        if str(position.get("status") or "open").strip().lower() not in {"open", "partial"}:
            continue
        try:
            remaining = int(position.get("remaining_quantity") or position.get("quantity") or 0)
        except (TypeError, ValueError):
            remaining = 0
        if remaining <= 0:
            continue
        if same_option_contract(position, alert_contract):
            if scale_in_allowed:
                return None
            ticker = str(alert_contract.get("ticker") or position.get("ticker") or "").strip().upper()
            strike = float(alert_contract.get("strike") or position.get("strike") or 0.0)
            option_type = str(alert_contract.get("option_type") or position.get("option_type") or "").strip().upper()
            expiration = canonical_expiration_yyyymmdd(
                alert_contract.get("expiration") or position.get("expiration")
            )
            return f"blocked: open position exists for {ticker} {strike} {option_type} {expiration}"

    if explicit_reentry_allowed(raw_text):
        return None

    observed_at = now or datetime.now(timezone.utc)
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    eastern = ZoneInfo("America/New_York")
    session_date = observed_at.astimezone(eastern).date()
    for position in positions or []:
        if str(position.get("status") or "").strip().lower() != "closed":
            continue
        if not same_option_contract(position, alert_contract):
            continue
        closed_at = _parsed_datetime(position.get("closed_at"))
        if closed_at is None or closed_at.astimezone(eastern).date() != session_date:
            continue
        prior_alert_id = str(position.get("alert_id") or "").strip()
        incoming_alert_id = str(alert_id or "").strip()
        if (
            allow_fresh_entry_after_close
            and incoming_alert_id
            and prior_alert_id
            and incoming_alert_id != prior_alert_id
        ):
            return None
        ticker = str(alert_contract.get("ticker") or position.get("ticker") or "").strip().upper()
        strike = float(alert_contract.get("strike") or position.get("strike") or 0.0)
        option_type = str(alert_contract.get("option_type") or position.get("option_type") or "").strip().upper()
        expiration = canonical_expiration_yyyymmdd(
            alert_contract.get("expiration") or position.get("expiration")
        )
        return f"blocked: contract already closed this session for {ticker} {strike} {option_type} {expiration}"
    return None


def _parsed_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
