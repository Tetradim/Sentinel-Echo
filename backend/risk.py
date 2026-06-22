"""
Risk management helpers called during trade entry.

Covers three gaps vs a professional system:

1. Risk-based position sizing
   Instead of always using default_quantity, compute the maximum number of
   contracts that fits within max_position_size. If one contract would exceed
   the cap, sizing returns 0 so the trade can be blocked instead of forced.

2. Correlation / concentration check
   Before entering a new position, count how many open positions exist for
   the same underlying ticker.  If the count would exceed max_positions_per_ticker
   the trade is blocked and an SMS is sent.  This prevents accidentally
   accumulating 5 SPY calls from 5 separate alerts.

3. Duplicate alert detection
   A content fingerprint (ticker + strike + option_type + expiration + alert_type)
   is stored with a timestamp.  If the same fingerprint arrives within
   DUPLICATE_WINDOW_SECS it is silently dropped.  The window is intentionally
   short (60 s) so legitimate re-entries after a few minutes are still allowed.
"""

import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── Duplicate alert detection ──────────────────────────────────────────────────
DUPLICATE_WINDOW_SECS = 60   # suppress identical alert within this window

# In-memory store: { fingerprint: datetime_of_first_seen }
# This resets on restart which is fine; the window is short enough that
# a restart during normal operation causes at most one extra trade.
_seen_fingerprints: dict[str, datetime] = {}


def _alert_fingerprint(parsed: dict) -> str:
    """
    Stable hash over the fields that define a unique trade signal.
    Sell alerts don't include strike/option_type so "SELL $SPY" dedupes
    regardless of which position it would close.
    """
    key_parts = [
        str(parsed.get("ticker", "")).upper(),
        str(parsed.get("alert_type", "")).lower(),
    ]
    if parsed.get("alert_type") == "buy":
        key_parts += [
            str(parsed.get("strike", "")),
            str(parsed.get("option_type", "")).upper(),
            str(parsed.get("expiration", "")),
        ]
    key = "|".join(key_parts)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _purge_old_fingerprints():
    """Remove entries older than the window to keep memory bounded."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=DUPLICATE_WINDOW_SECS)
    stale = [k for k, ts in _seen_fingerprints.items() if ts < cutoff]
    for k in stale:
        del _seen_fingerprints[k]


def is_duplicate_alert(parsed: dict) -> bool:
    """
    Returns True if this alert is a duplicate of one seen within the last
    DUPLICATE_WINDOW_SECS seconds.  Records the fingerprint if new.
    """
    _purge_old_fingerprints()
    fp = _alert_fingerprint(parsed)
    now = datetime.now(timezone.utc)

    if fp in _seen_fingerprints:
        age = (now - _seen_fingerprints[fp]).total_seconds()
        logger.warning(
            f"[risk] duplicate alert suppressed (fingerprint={fp}, age={age:.1f}s): "
            f"{parsed.get('ticker')} {parsed.get('alert_type')}"
        )
        return True

    _seen_fingerprints[fp] = now
    return False


# ── Risk-based position sizing ─────────────────────────────────────────────────
def calculate_position_size(
    entry_price: float,
    default_quantity: int,
    max_position_size: float,
    risk_multiplier: float = 1.0,
) -> int:
    """
    Return the number of contracts to trade.

    Options contracts represent 100 shares, so:
        cost_per_contract = entry_price * 100

    We adjust default_quantity by risk_multiplier, then take the floor of
    (max_position_size / cost_per_contract) and cap to the adjusted default.
    If one contract would exceed max_position_size, return 0.

    Examples
    --------
    entry_price=2.50, default_quantity=10, max_position_size=1000
        -> floor(1000 / 250) = 4 -> 4 contracts (not 10)

    entry_price=0.30, default_quantity=5, max_position_size=1000
        -> floor(1000 / 30) = 33 -> clamped to 5 (default cap)

    entry_price=15.00, default_quantity=5, max_position_size=1000
        -> floor(1000 / 1500) = 0 -> 0 contracts (blocked)
    """
    if entry_price <= 0:
        logger.warning("[risk] entry_price <= 0 - defaulting to 1 contract")
        return 1

    cost_per_contract = entry_price * 100.0

    try:
        multiplier = float(risk_multiplier)
    except (TypeError, ValueError):
        multiplier = 1.0
    if multiplier <= 0:
        multiplier = 1.0

    adjusted_default_quantity = max(1, int(default_quantity * multiplier))

    if max_position_size <= 0:
        logger.warning("[risk] max_position_size <= 0 - blocking trade")
        return 0

    risk_qty = int(max_position_size / cost_per_contract)
    quantity = min(risk_qty, adjusted_default_quantity)

    logger.info(
        f"[risk] sizing: entry=${entry_price:.2f} cost/contract=${cost_per_contract:.0f} "
        f"max_size=${max_position_size:.0f} risk_qty={risk_qty} "
        f"default_qty={default_quantity} -> final={quantity}"
    )
    return quantity


# ── Correlation / concentration check ─────────────────────────────────────────
DEFAULT_MAX_POSITIONS_PER_TICKER = 3   # sensible default if not in settings


async def check_correlation(
    ticker: str,
    db,
    settings: dict,
) -> tuple[bool, str]:
    """
    Check whether adding a new position in `ticker` would exceed the
    max_positions_per_ticker setting.

    Returns
    -------
    (allowed: bool, reason: str)
        allowed=True  -> proceed with the trade
        allowed=False -> block the trade; reason explains why
    """
    max_per_ticker = int(
        settings.get("max_positions_per_ticker", DEFAULT_MAX_POSITIONS_PER_TICKER)
    )

    # max_per_ticker=0 means unlimited (disabled)
    if max_per_ticker == 0:
        return True, ""

    try:
        open_positions = await db.get_positions("open")
    except Exception as e:
        logger.error(f"[risk] correlation check db error: {e}")
        # Fail open; don't block the trade due to a db hiccup
        return True, ""

    same_ticker = [
        p for p in open_positions
        if str(p.get("ticker", "")).upper() == ticker.upper()
    ]
    count = len(same_ticker)

    if count >= max_per_ticker:
        reason = (
            f"Correlation limit: {count} open position(s) in {ticker} "
            f"(max {max_per_ticker})"
        )
        logger.warning(f"[risk] {reason}")
        return False, reason

    logger.info(
        f"[risk] correlation OK: {count}/{max_per_ticker} open positions in {ticker}"
    )
    return True, ""
