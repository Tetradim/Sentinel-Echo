from __future__ import annotations

from typing import Any

from models import Alert


def build_edge_sr_action_request(plan: dict[str, Any], *, source_config: dict[str, Any]) -> dict[str, Any]:
    """Convert a ready Edge S/R plan into Consolidation alert-processing inputs."""
    if plan.get("status") != "ready":
        raise ValueError("Edge S/R execution plan must be ready before building an action request")

    order_intent = plan.get("order_intent") if isinstance(plan.get("order_intent"), dict) else {}
    action = str(plan.get("action") or "").strip()
    if action == "close_position":
        return _close_request(plan, order_intent, source_config)
    if action == "request_scale_in":
        return _scale_in_request(plan, order_intent, source_config)
    raise ValueError(f"Unsupported Edge S/R plan action: {action}")


def _close_request(
    plan: dict[str, Any],
    order_intent: dict[str, Any],
    source_config: dict[str, Any],
) -> dict[str, Any]:
    price = _positive_price(order_intent.get("limit_price")) or 0.01
    alert = Alert(
        ticker=_required_text(order_intent.get("ticker"), "ticker"),
        strike=_required_float(order_intent.get("strike"), "strike"),
        option_type=_required_text(order_intent.get("option_type"), "option_type").upper(),
        expiration=_required_text(order_intent.get("expiration"), "expiration"),
        entry_price=price,
        alert_type="sell",
        sell_percentage=100.0,
        raw_message=_raw_message(plan),
    )
    parsed = _base_parsed(alert, plan, source_config)
    parsed["sell_percentage"] = 100.0
    return {"alert": alert, "parsed": parsed}


def _scale_in_request(
    plan: dict[str, Any],
    order_intent: dict[str, Any],
    source_config: dict[str, Any],
) -> dict[str, Any]:
    price = _positive_price(order_intent.get("limit_price")) or _positive_price(order_intent.get("entry_price")) or 0.01
    alert = Alert(
        ticker=_required_text(order_intent.get("ticker"), "ticker"),
        strike=_required_float(order_intent.get("strike"), "strike"),
        option_type=_required_text(order_intent.get("option_type"), "option_type").upper(),
        expiration=_required_text(order_intent.get("expiration"), "expiration"),
        entry_price=price,
        alert_type="buy",
        raw_message=_raw_message(plan),
    )
    parsed = _base_parsed(alert, plan, source_config)
    parsed["_edge_sr_sizing"] = order_intent.get("sizing") if isinstance(order_intent.get("sizing"), dict) else {}
    return {"alert": alert, "parsed": parsed}


def _base_parsed(alert: Alert, plan: dict[str, Any], source_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticker": alert.ticker,
        "strike": alert.strike,
        "option_type": alert.option_type,
        "expiration": alert.expiration,
        "entry_price": alert.entry_price,
        "alert_type": alert.alert_type,
        "_source_config": dict(source_config or {}),
        "_edge_sr_directive_id": str(plan.get("directive_id") or ""),
        "_edge_sr_reason_code": str(plan.get("reason_code") or ""),
        "_edge_sr_position_id": str(plan.get("position_id") or ""),
    }


def _raw_message(plan: dict[str, Any]) -> str:
    return (
        f"EDGE_SR {plan.get('action')} {plan.get('directive_id')} "
        f"{plan.get('reason_code') or ''}"
    ).strip()


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"Edge S/R action request missing {field}")
    return text


def _required_float(value: Any, field: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Edge S/R action request missing {field}") from exc
    if numeric <= 0:
        raise ValueError(f"Edge S/R action request missing {field}")
    return numeric


def _positive_price(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None
