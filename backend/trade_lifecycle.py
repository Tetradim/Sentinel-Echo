from __future__ import annotations

from math import floor
from typing import Any, Dict, Iterable, List, Optional

from utils import normalize_expiration_for_order


EXIT_ALERT_TYPES = {"sell", "trim", "close"}


def is_exit_alert(parsed: Dict[str, Any]) -> bool:
    return str(parsed.get("alert_type", "")).lower() in EXIT_ALERT_TYPES


def build_exit_plans(
    positions: Iterable[Dict[str, Any]],
    parsed_alert: Dict[str, Any],
    *,
    include_simulated: bool = True,
    allow_missing_exit_price: bool = False,
) -> List[Dict[str, Any]]:
    """Build sell plans for open positions matching an exit alert."""
    if not is_exit_alert(parsed_alert):
        return []

    matched = [
        position
        for position in positions
        if _is_open_position(position) and _matches_alert(position, parsed_alert)
    ]

    if not matched:
        return []

    source_config = parsed_alert.get("_source_config") if isinstance(parsed_alert.get("_source_config"), dict) else {}
    if _is_broad_exit_alert(parsed_alert):
        if not _behavior_enabled(source_config, "allow_broad_exit_matching", default=True) and (
            parsed_alert.get("strike") is None or not parsed_alert.get("option_type")
        ):
            raise ValueError(
                f"broad exit matching disabled for {parsed_alert.get('ticker')}: "
                "alert requires strike and option type."
            )
        if not _behavior_enabled(source_config, "allow_single_position_inferred_sell", default=True) and not parsed_alert.get("expiration"):
            raise ValueError(
                f"single-position inferred sell disabled for {parsed_alert.get('ticker')}: "
                "alert requires expiration."
            )

    if len(matched) > 1 and _is_broad_exit_alert(parsed_alert):
        raise ValueError(
            f"ambiguous exit alert for {parsed_alert.get('ticker')}: "
            f"{len(matched)} matching open positions require a more specific contract."
        )

    plans = []
    for position in matched:
        quantity = _exit_quantity(
            int(position.get("remaining_quantity") or position.get("quantity") or 0),
            parsed_alert.get("sell_percentage"),
        )
        if quantity <= 0:
            continue

        exit_price = _exit_price(parsed_alert, position)
        if exit_price is None and not allow_missing_exit_price:
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
    return plans


def _is_open_position(position: Dict[str, Any]) -> bool:
    return str(position.get("status", "open")).lower() in {"open", "partial"}


def _is_broad_exit_alert(parsed_alert: Dict[str, Any]) -> bool:
    return (
        parsed_alert.get("strike") is None
        or not parsed_alert.get("option_type")
        or not parsed_alert.get("expiration")
    )


def _matches_alert(position: Dict[str, Any], parsed_alert: Dict[str, Any]) -> bool:
    if parsed_alert.get('_card') and position.get('id') != parsed_alert['_card'].get('position_id'):
        return False
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

    if parsed_alert.get("market_price"):
        return None

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
    return (
        str(normalize_expiration_for_order(value, roll_forward=False) or value or "")
        .strip()
        .upper()
        .replace("-", "/")
    )


def _behavior_enabled(source_config: Dict[str, Any], key: str, *, default: bool) -> bool:
    value = (source_config or {}).get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    return default
