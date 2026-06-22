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
    re.compile(
        r"\$(?P<price>\d+(?:\.\d+)?)\s*(?:ENTRY|ENTRIES|FILL|FILLS|AVG|AVERAGE)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\$\.(?P<cents>\d{1,2})\b", re.IGNORECASE),
)
ACTION_TICKER_RE = re.compile(
    r"\b(?:BTO|STC|BUY|BOUGHT|SELL|SOLD|TRIM|CLOSE|EXIT|LONG|ENTRY)\s+\$?(?P<ticker>[A-Z]{1,6})\b",
    re.IGNORECASE,
)
CASH_TICKER_RE = re.compile(r"\$(?P<ticker>[A-Z]{1,6})\b")
TICKER_OPTION_SIDE_RE = re.compile(
    r"\b(?:ON\s+)?\$?(?P<ticker>[A-Z]{1,6})\s+(?P<kind>CALLS?|PUTS?)\b",
    re.IGNORECASE,
)
EXIT_START_RE = re.compile(
    r"^\s*(?:STC|SELL(?:\s+TO\s+CLOSE)?|SELLING|SOLD|TRIM(?:MING)?|"
    r"CLOSE|CLOSING|EXIT|EXITING|OUT|STOPPED\s+OUT)\b",
    re.IGNORECASE,
)
EXIT_ACTION_RE = re.compile(
    r"\b(?:STC|SELL\s+TO\s+CLOSE|TRIM(?:MING)?|SELL\s+(?:HALF|MAJORITY|\d{1,3}%))\b",
    re.IGNORECASE,
)
TICKER_STOPWORDS = {
    *(keyword.upper() for keyword in BUY_KEYWORDS + SELL_KEYWORDS + AVG_DOWN_KEYWORDS),
    "AT",
    "BE",
    "DCA",
    "FINAL",
    "FULLY",
    "HERE",
    "INITIALS",
    "MAJORITY",
    "MOST",
    "OF",
    "OFF",
    "ON",
    "OUT",
    "POSITION",
    "SECURED",
    "THOSE",
    "WATCH",
    "ZONE",
}


def parse_alert(message: str) -> Optional[dict]:
    """Parse a Discord options alert into a normalized trade signal."""
    try:
        text = " ".join(message.strip().split())

        if _contains_keyword(text, AVG_DOWN_KEYWORDS):
            return _parse_contract_alert(text, "average_down", require_price=False)

        if _contains_keyword(text, SELL_KEYWORDS) and _looks_like_exit_alert(text):
            return _parse_sell_alert(text)

        if _contains_keyword(text, BUY_KEYWORDS):
            return _parse_contract_alert(text, "buy", require_price=True)

        return _parse_contract_alert(text, "buy", require_price=True)
    except Exception as exc:
        logger.error("Error parsing alert: %s", exc)
        return None


def _parse_sell_alert(message: str) -> Optional[dict]:
    result = _parse_contract_alert(message, "sell", require_price=False, require_contract=False)
    if not result:
        return None

    if _contains_keyword(message, ("TRIM", "TRIMMING")):
        result["alert_type"] = "trim"
    elif _contains_keyword(message, ("CLOSE", "CLOSING", "EXIT", "EXITING")):
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
    if option_type is None and alert_type in {"sell", "trim", "close"}:
        option_type = _extract_option_side_without_strike(message)
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
        ticker = _normalize_ticker(cash_match.group("ticker"))
        if ticker:
            return ticker

    option_side_match = _first_valid_ticker_option_side(message)
    if option_side_match:
        return option_side_match

    action_match = ACTION_TICKER_RE.search(message)
    if action_match:
        ticker = _normalize_ticker(action_match.group("ticker"))
        if ticker:
            return ticker

    # Fallback: use the token before the first option contract.
    option_match = OPTION_RE.search(message)
    if option_match:
        prefix = message[: option_match.start()].strip()
        tokens = re.findall(r"\b[A-Z]{1,6}\b", prefix.upper())
        for token in reversed(tokens):
            ticker = _normalize_ticker(token)
            if ticker:
                return ticker
    return None


def _extract_option_contract(message: str) -> tuple[Optional[float], Optional[str]]:
    match = OPTION_RE.search(message)
    if not match:
        return None, None

    strike = match.group("strike") or match.group("strike_word")
    kind = match.group("kind") or match.group("kind_word")
    option_type = "CALL" if kind.upper().startswith("C") else "PUT"
    return float(strike), option_type


def _extract_option_side_without_strike(message: str) -> Optional[str]:
    match = TICKER_OPTION_SIDE_RE.search(message)
    if not match or not _normalize_ticker(match.group("ticker")):
        return None
    kind = match.group("kind")
    return "CALL" if kind.upper().startswith("C") else "PUT"


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

    match = re.search(
        r"\b(?:SELL|TRIM|STC|SCALE|OUT|EXIT|CLOSE)\s*(?:OUT\s*)?(\d{1,3})\s*%",
        upper,
    )
    if not match:
        match = re.search(
            r"\b(\d{1,3})\s*%\s*(?:POSITION\s+)?(?:SOLD|SECURED|OUT|TRIM|CLOSED|EXITED)\b",
            upper,
        )
    if match:
        return min(100.0, max(1.0, float(match.group(1))))

    half_terms = ("HALF", "1/2", "ONE HALF")
    if _contains_keyword(message, half_terms):
        return 50.0

    quarter_terms = ("QUARTER", "1/4")
    if _contains_keyword(message, quarter_terms):
        return 25.0

    if _contains_keyword(message, ("MAJORITY", "MOST")):
        return 75.0

    if _contains_keyword(message, ("TRIM", "TRIMMING", "PARTIAL", "INITIALS")):
        return 50.0

    if _contains_keyword(message, ("ALL", "CLOSE", "CLOSING", "EXIT", "EXITING", "FULLY")):
        return 100.0

    return 100.0


def _looks_like_exit_alert(message: str) -> bool:
    """Return True only for actionable exit language, not market commentary."""
    return bool(EXIT_START_RE.search(message) or EXIT_ACTION_RE.search(message))


def _first_valid_ticker_option_side(message: str) -> Optional[str]:
    for match in TICKER_OPTION_SIDE_RE.finditer(message):
        ticker = _normalize_ticker(match.group("ticker"))
        if ticker:
            return ticker
    return None


def _normalize_ticker(value: str) -> Optional[str]:
    ticker = str(value or "").strip().upper().lstrip("$")
    if not re.fullmatch(r"[A-Z]{1,6}", ticker):
        return None
    if ticker in TICKER_STOPWORDS:
        return None
    return ticker


def _contains_keyword(message: str, keywords: tuple[str, ...]) -> bool:
    return any(_keyword_regex(keyword).search(message) for keyword in keywords)


def _keyword_regex(keyword: str) -> re.Pattern:
    parts = [re.escape(part) for part in str(keyword).strip().split()]
    body = r"\s+".join(parts)
    return re.compile(rf"(?<![A-Z0-9]){body}(?![A-Z0-9])", re.IGNORECASE)


def calculate_pnl(entry_price: float, current_price: float, quantity: int) -> float:
    """Calculate options P&L, where one contract controls 100 shares."""
    return (current_price - entry_price) * quantity * 100
