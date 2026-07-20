from __future__ import annotations

from math import floor
from typing import Any, Dict, Iterable, List, Optional


EXIT_ALERT_TYPES = {"sell", "trim", "close"}


def is_exit_alert(parsed: Dict[str, Any]) -> bool:
    return str(parsed.get("alert_type", "")).lower() in EXIT_ALERT_TYPES


def build_exit_plans(
    positions: Iterable[Dict[str, Any]],
    parsed_alert: Dict[str, Any],
    *,
    include_simulated: bool = True,
) -> List[Dict[str, Any]]:
    """Build aggregate sell plans for open positions matching an exit alert.

    The exit percentage is applied once to the total matching exposure, then
    allocated across position lots in the input order. This prevents a small
    partial-exit alert from selling the minimum one contract from every lot.

    When an exit omits expiration and multiple expirations match, the alert is
    blocked rather than guessed.
    """
    if not is_exit_alert(parsed_alert):
        return []

    matched = [
        position
        for position in positions
        if _is_open_position(position) and _matches_alert(position, parsed_alert)
        and (include_simulated or not _is_simulated_position(position))
    ]

    if not matched:
        return []

    if not parsed_alert.get("expiration"):
        expiration_keys = {_date_key(position.get("expiration")) for position in matched}
        expiration_keys.discard("")
        if len(expiration_keys) > 1:
            raise ValueError(
                f"Exit alert for {parsed_alert.get('ticker')} is ambiguous across "
                f"multiple expirations: {sorted(expiration_keys)}"
            )

    remaining_by_position = [
        max(0, int(position.get("remaining_quantity") or position.get("quantity") or 0))
        for position in matched
    ]
    total_remaining = sum(remaining_by_position)
    target_quantity = _exit_quantity(total_remaining, parsed_alert.get("sell_percentage"))
    if target_quantity <= 0:
        return []

    plans = []
    quantity_left = target_quantity
    for position, remaining in zip(matched, remaining_by_position):
        if quantity_left <= 0:
            break
        quantity = min(remaining, quantity_left)
        if quantity <= 0:
            continue

        exit_price = _exit_price(parsed_alert, position)
        if exit_price is None:
            raise ValueError(
                f"Exit alert for {parsed_alert.get('ticker')} matched position "
                f"{position.get('id')}, but no exit price or current position price is available."
            )

        plans.append(
            {
                "position": position,
                "quantity": quantity,
                "exit_price": exit_price,
                "percentage": float(parsed_alert.get("sell_percentage") or 100.0),
            }
        )
        quantity_left -= quantity

    return plans


def _is_open_position(position: Dict[str, Any]) -> bool:
    return str(position.get("status", "open")).lower() in {"open", "partial"}


def _is_simulated_position(position: Dict[str, Any]) -> bool:
    broker = str(position.get("broker") or "").lower()
    return bool(position.get("simulated")) or broker.endswith(":paper_shadow")


def _matches_alert(position: Dict[str, Any], parsed_alert: Dict[str, Any]) -> bool:
    if _norm(position.get("ticker")) != _norm(parsed_alert.get("ticker")):
        return False

    if parsed_alert.get("strike") is not None and not _float_equal(
        position.get("strike"), parsed_alert.get("strike")
    ):
        return False

    if parsed_alert.get("option_type") and _norm(position.get("option_type")) != _norm(
        parsed_alert.get("option_type")
    ):
        return False

    if parsed_alert.get("expiration") and _date_key(position.get("expiration")) != _date_key(
        parsed_alert.get("expiration")
    ):
        return False

    return True


def _exit_quantity(remaining_quantity: int, sell_percentage: Optional[float]) -> int:
    if remaining_quantity <= 0:
        return 0
    pct = float(sell_percentage or 100.0)
    pct = min(100.0, max(1.0, pct))
    return min(remaining_quantity, max(1, floor(remaining_quantity * pct / 100.0)))


def _exit_price(parsed_alert: Dict[str, Any], position: Dict[str, Any]) -> Optional[float]:
    for key in ("entry_price", "exit_price", "current_price"):
        value = parsed_alert.get(key)
        if _positive_number(value):
            return float(value)

    current = position.get("current_price")
    if _positive_number(current):
        return float(current)
    return None


def _positive_number(value: Any) -> bool:
    try:
        return value is not None and float(value) > 0
    except (TypeError, ValueError):
        return False


def _float_equal(left: Any, right: Any) -> bool:
    try:
        return abs(float(left) - float(right)) < 0.001
    except (TypeError, ValueError):
        return False


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()


def _date_key(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "/")
