from __future__ import annotations

import re
from datetime import date
from typing import Any

from utils import normalize_expiration_for_order


ALPACA_OPTION_SYMBOL_RE = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$")


def canonical_expiration_yyyymmdd(expiration: Any) -> str:
    """Return YYYY-MM-DD when expiration can be normalized, otherwise a stable string."""
    text = str(expiration or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    if re.fullmatch(r"\d{8}", text):
        year = int(text[:4])
        month = int(text[4:6])
        day = int(text[6:8])
        return _format_date(year, month, day) or text
    if re.fullmatch(r"\d{6}", text):
        year = 2000 + int(text[:2])
        month = int(text[2:4])
        day = int(text[4:6])
        return _format_date(year, month, day) or text

    normalized = normalize_expiration_for_order(text, roll_forward=False)
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", str(normalized or ""))
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        if year < 100:
            year += 2000
        return _format_date(year, month, day) or text
    return text


def contract_position_id(
    broker: Any,
    ticker: Any,
    strike: Any,
    option_type: Any,
    expiration: Any,
) -> str:
    broker_token = _token(broker, fallback="broker")
    ticker_token = _token(ticker, fallback="ticker")
    expiration_token = canonical_expiration_yyyymmdd(expiration).replace("-", "")
    expiration_token = expiration_token[2:] if len(expiration_token) == 8 else _token(expiration_token, fallback="exp")
    option_token = "c" if str(option_type or "").upper().startswith("C") else "p"
    strike_token = _strike_token(strike)
    return f"position-{broker_token}-{ticker_token}-{expiration_token}-{option_token}-{strike_token}"


def same_option_contract(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        str(left.get("ticker") or "").strip().upper() == str(right.get("ticker") or "").strip().upper()
        and abs(_float(left.get("strike")) - _float(right.get("strike"))) < 0.001
        and _option_side(left.get("option_type")) == _option_side(right.get("option_type"))
        and canonical_expiration_yyyymmdd(left.get("expiration"))
        == canonical_expiration_yyyymmdd(right.get("expiration"))
    )


def parse_alpaca_option_symbol(symbol: Any) -> dict[str, Any] | None:
    match = ALPACA_OPTION_SYMBOL_RE.fullmatch(str(symbol or "").strip().upper())
    if not match:
        return None
    ticker, expiry, side, strike_raw = match.groups()
    expiration = canonical_expiration_yyyymmdd(expiry)
    return {
        "ticker": ticker,
        "expiration": expiration,
        "option_type": "CALL" if side == "C" else "PUT",
        "strike": int(strike_raw) / 1000,
    }


def _format_date(year: int, month: int, day: int) -> str:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _option_side(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("C"):
        return "CALL"
    if text.startswith("P"):
        return "PUT"
    return text


def _strike_token(value: Any) -> str:
    amount = _float(value)
    if amount.is_integer():
        return str(int(amount))
    return f"{amount:.3f}".rstrip("0").rstrip(".").replace(".", "_")


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _token(value: Any, *, fallback: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return token or fallback
