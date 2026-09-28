"""Deterministic labelled Discord cards; never infer trades from card commentary."""
from dataclasses import dataclass
from datetime import datetime
import re
import unicodedata


@dataclass(frozen=True)
class CardResult:
    recognized: bool
    parsed: dict | None = None
    reason: str = ""


CONTRACT = re.compile(r"\b([A-Z]{1,6})\s+\$?(\d+(?:\.\d+)?)\s*(CALLS?|PUTS?|[CP])\b", re.I)
EXP_LABEL = r"(?:EXP|EXPIRATION|EXPIRY)"
DATE_VALUE = r"(?:[A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/(?:\d{4}|\d{2}))"
FILLED_POSITION_HINT = re.compile(
    r"^\s*\$?[A-Z]{1,6}\s+\$?\d+(?:\.\d+)?\s*[CP]\s+"
    r"\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?\b[^\n]*\bFILLED\b",
    re.I | re.M,
)
FILLED_POSITION_ENTRY = re.compile(
    r"^\s*\$?(?P<ticker>[A-Z]{1,6})\s+\$?(?P<strike>\d+(?:\.\d+)?)\s*(?P<side>[CP])\s+"
    r"(?P<expiration>\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?)\b[^\n]*?\bFILLED\s+"
    r"(?P<quantity>\d+)\s*[Xx]?\s*@\s*\$(?P<price>\d+(?:\.\d+)?)\b",
    re.I | re.M,
)


def parse_card(raw: str) -> CardResult:
    # Preserve field boundaries, removing only formatting and decorative glyphs.
    text = unicodedata.normalize('NFKC', str(raw or ''))
    text = text.replace('×', 'x').replace('−', '-').replace('·', ' ')
    text = re.sub(r'<a?:\w+:\d+>', ' ', text)
    text = re.sub(r'[^\x20-\x7e\n\r\t]', ' ', text).replace('**', '').replace('__', '')
    filled_card = _parse_filled_position_card(text)
    if filled_card.recognized:
        return filled_card
    is_update = bool(re.search(r'\bPOSITION UPDATE\b', text, re.I))
    is_entry = bool(re.search(r'\bALERTED BY\b', text, re.I)) or bool(
        re.search(rf'^\s*{EXP_LABEL}\s*(?:[:|]|$)', text, re.I | re.M)
        and re.search(r'^\s*ENTRY(?: PRICE)?\s*[:|]?\s*', text, re.I | re.M)
    )
    if not (is_update or is_entry):
        return CardResult(False)

    def invalid(reason):
        return CardResult(True, reason=reason)

    type_match = re.search(r'\bTYPE\s*[:|]?\s*([^\n]+)', text, re.I)
    update_type = type_match.group(1).strip() if type_match else ''
    if is_update and re.match(r'COMMENT\b', update_type, re.I):
        return invalid('card comment; no trade action')
    contracts = {(t.upper(), float(s), 'CALL' if o.upper().startswith('C') else 'PUT')
                 for t, s, o in CONTRACT.findall(text)}
    if len(contracts) != 1:
        return invalid('card requires one unambiguous option contract')
    ticker, strike, side = contracts.pop()
    if strike <= 0:
        return invalid('invalid card strike')
    expiry_matches = re.findall(rf'\b{EXP_LABEL}\s*[:|]?\s*({DATE_VALUE})\b', text, re.I)
    if re.search(rf'^\s*{EXP_LABEL}\s*(?:[:|]|$)', text, re.I | re.M) and not expiry_matches:
        return invalid('invalid labelled card expiration')
    expirations = {_parse_expiration(value) for value in expiry_matches}
    if len(expirations) > 1 or (expirations and None in expirations):
        return invalid('ambiguous or invalid labelled card expiration')
    expiry = next(iter(expirations), None)
    action, percentage, exit_price = 'buy', None, None
    action_text = update_type if is_update else text
    if re.search(r'\b(?:FULL CLOSE|FULLY CLOSED|FINAL EXIT)\b', action_text, re.I):
        action, percentage = 'close', 100.0
    elif re.search(r'\bTRIM(?:MED)?\b', action_text, re.I):
        amounts = set()
        for numerator, denominator, percent in re.findall(
            r'\bTRIM(?:MED)?\s+(?:(\d+)\s*/\s*(\d+)|(\d+(?:\.\d+)?)\s*%)', action_text, re.I
        ):
            if denominator and int(denominator) == 0:
                return invalid('invalid card trim fraction')
            amounts.add(float(percent) if percent else 100 * int(numerator) / int(denominator))
        if len(amounts) != 1 or not 0 < next(iter(amounts)) <= 100:
            return invalid('card trim requires one explicit valid fraction or percentage')
        action, percentage = 'trim', amounts.pop()
    elif is_update:
        return invalid('unsupported card update type')
    elif re.search(r'\b(?:TRIMS|CLOSED|EXIT)\b', text, re.I):
        return invalid('updated entry card has no supported explicit action')
    entry_price = None
    if action == 'buy':
        prices = {float(p) for p in re.findall(r'\bENTRY(?: PRICE)?\s*[:|]?\s*\$(\d+(?:\.\d+)?)', text, re.I)}
        if not expiry or len(prices) != 1 or next(iter(prices)) <= 0:
            return invalid('card entry requires labelled expiration with year and positive entry price')
        entry_price = prices.pop()
    else:
        price_pattern = (r'\b(?:FINAL )?EXIT\s*@\s*\$(\d+(?:\.\d+)?)' if action == 'close' else
                         r'(?:\bEXIT\s*@|\bTRIMMED\s+(?:\d+\s*/\s*\d+|\d+(?:\.\d+)?%)\s*[-|:]*)\s*\$(\d+(?:\.\d+)?)')
        prices = re.findall(price_pattern, text, re.I)
        unique_prices = {float(p) for p in prices}
        if len(unique_prices) > 1:
            return invalid('card contains multiple exit actions; cannot replay trim history')
        exit_price = next(iter(unique_prices), None)
        if action == 'trim' and (exit_price is None or exit_price <= 0):
            return invalid('card trim requires reported exit price for action identity')
    return CardResult(True, {
        'alert_type': action, 'ticker': ticker, 'strike': strike, 'option_type': side,
        'expiration': expiry, 'entry_price': entry_price, 'sell_percentage': percentage,
        'market_price': False,
        '_card': {'schema': 'labelled_options_v1', 'reported_exit_price': exit_price},
    })


def _parse_filled_position_card(text: str) -> CardResult:
    if not FILLED_POSITION_HINT.search(text):
        return CardResult(False)

    match = FILLED_POSITION_ENTRY.search(text)
    if not match:
        return CardResult(True, reason='filled position card requires quantity and entry price')

    expiration = _parse_expiration(match.group('expiration'))
    quantity = int(match.group('quantity'))
    price = float(match.group('price'))
    strike = float(match.group('strike'))
    if not expiration or quantity <= 0 or price <= 0 or strike <= 0:
        return CardResult(True, reason='filled position card has invalid contract, expiration, quantity, or price')

    headline_start = match.start('ticker')
    headline_end = text.find('\n', headline_start)
    headline = text[headline_start:headline_end if headline_end >= 0 else len(text)]
    stop_match = re.search(r'\bSTOP\s*([+-]?\d+(?:\.\d+)?)\s*%', headline, re.I)
    target_match = re.search(r'\bTARGET\s*:\s*([A-Z]+)', headline, re.I)
    return CardResult(True, {
        'alert_type': 'buy',
        'ticker': match.group('ticker').upper(),
        'strike': strike,
        'option_type': 'CALL' if match.group('side').upper() == 'C' else 'PUT',
        'expiration': expiration,
        'entry_price': price,
        'sell_percentage': None,
        'market_price': False,
        '_card': {
            'schema': 'filled_position_v1',
            'reported_exit_price': None,
            'reported_quantity': quantity,
            'reported_stop_percent': float(stop_match.group(1)) if stop_match else None,
            'target_mode': target_match.group(1).lower() if target_match else None,
        },
    })


def _parse_expiration(value: str) -> str | None:
    short_date = str(value or '').replace('-', '/')
    if re.fullmatch(r'\d{1,2}/\d{1,2}', short_date):
        try:
            return datetime.strptime(short_date, '%m/%d').strftime('%m/%d')
        except ValueError:
            return None
    if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{2,4}', short_date):
        value = short_date
    for fmt in ('%b %d, %Y', '%B %d, %Y', '%b %d %Y', '%B %d %Y', '%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'):
        try:
            return datetime.strptime(value, fmt).strftime('%m/%d/%y')
        except ValueError:
            pass
    return None
