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
   A content fingerprint (ticker + strike + option_type + expiration +
   alert_type + price/percentage details) is stored with a timestamp.  If
   the same fingerprint arrives within
   DUPLICATE_WINDOW_SECS it is silently dropped.  The window is intentionally
   short (60 s) so legitimate re-entries after a few minutes are still allowed.
"""

import hashlib
import logging
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Protocol

from settings_flags import coerce_bool

logger = logging.getLogger(__name__)

# Duplicate alert detection.
DUPLICATE_WINDOW_SECS = 60   # suppress identical alert within this window

# In-memory store: { fingerprint: datetime_of_first_seen }
# This resets on restart which is fine; the window is short enough that
# a restart during normal operation causes at most one extra trade.
_seen_fingerprints: dict[str, datetime] = {}


class DuplicateAlertStore(Protocol):
    def seen_recently(self, fingerprint: str, now: datetime, window_seconds: int) -> bool:
        """Return True when fingerprint already exists inside the duplicate window."""


class SQLiteDuplicateAlertStore:
    """Process-shared duplicate alert store backed by a SQLite uniqueness constraint."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_table()

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=30)

    def _ensure_table(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS duplicate_alert_fingerprints (
                        fingerprint TEXT PRIMARY KEY,
                        seen_at TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def seen_recently(self, fingerprint: str, now: datetime, window_seconds: int) -> bool:
        cutoff = now - timedelta(seconds=window_seconds)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM duplicate_alert_fingerprints WHERE seen_at < ?",
                    (cutoff.isoformat(),),
                )
                try:
                    conn.execute(
                        "INSERT INTO duplicate_alert_fingerprints (fingerprint, seen_at) VALUES (?, ?)",
                        (fingerprint, now.isoformat()),
                    )
                    conn.commit()
                    return False
                except sqlite3.IntegrityError:
                    conn.commit()
                    return True
            finally:
                conn.close()


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
    if parsed.get("strike") or parsed.get("option_type") or parsed.get("expiration"):
        key_parts += [
            str(parsed.get("strike", "")),
            str(parsed.get("option_type", "")).upper(),
            str(parsed.get("expiration", "")),
        ]
    entry_price = parsed.get("entry_price")
    if entry_price not in (None, ""):
        try:
            key_parts.append(f"price={float(entry_price):.4f}")
        except (TypeError, ValueError):
            key_parts.append(f"price={entry_price}")
    sell_percentage = parsed.get("sell_percentage")
    if sell_percentage not in (None, ""):
        try:
            key_parts.append(f"sell_pct={float(sell_percentage):.4f}")
        except (TypeError, ValueError):
            key_parts.append(f"sell_pct={sell_percentage}")
    key = "|".join(key_parts)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _purge_old_fingerprints():
    """Remove entries older than the window to keep memory bounded."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=DUPLICATE_WINDOW_SECS)
    stale = [k for k, ts in _seen_fingerprints.items() if ts < cutoff]
    for k in stale:
        del _seen_fingerprints[k]


def _is_duplicate_alert(parsed: dict, store: Optional[DuplicateAlertStore] = None) -> bool:
    """
    Returns True if this alert is a duplicate of one seen within the last
    DUPLICATE_WINDOW_SECS seconds.  Records the fingerprint if new.
    """
    fp = _alert_fingerprint(parsed)
    now = datetime.now(timezone.utc)

    if store is not None:
        if store.seen_recently(fp, now, DUPLICATE_WINDOW_SECS):
            logger.warning(
                f"[risk] duplicate alert suppressed (fingerprint={fp}): "
                f"{parsed.get('ticker')} {parsed.get('alert_type')}"
            )
            return True
        return False

    _purge_old_fingerprints()
    if fp in _seen_fingerprints:
        age = (now - _seen_fingerprints[fp]).total_seconds()
        logger.warning(
            f"[risk] duplicate alert suppressed (fingerprint={fp}, age={age:.1f}s): "
            f"{parsed.get('ticker')} {parsed.get('alert_type')}"
        )
        return True

    _seen_fingerprints[fp] = now
    return False


def is_duplicate_alert(parsed: dict, store: Optional[DuplicateAlertStore] = None) -> bool:
    return _is_duplicate_alert(parsed, store=store)


# Risk-based position sizing.
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
        logger.warning("[risk] entry_price <= 0 - blocking trade")
        return 0

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


# Correlation / concentration check.
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
        if not coerce_bool(settings.get("simulation_mode"), default=True):
            return False, "Risk controls unavailable"
        return True, ""

    if not coerce_bool(settings.get("simulation_mode"), default=True):
        open_positions = [
            p for p in open_positions
            if not coerce_bool(p.get("simulated"), default=False)
        ]

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
