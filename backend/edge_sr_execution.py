from __future__ import annotations

from datetime import datetime, time, timezone
from math import isfinite
from typing import Any, Iterable

from edge_sr_directives import validate_edge_sr_directive


def build_edge_sr_execution_plan(
    payload: dict[str, Any],
    *,
    positions: Iterable[dict[str, Any]],
    source_config: dict[str, Any],
    now: datetime | None = None,
    idempotency: Any = None,
    max_age_seconds: int = 300,
) -> dict[str, Any]:
    """Build a guarded, non-executing plan from an Edge S/R directive."""
    resolved_now = now or datetime.now(timezone.utc)
    validation = validate_edge_sr_directive(payload, now=resolved_now, max_age_seconds=max_age_seconds)
    if not validation["valid"]:
        return {"status": "rejected", "reason": "invalid_directive", "errors": validation["errors"]}

    intent = validation["intent"]
    directive_id = intent["directive_id"]
    if idempotency is not None:
        accepted = idempotency.accept(directive_id)
        if not accepted.get("accepted"):
            return {"status": "rejected", "reason": accepted.get("reason") or "duplicate_directive"}

    if not source_config.get("sr_watch_enabled"):
        return {"status": "blocked", "reason": "sr_watch_disabled", "directive_id": directive_id}

    position = _matching_position(positions, intent["contract"])
    if position is None:
        return {"status": "blocked", "reason": "position_not_found", "directive_id": directive_id}

    if not source_config.get("sr_watch_auto_act"):
        return {
            "status": "operator_review_required",
            "reason": "sr_watch_auto_act_disabled",
            "directive_id": directive_id,
            "intent": intent,
            "position_id": position.get("id"),
        }

    action = intent["action"]
    if action == "request_scale_in" and _after_stop_trading_cutoff(source_config, resolved_now):
        return {"status": "blocked", "reason": "scale_in_after_cutoff", "directive_id": directive_id}

    if action == "close_position":
        return _close_plan(intent=intent, position=position, directive_id=directive_id)
    if action == "request_scale_in":
        return _scale_in_plan(intent=intent, position=position, directive_id=directive_id)
    return {"status": "rejected", "reason": "unsupported_action", "directive_id": directive_id}


def _close_plan(*, intent: dict[str, Any], position: dict[str, Any], directive_id: str) -> dict[str, Any]:
    quantity = max(0, int(position.get("remaining_quantity") or position.get("quantity") or 0))
    limit_price = _positive_float(position.get("current_price")) or _positive_float(position.get("entry_price"))
    order_intent = {
        "side": "SELL",
        "ticker": position.get("ticker") or intent["contract"]["underlying"],
        "strike": position.get("strike") or intent["contract"]["strike"],
        "option_type": position.get("option_type") or intent["contract"]["option_side"].upper(),
        "expiration": position.get("expiration") or intent["contract"]["expiry"],
        "quantity": quantity,
        "limit_price": limit_price,
        "order_preference": intent.get("execution", {}).get("order_preference", "marketable_limit"),
        "requires_price": limit_price is None,
    }
    return {
        "status": "ready",
        "action": "close_position",
        "directive_id": directive_id,
        "position_id": position.get("id"),
        "reason_code": intent.get("reason_code"),
        "order_intent": order_intent,
    }


def _scale_in_plan(*, intent: dict[str, Any], position: dict[str, Any], directive_id: str) -> dict[str, Any]:
    sizing = intent.get("sizing") or {}
    return {
        "status": "ready",
        "action": "request_scale_in",
        "directive_id": directive_id,
        "position_id": position.get("id"),
        "reason_code": intent.get("reason_code"),
        "order_intent": {
            "side": "BUY",
            "ticker": position.get("ticker") or intent["contract"]["underlying"],
            "strike": position.get("strike") or intent["contract"]["strike"],
            "option_type": position.get("option_type") or intent["contract"]["option_side"].upper(),
            "expiration": position.get("expiration") or intent["contract"]["expiry"],
            "sizing": {
                "mode": sizing.get("mode", "buying_power_fraction"),
                "fraction": sizing.get("fraction", 0.25),
                "minimum_contracts": sizing.get("minimum_contracts", 1),
            },
        },
    }


def _matching_position(
    positions: Iterable[dict[str, Any]],
    contract: dict[str, Any],
) -> dict[str, Any] | None:
    contract_position_id = str(contract.get("position_id") or "").strip()
    candidates = [
        position
        for position in positions
        if str(position.get("status", "open")).lower() in {"open", "partial"}
    ]
    if contract_position_id:
        return next((position for position in candidates if str(position.get("id") or "") == contract_position_id), None)
    return next((position for position in candidates if _same_contract(position, contract)), None)


def _same_contract(position: dict[str, Any], contract: dict[str, Any]) -> bool:
    return (
        _norm(position.get("ticker")) == _norm(contract.get("underlying"))
        and _option_type(position.get("option_type")) == _option_type(contract.get("option_side"))
        and _float_equal(position.get("strike"), contract.get("strike"))
        and _date_key(position.get("expiration")) == _date_key(contract.get("expiry"))
    )


def _after_stop_trading_cutoff(source_config: dict[str, Any], now: datetime) -> bool:
    if not source_config.get("sr_watch_stop_trading_after_time_enabled"):
        return False
    cutoff = _parse_market_time(source_config.get("sr_watch_stop_trading_after_time"))
    if cutoff is None:
        return False
    localized = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return localized.time().replace(tzinfo=None) >= cutoff


def _parse_market_time(value: Any) -> time | None:
    raw = str(value or "").strip()
    parts = raw.split(":", 1)
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return time(hour=hour, minute=minute)


def _option_type(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"C", "CALL", "CALLS"}:
        return "CALL"
    if raw in {"P", "PUT", "PUTS"}:
        return "PUT"
    return raw


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def _date_key(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "/")


def _float_equal(left: Any, right: Any) -> bool:
    try:
        return abs(float(left) - float(right)) < 0.001
    except (TypeError, ValueError):
        return False


def _positive_float(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(numeric) or numeric <= 0:
        return None
    return numeric
