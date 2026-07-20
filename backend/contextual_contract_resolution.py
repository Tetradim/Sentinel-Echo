from __future__ import annotations

import inspect
import re
from typing import Any, Callable, Optional

from utils import OPTION_RE, _extract_price


CONTEXTUAL_ENTRY_RE = re.compile(
    r"^\s*(?:RE[-\s]?ADD(?:ING|ED)?|RE[-\s]?ENTER(?:ING|ED)?|RE[-\s]?ENTRY|"
    r"ADD(?:ING)?\s+TO)\b",
    re.IGNORECASE,
)
WATCH_BLOCK_RE = re.compile(
    r"\b(?:ENTRY\s+NOT\s+VALID|NO\s+ENTRY(?:\s+YET)?|ON\s+WATCH|"
    r"WATCHING\s+FOR|POSSIBLE\s+RELOAD)\b",
    re.IGNORECASE,
)
CONTEXT_TICKER_STOPWORDS = {
    "RE", "ADD", "ADDING", "ADDED", "ENTER", "ENTERING", "ENTERED",
    "ENTRY", "TO", "THE", "A", "AN", "INITIAL", "ORIGINAL", "PRIOR",
    "PREVIOUS", "ALERT", "POSITION", "POSITIONS", "CALL", "CALLS", "PUT",
    "PUTS", "AT", "FOR", "IN", "ON", "NOW", "AGAIN", "BACK", "LOTTO",
    "RISK", "EXTREME", "AVG", "AVERAGE", "DOWN", "DCA",
}


def parse_contextual_entry(message: str) -> Optional[dict]:
    """Parse a re-entry/re-add that intentionally relies on an open position.

    This fallback is deliberately narrow: the action must lead the message, a
    concrete option contract and executable premium must be present, and the
    message may not be a watch/no-entry notice. Expiration is resolved later
    from broker/local position state rather than guessed from the message date.
    """
    raw_text = str(message or "").strip()
    if not raw_text or not CONTEXTUAL_ENTRY_RE.search(raw_text):
        return None
    if WATCH_BLOCK_RE.search(raw_text):
        return None

    contract = OPTION_RE.search(raw_text)
    if not contract:
        return None

    strike = contract.group("strike") or contract.group("strike_word")
    kind = contract.group("kind") or contract.group("kind_word")
    ticker = _extract_context_ticker(raw_text, contract.start())
    price = _extract_price(raw_text)
    if not ticker or price is None:
        return None

    return {
        "alert_type": "buy",
        "ticker": ticker,
        "strike": float(strike),
        "option_type": "CALL" if kind.upper().startswith("C") else "PUT",
        "expiration": None,
        "entry_price": float(price),
        "sell_percentage": None,
        "_requires_position_context": True,
        "_context_reason": "contextual re-entry omitted expiration",
    }


async def resolve_contextual_expiration(
    parsed: dict,
    *,
    resolver: Optional[Callable[..., Any]] = None,
    include_simulated: bool = False,
) -> tuple[dict, str]:
    """Resolve a context-dependent entry against exactly one expiration.

    Returns ``(parsed, reason)``. ``reason`` is empty on success. No broker order
    should be attempted when a non-empty reason is returned.
    """
    if not parsed.get("_requires_position_context"):
        return parsed, ""

    if resolver is None:
        result = await _resolve_from_positions(parsed, include_simulated=include_simulated)
    else:
        result = resolver(parsed, include_simulated=include_simulated)
        if inspect.isawaitable(result):
            result = await result

    if isinstance(result, str):
        result = {"expiration": result}
    if not isinstance(result, dict):
        result = {}

    expiration = str(result.get("expiration") or "").strip()
    if not expiration:
        reason = str(result.get("reason") or "no unique matching open position").strip()
        return parsed, reason

    resolved = dict(parsed)
    resolved["expiration"] = expiration
    resolved.pop("_requires_position_context", None)
    resolved["_context_resolved_from_positions"] = True
    if result.get("position_ids"):
        resolved["_context_position_ids"] = list(result["position_ids"])
    return resolved, ""


async def _resolve_from_positions(parsed: dict, *, include_simulated: bool) -> dict:
    try:
        from database import get_db

        db = get_db()
        positions = await db.get_positions("open")
        positions += await db.get_positions("partial")
    except Exception as exc:
        return {"reason": f"position lookup failed: {exc}"}

    matches = []
    for position in positions:
        if not include_simulated and _is_simulated(position):
            continue
        if _norm(position.get("ticker")) != _norm(parsed.get("ticker")):
            continue
        if not _float_equal(position.get("strike"), parsed.get("strike")):
            continue
        if _norm(position.get("option_type")) != _norm(parsed.get("option_type")):
            continue
        if int(float(position.get("remaining_quantity") or position.get("quantity") or 0)) <= 0:
            continue
        expiration = str(position.get("expiration") or "").strip()
        if expiration:
            matches.append(position)

    by_expiration: dict[str, list[dict]] = {}
    for position in matches:
        by_expiration.setdefault(str(position.get("expiration")).strip(), []).append(position)

    if not by_expiration:
        return {
            "reason": (
                "no matching open position for "
                f"{parsed.get('ticker')} {parsed.get('strike')} {parsed.get('option_type')}"
            )
        }
    if len(by_expiration) > 1:
        return {
            "reason": (
                "matching open positions span multiple expirations: "
                f"{sorted(by_expiration)}"
            )
        }

    expiration, positions_for_expiration = next(iter(by_expiration.items()))
    return {
        "expiration": expiration,
        "position_ids": [
            str(position.get("id"))
            for position in positions_for_expiration
            if position.get("id") is not None
        ],
    }


def _extract_context_ticker(message: str, contract_start: int) -> Optional[str]:
    prefix = message[:contract_start].upper()
    cash_tickers = re.findall(r"\$([A-Z]{1,6})\b", prefix)
    if cash_tickers:
        return cash_tickers[-1]

    tokens = re.findall(r"\b[A-Z]{1,6}\b", prefix)
    for token in reversed(tokens):
        if token not in CONTEXT_TICKER_STOPWORDS:
            return token
    return None


def _is_simulated(position: dict) -> bool:
    broker = str(position.get("broker") or "").lower()
    return bool(position.get("simulated")) or broker.endswith(":paper_shadow")


def _float_equal(left: Any, right: Any) -> bool:
    try:
        return abs(float(left) - float(right)) < 0.001
    except (TypeError, ValueError):
        return False


def _norm(value: Any) -> str:
    return str(value or "").strip().upper()
