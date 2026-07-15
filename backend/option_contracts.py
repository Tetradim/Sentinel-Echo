"""Canonical option-contract identifiers used by every live broker adapter."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


_EXPIRATION_FORMATS = (
    "%m/%d/%y",
    "%m/%d/%Y",
    "%Y-%m-%d",
    "%y%m%d",
    "%Y%m%d",
)
_OCC_PATTERN = re.compile(r"^([A-Z0-9]+?)(\d{6})([CP])(\d{8})$")


def parse_expiration(value: str) -> datetime:
    raw = str(value or "").strip()
    for fmt in _EXPIRATION_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Unsupported option expiration {value!r}; expected MM/DD/YY, "
        "MM/DD/YYYY, YYYY-MM-DD, YYMMDD, or YYYYMMDD"
    )


def build_occ_symbol(
    underlying: str,
    expiration: str,
    option_type: str,
    strike: float,
) -> str:
    root = re.sub(r"[^A-Z0-9]", "", str(underlying or "").upper())
    if not root:
        raise ValueError("Option underlying is required")

    right_raw = str(option_type or "").strip().upper()
    if right_raw in {"CALL", "C"}:
        right = "C"
    elif right_raw in {"PUT", "P"}:
        right = "P"
    else:
        raise ValueError(f"Unsupported option type: {option_type!r}")

    try:
        strike_decimal = Decimal(str(strike))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid option strike: {strike!r}") from exc
    if strike_decimal <= 0:
        raise ValueError("Option strike must be positive")

    strike_millis = int(
        (strike_decimal * Decimal("1000")).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    if strike_millis > 99_999_999:
        raise ValueError(f"Option strike is too large for OCC encoding: {strike}")

    expiry = parse_expiration(expiration).strftime("%y%m%d")
    return f"{root}{expiry}{right}{strike_millis:08d}"


def parse_occ_symbol(symbol: str) -> dict:
    raw = re.sub(r"\s+", "", str(symbol or "").upper())
    match = _OCC_PATTERN.fullmatch(raw)
    if not match:
        raise ValueError(f"Invalid OCC option symbol: {symbol!r}")
    underlying, expiry_yymmdd, right, strike_raw = match.groups()
    expiry = datetime.strptime(expiry_yymmdd, "%y%m%d")
    return {
        "occ_symbol": raw,
        "ticker": underlying,
        "expiration": expiry.strftime("%Y-%m-%d"),
        "option_type": "CALL" if right == "C" else "PUT",
        "strike": float(Decimal(strike_raw) / Decimal("1000")),
    }
