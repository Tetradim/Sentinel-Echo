import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


BUY_KEYWORDS = (
    "BTO",
    "BUY TO OPEN",
    "BUYING",
    "BOUGHT",
    "BUY",
    "ENTRY",
    "ENTERING",
    "LONG",
    "OPENING",
)
SELL_KEYWORDS = (
    "STC",
    "SELL TO CLOSE",
    "SELLING",
    "SOLD",
    "SELL",
    "TRIM",
    "CLOSE",
    "EXIT",
    "OUT",
)
AVG_DOWN_KEYWORDS = (
    "AVERAGE DOWN",
    "AVG DOWN",
    "AVERAGING",
    "ADD TO",
    "ADDING",
)

OPTION_RE = re.compile(
    r"(?:^|\s)\$?(?P<strike>\d+(?:\.\d+)?)(?P<kind>[CP])\b|"
    r"(?:^|\s)\$?(?P<strike_word>\d+(?:\.\d+)?)\s*(?P<kind_word>CALLS?|PUTS?)\b",
    re.IGNORECASE,
)
EXPIRATION_RE = re.compile(r"\b(?P<expiration>\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b")
PRICE_PATTERNS = (
    re.compile(r"@\s*\$?(?P<price>\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\b(?:ENTRY|PRICE|AT|FILL)\s*:?\s*\$?(?P<price>\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\$\.(?P<cents>\d{1,2})\b", re.IGNORECASE),
)
ACTION_TICKER_RE = re.compile(
    r"\b(?:BTO|STC|BUY|BOUGHT|SELL|SOLD|TRIM|CLOSE|EXIT|LONG|ENTRY)\s+\$?(?P<ticker>[A-Z]{1,6})\b",
    re.IGNORECASE,
)
CASH_TICKER_RE = re.compile(r"\$(?P<ticker>[A-Z]{1,6})\b")


def parse_alert(message: str) -> Optional[dict]:
    """Parse a Discord options alert into a normalized trade signal."""
    try:
        text = " ".join(message.strip().split())
        upper = text.upper()

        if any(keyword in upper for keyword in AVG_DOWN_KEYWORDS):
            return _parse_contract_alert(text, "average_down", require_price=False)

        if any(keyword in upper for keyword in SELL_KEYWORDS):
            return _parse_sell_alert(text)

        if any(keyword in upper for keyword in BUY_KEYWORDS):
            return _parse_contract_alert(text, "buy", require_price=True)

        return _parse_contract_alert(text, "buy", require_price=True)
    except Exception as exc:
        logger.error("Error parsing alert: %s", exc)
        return None


def _parse_sell_alert(message: str) -> Optional[dict]:
    result = _parse_contract_alert(message, "sell", require_price=False, require_contract=False)
    if not result:
        return None

    upper = message.upper()
    if "TRIM" in upper:
        result["alert_type"] = "trim"
    elif "CLOSE" in upper or "EXIT" in upper:
        result["alert_type"] = "close"

    result["sell_percentage"] = _extract_sell_percentage(message)
    return result


def _parse_contract_alert(
    message: str,
    alert_type: str,
    *,
    require_price: bool,
    require_contract: bool = True,
) -> Optional[dict]:
    ticker = _extract_ticker(message)
    strike, option_type = _extract_option_contract(message)
    expiration = _extract_expiration(message)
    price = _extract_price(message)

    if not ticker:
        return None
    if require_contract and (strike is None or option_type is None or not expiration):
        return None
    if require_price and price is None:
        return None

    return {
        "alert_type": alert_type,
        "ticker": ticker,
        "strike": strike,
        "option_type": option_type,
        "expiration": expiration,
        "entry_price": price,
        "sell_percentage": None,
    }


def _extract_ticker(message: str) -> Optional[str]:
    cash_match = CASH_TICKER_RE.search(message)
    if cash_match:
        return cash_match.group("ticker").upper()

    action_match = ACTION_TICKER_RE.search(message)
    if action_match:
        return action_match.group("ticker").upper()

    # Fallback: use the token before the first option contract.
    option_match = OPTION_RE.search(message)
    if option_match:
        prefix = message[: option_match.start()].strip()
        tokens = re.findall(r"\b[A-Z]{1,6}\b", prefix.upper())
        ignored = set(BUY_KEYWORDS + SELL_KEYWORDS + AVG_DOWN_KEYWORDS)
        for token in reversed(tokens):
            if token not in ignored:
                return token
    return None


def _extract_option_contract(message: str) -> tuple[Optional[float], Optional[str]]:
    match = OPTION_RE.search(message)
    if not match:
        return None, None

    strike = match.group("strike") or match.group("strike_word")
    kind = match.group("kind") or match.group("kind_word")
    option_type = "CALL" if kind.upper().startswith("C") else "PUT"
    return float(strike), option_type


def _extract_expiration(message: str) -> Optional[str]:
    match = EXPIRATION_RE.search(message)
    return match.group("expiration") if match else None


def _extract_price(message: str) -> Optional[float]:
    for pattern in PRICE_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        if "cents" in match.groupdict() and match.group("cents") is not None:
            return float(f"0.{match.group('cents')}")
        return float(match.group("price"))
    return None


def _extract_sell_percentage(message: str) -> float:
    upper = message.upper()
    if "ALL" in upper or "CLOSE" in upper or "EXIT" in upper:
        return 100.0

    match = re.search(r"\b(?:SELL|TRIM|STC)?\s*(\d{1,3})\s*%", upper)
    if match:
        return min(100.0, max(1.0, float(match.group(1))))

    half_terms = ("HALF", "1/2", "ONE HALF")
    if any(term in upper for term in half_terms):
        return 50.0

    quarter_terms = ("QUARTER", "1/4")
    if any(term in upper for term in quarter_terms):
        return 25.0

    return 100.0


def calculate_pnl(entry_price: float, current_price: float, quantity: int) -> float:
    """Calculate options P&L, where one contract controls 100 shares."""
    return (current_price - entry_price) * quantity * 100
