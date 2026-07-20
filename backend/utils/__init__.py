import logging
import re
from datetime import datetime
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
    "ENTERED",
    "LONG",
    "OPENING",
    "RE-ENTER",
    "RE-ENTERING",
    "RE-ENTERED",
    "RE-ENTRY",
    "RE-ADD",
    "RE-ADDING",
    "RE-ADDED",
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
ZERO_DTE_RE = re.compile(r"\b0DTE\b", re.IGNORECASE)
PRICE_PATTERNS = (
    re.compile(r"@\s*(?:A\s+)?\$?(?P<price>\d+(?:\.\d+)?)", re.IGNORECASE),
    # Handle shorthand option premiums before any label-based scan so a phrase
    # such as ``AT A $.20 FILL`` cannot accidentally capture a later target.
    re.compile(r"\$\.(?P<cents>\d{1,2})\b", re.IGNORECASE),
    re.compile(
        r"\b(?:ENTRY|PRICE|AT|FILL|IN)\s*:?\s*(?:A\s+)?@\s*\$?"
        r"(?P<price>\d+(?:\.\d+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:ENTRY|PRICE|AT|FILL|IN)\s*:?\s*(?:A\s+)?\$?"
        r"(?P<price>\d+(?:\.\d+)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![\d.])\$?(?P<price>\d+(?:\.\d+)?)\s*(?:ENTRY|FILL)\b",
        re.IGNORECASE,
    ),
)
ACTION_TICKER_RE = re.compile(
    r"\b(?:BTO|BUY\s+TO\s+OPEN|BUYING|BOUGHT|BUY|ENTERING|ENTERED|LONG|OPENING|"
    r"RE[-\s]?ENTER(?:ING|ED)?|RE[-\s]?ENTRY|RE[-\s]?ADD(?:ING|ED)?)\s+"
    r"\$?(?P<ticker>[A-Z]{1,6})\b",
    re.IGNORECASE,
)
CASH_TICKER_RE = re.compile(r"\$(?P<ticker>[A-Z]{1,6})\b")

WATCH_BLOCK_RE = re.compile(
    r"\b(?:ENTRY\s+NOT\s+VALID|NO\s+ENTRY(?:\s+YET)?|ON\s+WATCH|"
    r"WATCHING\s+FOR|POSSIBLE\s+RELOAD)\b",
    re.IGNORECASE,
)
LEADING_BUY_RE = re.compile(
    r"^\s*(?:BTO|BUY\s+TO\s+OPEN|BUYING|BOUGHT|BUY|ENTERING|ENTERED|LONG|OPENING|"
    r"RE[-\s]?ENTER(?:ING|ED)?|RE[-\s]?ENTRY|RE[-\s]?ADD(?:ING|ED)?)\b",
    re.IGNORECASE,
)
LEADING_AVG_DOWN_RE = re.compile(
    r"^\s*(?:AVERAGE\s+DOWN|AVG\s+DOWN|AVERAGING|ADD\s+TO|ADDING)\b",
    re.IGNORECASE,
)
STRUCTURED_ENTRY_RE = re.compile(r"^\s*\$[A-Z]{1,6}\b", re.IGNORECASE)
EXIT_CLAUSE_RE = re.compile(
    r"\b(?P<action>STC|SELL\s+TO\s+CLOSE|SELLING|SOLD|SELL|TRIMMING|TRIM|"
    r"CLOSING|CLOSED|CLOSE|EXITING|EXITED|EXIT)\b"
    r"\s+(?:(?P<size>\d{1,3}\s*%|ALL|MOST|HALF|QUARTER|1/2|1/4)\s+)?"
    r"(?P<ticker>\$?[A-Za-z]{1,6})\b",
    re.IGNORECASE,
)
EXIT_TICKER_STOPWORDS = {
    "OFF",
    "NOW",
    "AT",
    "HERE",
    "THERE",
    "THOSE",
    "THAT",
    "THIS",
    "OTHER",
    "OTHERS",
    "MOST",
    "ALL",
    "SLOWLY",
    "OUT",
    "IN",
    "ABOVE",
    "BELOW",
    "AROUND",
    "BASED",
    "THE",
    "TO",
    "FOR",
    "WHILE",
    "AS",
    "AND",
    "BEFORE",
    "NEAR",
    "GAPS",
    "FULLY",
    "ZONE",
    "IT",
    "ON",
    "UP",
    "DOWN",
    "CALLS",
    "PUTS",
    "POSITION",
    "POSITIONS",
}


def parse_alert(message: str, created_at=None) -> Optional[dict]:
    """Parse a Discord options alert into a normalized trade signal.

    ``created_at`` is optional and is used only to resolve 0DTE contracts to the
    message's calendar date. Discord supplies an aware datetime; tests and
    preview callers may also pass an ISO-8601 string.
    """
    try:
        raw_text = str(message or "").strip()
        text = " ".join(raw_text.split())
        if not text:
            return None

        is_structured_entry = bool(STRUCTURED_ENTRY_RE.search(raw_text)) and bool(
            _keyword_regex("ENTRY").search(raw_text)
        )
        is_leading_buy = bool(LEADING_BUY_RE.search(raw_text))

        # A concrete entry at the start of the alert takes precedence over
        # narrative words such as "sell", "sold off", or "avg down" in the
        # analyst's trade notes.
        if (is_structured_entry or is_leading_buy) and not WATCH_BLOCK_RE.search(raw_text):
            parsed = _parse_contract_alert(
                text,
                "buy",
                require_price=True,
                created_at=created_at,
            )
            if parsed:
                return parsed

        # Average-down actions must be explicit at the start of the message.
        # Merely mentioning DCA/AVG DOWN in an entry's risk notes is not a new
        # average-down order.
        if LEADING_AVG_DOWN_RE.search(raw_text):
            parsed = _parse_contract_alert(
                text,
                "average_down",
                require_price=False,
                created_at=created_at,
            )
            if parsed:
                return parsed

        exit_clause = _find_explicit_exit_clause(raw_text)
        if exit_clause:
            match, ticker, clause_text = exit_clause
            parsed = _parse_contract_alert(
                clause_text,
                "sell",
                require_price=False,
                require_contract=False,
                ticker_override=ticker,
                created_at=created_at,
            )
            if parsed:
                action = match.group("action").upper()
                if "TRIM" in action:
                    parsed["alert_type"] = "trim"
                elif "CLOSE" in action or "EXIT" in action:
                    parsed["alert_type"] = "close"
                parsed["sell_percentage"] = _extract_sell_percentage(clause_text)
                return parsed

        # Conservative fallback for compact entry alerts that contain a full
        # contract, expiration, and executable price but no standard action.
        if not WATCH_BLOCK_RE.search(raw_text):
            return _parse_contract_alert(
                text,
                "buy",
                require_price=True,
                created_at=created_at,
            )
        return None
    except Exception as exc:
        logger.error("Error parsing alert: %s", exc)
        return None


def _parse_contract_alert(
    message: str,
    alert_type: str,
    *,
    require_price: bool,
    require_contract: bool = True,
    ticker_override: Optional[str] = None,
    created_at=None,
) -> Optional[dict]:
    ticker = ticker_override or _extract_ticker(message)
    strike, option_type = _extract_option_contract(message)
    expiration = _extract_expiration(message, created_at=created_at)
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


def _find_explicit_exit_clause(message: str):
    for match in EXIT_CLAUSE_RE.finditer(message):
        raw_ticker = match.group("ticker")
        ticker = raw_ticker.lstrip("$")
        if not raw_ticker.startswith("$") and ticker != ticker.upper():
            continue

        clause_text = message[match.start():]
        contract_match = OPTION_RE.search(clause_text)
        leading_action = not message[: match.start()].strip(" \t\n\r([{.-")

        # Common prose words are never tickers unless the same concrete exit
        # clause also names an option contract. This preserves valid symbols
        # such as NOW while rejecting "sold off", "sell at", and "trim slowly".
        if ticker.upper() in EXIT_TICKER_STOPWORDS and not contract_match:
            continue
        if contract_match or leading_action:
            return match, ticker.upper(), clause_text
    return None


def _extract_ticker(message: str) -> Optional[str]:
    cash_match = CASH_TICKER_RE.search(message)
    if cash_match:
        return cash_match.group("ticker").upper()

    action_match = ACTION_TICKER_RE.search(message)
    if action_match:
        return action_match.group("ticker").upper()

    option_match = OPTION_RE.search(message)
    if option_match:
        prefix = message[: option_match.start()].strip()
        tokens = re.findall(r"\b[A-Z]{1,6}\b", prefix.upper())
        ignored = set(BUY_KEYWORDS + SELL_KEYWORDS + AVG_DOWN_KEYWORDS)
        for token in reversed(tokens):
            if token not in ignored and token not in EXIT_TICKER_STOPWORDS:
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


def _extract_expiration(message: str, *, created_at=None) -> Optional[str]:
    match = EXPIRATION_RE.search(message)
    if match:
        return match.group("expiration")
    if not ZERO_DTE_RE.search(message):
        return None

    timestamp = _coerce_datetime(created_at)
    if timestamp is None:
        return None
    return f"{timestamp.month}/{timestamp.day}/{timestamp.year}"


def _coerce_datetime(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
        for fmt in (
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y",
        ):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue
    return None


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
    if _contains_keyword(message, ("ALL", "CLOSE", "CLOSING", "EXIT", "EXITING")):
        return 100.0

    match = re.search(r"\b(?:SELL|TRIM|STC|SOLD)?\s*(\d{1,3})\s*%", upper)
    if match:
        return min(100.0, max(1.0, float(match.group(1))))

    half_terms = ("HALF", "1/2", "ONE HALF")
    if _contains_keyword(message, half_terms):
        return 50.0

    quarter_terms = ("QUARTER", "1/4")
    if _contains_keyword(message, quarter_terms):
        return 25.0

    return 100.0


def _contains_keyword(message: str, keywords: tuple[str, ...]) -> bool:
    return any(_keyword_regex(keyword).search(message) for keyword in keywords)


def _keyword_regex(keyword: str) -> re.Pattern:
    parts = [re.escape(part) for part in str(keyword).strip().split()]
    body = r"\s+".join(parts)
    return re.compile(rf"(?<![A-Z0-9]){body}(?![A-Z0-9])", re.IGNORECASE)


def calculate_pnl(entry_price: float, current_price: float, quantity: int) -> float:
    """Calculate options P&L, where one contract controls 100 shares."""
    return (current_price - entry_price) * quantity * 100
