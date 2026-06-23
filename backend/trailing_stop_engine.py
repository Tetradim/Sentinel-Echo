from __future__ import annotations

from typing import Any

from settings_flags import coerce_bool


def evaluate_trailing_stop(
    position: dict[str, Any],
    settings: dict[str, Any],
    *,
    current_price: float,
) -> dict[str, Any]:
    """Return a deterministic trailing-stop decision for one position mark."""
    position_id = str(position.get("id") or "").strip()
    entry_price = _positive_float(position.get("entry_price"))
    previous_peak = _positive_float(position.get("highest_price")) or entry_price
    if previous_peak <= 0:
        previous_peak = _positive_float(position.get("current_price"))
    current_price = round(float(current_price), 4)

    decision = {
        "position_id": position_id,
        "enabled": coerce_bool(settings.get("trailing_stop_enabled"), default=False),
        "triggered": False,
        "action": "disabled",
        "reason": "",
        "entry_price": entry_price,
        "previous_peak": previous_peak,
        "highest_price": max(previous_peak, current_price),
        "current_price": current_price,
        "trailing_stop_type": str(settings.get("trailing_stop_type") or "percent").strip().lower(),
        "trailing_stop_level": 0.0,
        "exit_price": None,
    }
    if not decision["enabled"]:
        decision["reason"] = "trailing stop disabled"
        return decision
    if current_price <= 0:
        decision["action"] = "invalid"
        decision["reason"] = "current price must be greater than zero"
        return decision
    if _remaining_quantity(position) <= 0:
        decision["action"] = "ignored"
        decision["reason"] = "position has no remaining quantity"
        return decision
    if str(position.get("status") or "open").strip().lower() not in {"open", "partial"}:
        decision["action"] = "ignored"
        decision["reason"] = "position is not open"
        return decision

    stop_type = decision["trailing_stop_type"]
    peak = decision["highest_price"]
    if stop_type == "premium":
        trailing_amount = _positive_float(settings.get("trailing_stop_cents")) or 0.0
        level = max(0.0, peak - trailing_amount)
    elif stop_type == "percent":
        percent = _positive_float(settings.get("trailing_stop_percent")) or 0.0
        level = max(0.0, peak * (1 - percent / 100))
    else:
        decision["action"] = "invalid"
        decision["reason"] = f"unsupported trailing stop type: {stop_type}"
        return decision

    decision["trailing_stop_level"] = round(level, 4)
    if peak > previous_peak:
        decision["action"] = "peak_updated"
        decision["reason"] = "new highest price recorded"
        return decision
    if peak <= entry_price:
        decision["action"] = "held"
        decision["reason"] = "trailing stop not activated"
        return decision
    if decision["trailing_stop_level"] > 0 and current_price <= decision["trailing_stop_level"]:
        decision["triggered"] = True
        decision["action"] = "triggered"
        decision["reason"] = "current price is at or below trailing stop"
        decision["exit_price"] = current_price
        return decision

    decision["action"] = "held"
    decision["reason"] = "current price is above trailing stop"
    return decision


def _positive_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        return max(float(value or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _remaining_quantity(position: dict[str, Any]) -> int:
    if isinstance(position.get("remaining_quantity"), bool):
        return 0
    try:
        return max(int(position.get("remaining_quantity") or 0), 0)
    except (TypeError, ValueError):
        return 0
