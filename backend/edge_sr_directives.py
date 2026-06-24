from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Dict, Optional


EDGE_SR_DIRECTIVE_SCHEMA = "edge.sr.directive.v1"
VALID_ACTIONS = {"close_position", "request_scale_in"}
VALID_SIZING_MODES = {"buying_power_fraction", "contract_fraction"}


class EdgeSrDirectiveIdempotency:
    """Small in-memory helper for tests and local event consumers."""

    def __init__(self):
        self._seen: set[str] = set()

    def accept(self, directive_id: str) -> Dict[str, Any]:
        normalized = str(directive_id or "").strip()
        if not normalized:
            return {"accepted": False, "reason": "missing_directive_id"}
        if normalized in self._seen:
            return {"accepted": False, "reason": "duplicate_directive"}
        self._seen.add(normalized)
        return {"accepted": True, "reason": None}


def validate_edge_sr_directive(
    payload: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
    max_age_seconds: int = 300,
) -> Dict[str, Any]:
    """Validate an Edge S/R directive and map it to a non-executing intent."""
    directive = _unwrap_directive(payload)
    errors: list[str] = []

    if directive.get("schema_version") != EDGE_SR_DIRECTIVE_SCHEMA:
        errors.append("schema_version must be edge.sr.directive.v1")

    directive_id = str(directive.get("directive_id") or "").strip()
    if not directive_id:
        errors.append("directive_id is required")

    action = str(directive.get("action") or "").strip().lower()
    if action not in VALID_ACTIONS:
        errors.append("action must be close_position or request_scale_in")

    contract = _contract_identity(directive.get("position"), errors)
    if directive.get("created_at"):
        created_at = _parse_datetime(directive.get("created_at"))
        if created_at is None:
            errors.append("created_at must be ISO-8601 when supplied")
        elif now is not None and max_age_seconds >= 0:
            normalized_now = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
            age_seconds = (normalized_now - created_at.astimezone(timezone.utc)).total_seconds()
            if age_seconds > max_age_seconds:
                errors.append("directive is stale")

    sizing = None
    if action == "request_scale_in":
        sizing = _sizing_hint(directive.get("sizing_hint"), errors)

    if errors:
        return {"valid": False, "errors": errors, "intent": None}

    intent = {
        "directive_id": directive_id,
        "action": action,
        "reason_code": directive.get("reason_code"),
        "contract": contract,
        "level": directive.get("level") if isinstance(directive.get("level"), dict) else {},
        "execution": directive.get("execution_hint") if isinstance(directive.get("execution_hint"), dict) else {},
        "metadata": directive.get("metadata") if isinstance(directive.get("metadata"), dict) else {},
    }
    if sizing is not None:
        intent["sizing"] = sizing
    return {"valid": True, "errors": [], "intent": intent}


def _unwrap_directive(payload: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(payload, dict) and payload.get("event_type") == EDGE_SR_DIRECTIVE_SCHEMA:
        inner = payload.get("payload")
        return inner if isinstance(inner, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _contract_identity(position: Any, errors: list[str]) -> Dict[str, Any]:
    if not isinstance(position, dict):
        errors.append("position is required")
        return {}

    underlying = str(position.get("underlying") or position.get("symbol") or "").strip().upper()
    option_side = _option_side(position.get("option_side") or position.get("side"))
    expiry = str(position.get("expiry") or "").strip()
    strike = _positive_float(position.get("strike"))
    quantity = _positive_float(position.get("quantity"))

    if not underlying:
        errors.append("position.underlying is required")
    if option_side is None:
        errors.append("position.option_side must be call or put")
    if not expiry:
        errors.append("position.expiry is required")
    if strike is None:
        errors.append("position.strike is required")
    if quantity is None:
        errors.append("position.quantity is required")

    return {
        "position_id": str(position.get("position_id") or position.get("id") or "").strip(),
        "underlying": underlying,
        "option_side": option_side,
        "expiry": expiry,
        "strike": strike,
        "quantity": quantity,
        "entry_price": _positive_float(position.get("entry_price")),
    }


def _sizing_hint(sizing_hint: Any, errors: list[str]) -> Dict[str, Any]:
    if not isinstance(sizing_hint, dict):
        errors.append("sizing_hint is required for request_scale_in")
        return {}

    mode = str(sizing_hint.get("mode") or "").strip().lower()
    fraction = _positive_float(sizing_hint.get("fraction"))
    minimum_contracts = _positive_float(sizing_hint.get("minimum_contracts"))

    if mode not in VALID_SIZING_MODES:
        errors.append("sizing_hint.mode must be buying_power_fraction or contract_fraction")
    if fraction is None or fraction > 1:
        errors.append("sizing_hint.fraction must be greater than 0 and no more than 1")
    if minimum_contracts is None:
        errors.append("sizing_hint.minimum_contracts is required")

    return {
        "mode": mode,
        "fraction": fraction,
        "minimum_contracts": int(minimum_contracts) if minimum_contracts is not None else None,
    }


def _option_side(value: Any) -> Optional[str]:
    side = str(value or "").strip().lower().replace("long_", "")
    if side in {"c", "call", "calls"}:
        return "call"
    if side in {"p", "put", "puts"}:
        return "put"
    return None


def _positive_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
