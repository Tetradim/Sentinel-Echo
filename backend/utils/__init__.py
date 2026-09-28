import logging
import re
from datetime import date
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
    "DCA",
    "AVERAGE DOWN",
    "AVG DOWN",
    "AVERAGING",
    "ADD TO",
    "ADDING",
)

EXPLICIT_AVG_DOWN_RE = re.compile(
    r"\b(?:"
    r"DCA(?:['\u2019]D|ED)|"
    r"AVERAGED\s+DOWN|"
    r"FILLED\s+ADDS?|"
    r"ADDED(?:\s+MORE)?|"
    r"(?:DCA|AVERAGE\s+DOWN|AVG\s+DOWN|ADDING)\s+(?:HERE|NOW|AT|@)"
    r")\b",
    re.IGNORECASE,
)
DEFERRED_AVG_DOWN_RE = re.compile(
    r"\b(?:"
    r"DCA\s+ROOM|"
    r"LEAVE\b.{0,40}\bDCA|"
    r"LOOKING\b.{0,80}\b(?:TO\s+DCA|DOWNSIDE\s+TO\s+DCA|TO\s+ADD)|"
    r"(?:WILL|MAY|MIGHT|COULD|CAN)\s+(?:DCA|ADD)|"
    r"DCA\s+(?:UPON|IF|WHEN|AFTER)|"
    r"DCA\b.{0,40}\bBACKTESTS?|"
    r"ADD\s+ON\s+PULLBACKS?|"
    r"ADDING\s+TO\s+(?:THE\s+)?SETUP"
    r")\b",
    re.IGNORECASE,
)
NEGATED_AVG_DOWN_RE = re.compile(
    r"\b(?:"
    r"NO\s+(?:MORE\s+)?(?:DCA|ADDS?|ADDING|AVERAG(?:E|ING)\s+DOWN)|"
    r"(?:DO\s+NOT|DON['\u2019]?T|NEVER)\s+(?:DCA|ADD|ADDING|AVERAGE\s+DOWN)|"
    r"WITHOUT\s+(?:DCA|ADDS?|ADDING|AVERAGING\s+DOWN)"
    r")\b",
    re.IGNORECASE,
)
EXIT_ALERT_TYPES = {"sell", "trim", "close"}

OPTION_RE = re.compile(
    r"(?:^|\s)\$?(?P<strike>\d+(?:\.\d+)?)(?P<kind>[CP])\b|"
    r"(?:^|\s)\$?(?P<strike_word>\d+(?:\.\d+)?)\s*(?P<kind_word>CALLS?|PUTS?)\b",
    re.IGNORECASE,
)
EXPIRATION_RE = re.compile(r"\b(?P<expiration>\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b")
MARKET_PRICE_RE = re.compile(r"@\s*\$?\s*M(?:ARKET)?\b", re.IGNORECASE)
PRICE_PATTERNS = (
    re.compile(r"@\s*\$?\.(?P<cents>\d{1,2})\b", re.IGNORECASE),
    re.compile(r"@\s*\$?(?P<price>\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(
        r"\$\.(?P<cents>\d{1,2})\s*(?:ENTRY|ENTRIES|FILL|FILLS|AVG|AVERAGE)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\$(?P<price>\d+(?:\.\d+)?)\s*(?:ENTRY|ENTRIES|FILL|FILLS|AVG|AVERAGE)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:ENTRY|PRICE|AT|FILL)\s*:?\s*\$?\.(?P<cents>\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\b(?:ENTRY|PRICE|AT|FILL)\s*:?\s*\$?(?P<price>\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\$\.(?P<cents>\d{1,2})\b", re.IGNORECASE),
)
ACTION_TICKER_RE = re.compile(
    r"\b(?:BTO|STC|BUY|BOUGHT|SELL|SOLD|TRIM|CLOSE|EXIT|LONG|ENTRY)"
    r"(?:\s+\d+)?\s+(?P<ticker>\$?[A-Z]{1,6})\b",
    re.IGNORECASE,
)
CASH_TICKER_RE = re.compile(r"\$(?P<ticker>[A-Z]{1,6})\b")
TICKER_OPTION_SIDE_RE = re.compile(
    r"\b(?:ON\s+)?\$?(?P<ticker>[A-Z]{1,6})\s+(?P<kind>CALLS?|PUTS?)\b",
    re.IGNORECASE,
)
TRADE_ECHO_CONTRACT_RE = re.compile(
    r"\b(?:OPENED|PARTIALLY\s+CLOSED|CLOSED)\s+\d+\s+\$?(?P<ticker>[A-Z]{1,6})\s+"
    r"\d+(?:\.\d+)?[CP]\b",
    re.IGNORECASE,
)
TRADE_ECHO_OPEN_RE = re.compile(r"\bOPENED\s+\d+\s+\$?[A-Z]{1,6}\s+\d+(?:\.\d+)?[CP]\b", re.IGNORECASE)
TRADE_ECHO_EXIT_RE = re.compile(
    r"\b(?:PARTIALLY\s+CLOSED|CLOSED)\s+\d+\s+\$?[A-Z]{1,6}\s+\d+(?:\.\d+)?[CP]\b",
    re.IGNORECASE,
)
EXIT_START_RE = re.compile(
    r"^\s*(?:STC|SELL(?:\s+TO\s+CLOSE)?|SELLING|SOLD|TRIM(?:MING)?|"
    r"CLOSE|CLOSING|EXIT|EXITING|FULLY\s+OUT|OUT|STOPPED\s+OUT)\b",
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
    "FOR",
    "FULL",
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
    "SLOWLY",
    "NOW",
    "SECURED",
    "THOSE",
    "WATCH",
    "ZONE",
}


def parse_alert(message: str) -> Optional[dict]:
    """Parse a Discord options alert into a normalized trade signal."""
    from structured_alert_cards import parse_card

    card = parse_card(message)
    if card.recognized:
        return card.parsed
    try:
        text = " ".join(_strip_forwarded_alert_header(message).split())

        if TRADE_ECHO_EXIT_RE.search(text):
            return _parse_sell_alert(text)

        if TRADE_ECHO_OPEN_RE.search(text):
            return _parse_contract_alert(text, "buy", require_price=True)

        if is_actionable_average_down_alert(text):
            return _parse_contract_alert(text, "average_down", require_price=False)

        if _contains_keyword(text, SELL_KEYWORDS) and _looks_like_exit_alert(text):
            return _parse_sell_alert(text)

        if _contains_keyword(text, BUY_KEYWORDS):
            return _parse_contract_alert(text, "buy", require_price=True)

        return _parse_contract_alert(text, "buy", require_price=True)
    except Exception as exc:
        logger.error("Error parsing alert: %s", exc)
        return None


def is_actionable_average_down_alert(message: str) -> bool:
    """Distinguish an executed/immediate add from future DCA planning language."""
    text = " ".join(str(message or "").split())
    if not text:
        return False
    actionable_text = NEGATED_AVG_DOWN_RE.sub(" ", text)
    if EXPLICIT_AVG_DOWN_RE.search(actionable_text):
        return True
    if DEFERRED_AVG_DOWN_RE.search(actionable_text):
        return False
    return _contains_keyword(actionable_text, AVG_DOWN_KEYWORDS)


def normalize_expiration_for_order(
    expiration: Optional[str],
    *,
    today: Optional[date] = None,
    roll_forward: bool = True,
) -> Optional[str]:
    """Return broker-acceptable MM/DD/YY for slash dates that omit a year."""
    text = str(expiration or "").strip()
    if not text:
        return expiration

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) or re.fullmatch(r"\d{6,8}", text):
        return text

    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", text)
    if not match:
        return expiration

    month = int(match.group(1))
    day = int(match.group(2))
    year_text = match.group(3)
    if year_text:
        year = int(year_text)
        if year < 100:
            year += 2000
    else:
        base = today or date.today()
        year = base.year
        try:
            candidate = date(year, month, day)
        except ValueError:
            return expiration
        if roll_forward and candidate < base:
            year += 1

    try:
        date(year, month, day)
    except ValueError:
        return expiration
    return f"{month:02d}/{day:02d}/{year % 100:02d}"


def normalize_parsed_alert(parsed: Optional[dict]) -> Optional[dict]:
    if not parsed:
        return parsed
    normalized = dict(parsed)
    alert_type = str(normalized.get("alert_type") or "").strip().lower()
    normalized["expiration"] = normalize_expiration_for_order(
        normalized.get("expiration"),
        roll_forward=alert_type not in EXIT_ALERT_TYPES,
    )
    return normalized


def _strip_forwarded_alert_header(message: str) -> str:
    raw = str(message or "").strip()
    lines = raw.splitlines()
    if not lines:
        return raw

    first_lines = [line.strip().lower() for line in lines[:4]]
    if "[copied-alert]" not in first_lines and not any(line.startswith("source:") for line in first_lines):
        return raw

    for index, line in enumerate(lines):
        if not line.strip():
            body = "\n".join(lines[index + 1 :]).strip()
            return body or raw
    return raw


def _parse_sell_alert(message: str) -> Optional[dict]:
    result = _parse_contract_alert(message, "sell", require_price=False, require_contract=False)
    if not result:
        return None

    if re.search(r"\bPARTIALLY\s+CLOSED\b", message, re.IGNORECASE):
        result["alert_type"] = "trim"
    elif _contains_keyword(message, ("TRIM", "TRIMMING")):
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
        "market_price": bool(MARKET_PRICE_RE.search(message)),
    }


def _extract_ticker(message: str) -> Optional[str]:
    trade_echo_match = TRADE_ECHO_CONTRACT_RE.search(message)
    if trade_echo_match:
        ticker = _normalize_ticker(trade_echo_match.group("ticker"))
        if ticker:
            return ticker

    cash_match = CASH_TICKER_RE.search(message)
    if cash_match:
        ticker = _normalize_ticker(cash_match.group("ticker"), explicit=True)
        if ticker:
            return ticker

    action_match = ACTION_TICKER_RE.search(message)
    if action_match:
        action_ticker = action_match.group("ticker")
        ticker = _normalize_ticker(action_ticker, explicit=action_ticker.startswith("$"))
        if ticker:
            return ticker

    option_side_match = _first_valid_ticker_option_side(message)
    if option_side_match:
        return option_side_match

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
        r"\b(?:SELL|SOLD|TRIM|STC|SCALE|OUT|EXIT|CLOSE)\s*(?:OUT\s*)?(\d{1,3})\s*%",
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


def _normalize_ticker(value: str, *, explicit: bool = False) -> Optional[str]:
    ticker = str(value or "").strip().upper().lstrip("$")
    if not re.fullmatch(r"[A-Z]{1,6}", ticker):
        return None
    if not explicit and ticker in TICKER_STOPWORDS:
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
