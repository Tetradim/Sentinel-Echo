"""Direction-aware entry sizing for alerted option contracts."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor
from typing import Any, Iterable


MIN_BAR_COUNT = 6
MAX_FULL_SIZE_SPREAD_PERCENT = 50.0


@dataclass(frozen=True)
class EntryAlignmentDecision:
    tier: str
    alignment_score: float
    underlying_score: float
    multiplier_percent: float
    quote_spread_percent: float | None
    reasons: list[str]
    context_available: bool
    source: str
    option_bid: float | None = None
    option_ask: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def apply_alignment_quantity(base_quantity: int, multiplier_percent: float) -> int:
    """Reduce an already risk-capped quantity while preserving one contract."""
    quantity = max(1, int(base_quantity))
    percent = max(0.0, min(float(multiplier_percent), 100.0))
    return max(1, floor(quantity * percent / 100.0))


def entry_slippage_size_cap(
    alert_price: Any,
    live_ask: Any,
    *,
    warning_percent: float = 10.0,
    severe_percent: float = 20.0,
    warning_size_percent: float = 50.0,
    severe_size_percent: float = 25.0,
    mode: str = "tiered",
) -> tuple[float | None, float | None]:
    """Reduce quantity when the executable ask has moved above the alert price."""
    entry = _positive_float(alert_price)
    ask = _positive_float(live_ask)
    if entry is None or ask is None:
        return None, None
    slippage_percent = round(max(0.0, (ask - entry) / entry * 100.0), 3)
    normalized_mode = str(mode or "tiered").strip().lower()
    if normalized_mode == "disabled":
        return None, slippage_percent
    if normalized_mode == "binary":
        return (0.0 if slippage_percent > severe_percent else None), slippage_percent
    if slippage_percent > max(warning_percent, severe_percent):
        return _valid_percent(severe_size_percent), slippage_percent
    if slippage_percent > warning_percent:
        return _valid_percent(warning_size_percent), slippage_percent
    return None, slippage_percent


def evaluate_entry_alignment(
    *,
    option_type: str,
    bars: Iterable[dict[str, Any]] | None,
    option_bid: float | None,
    option_ask: float | None,
    agreement_percent: float = 100.0,
    mixed_percent: float = 50.0,
    conflict_percent: float = 25.0,
    source: str = "alpaca",
) -> EntryAlignmentDecision:
    """Classify whether point-in-time market context supports a CALL or PUT."""
    normalized_bars = _valid_bars(bars or [])
    bid = _positive_float(option_bid)
    ask = _positive_float(option_ask)
    quote_valid = bid is not None and ask is not None and ask >= bid
    context_available = len(normalized_bars) >= MIN_BAR_COUNT and quote_valid

    if not context_available:
        return EntryAlignmentDecision(
            tier="mixed",
            alignment_score=0.0,
            underlying_score=0.0,
            multiplier_percent=_valid_percent(mixed_percent),
            quote_spread_percent=_spread_percent(bid, ask),
            reasons=["market context unavailable"],
            context_available=False,
            source=source,
            option_bid=bid,
            option_ask=ask,
        )

    underlying_score, reasons = _score_underlying(normalized_bars)
    direction = str(option_type or "").strip().upper()
    direction_factor = -1.0 if direction == "PUT" else 1.0
    alignment_score = underlying_score * direction_factor
    spread_percent = _spread_percent(bid, ask)

    if alignment_score >= 2.0:
        tier = "agreement"
        multiplier = _valid_percent(agreement_percent)
        reasons.append(f"underlying trend supports {direction or 'CALL'}")
    elif alignment_score <= -2.0:
        tier = "conflict"
        multiplier = _valid_percent(conflict_percent)
        reasons.append(f"underlying trend conflicts with {direction or 'CALL'}")
    else:
        tier = "mixed"
        multiplier = _valid_percent(mixed_percent)
        reasons.append(f"underlying trend is mixed for {direction or 'CALL'}")

    if (
        tier == "agreement"
        and spread_percent is not None
        and spread_percent > MAX_FULL_SIZE_SPREAD_PERCENT
    ):
        tier = "mixed"
        multiplier = _valid_percent(mixed_percent)
        reasons.append("option spread is too wide for full sizing")

    return EntryAlignmentDecision(
        tier=tier,
        alignment_score=round(alignment_score, 3),
        underlying_score=round(underlying_score, 3),
        multiplier_percent=multiplier,
        quote_spread_percent=spread_percent,
        reasons=reasons,
        context_available=True,
        source=source,
        option_bid=bid,
        option_ask=ask,
    )


def disabled_entry_alignment() -> EntryAlignmentDecision:
    return EntryAlignmentDecision(
        tier="disabled",
        alignment_score=0.0,
        underlying_score=0.0,
        multiplier_percent=100.0,
        quote_spread_percent=None,
        reasons=["smart sizing disabled"],
        context_available=False,
        source="disabled",
    )


def _score_underlying(bars: list[dict[str, float]]) -> tuple[float, list[str]]:
    closes = [bar["c"] for bar in bars]
    volumes = [bar["v"] for bar in bars]
    latest = closes[-1]
    threshold = max(latest * 0.0002, 0.001)
    score = 0.0
    reasons: list[str] = []

    momentum = latest - closes[-6]
    score += _direction_point(momentum, threshold)
    reasons.append(f"five-minute momentum {momentum:+.4f}")

    recent_average = sum(closes[-3:]) / 3
    prior_average = sum(closes[-6:-3]) / 3
    short_trend = recent_average - prior_average
    score += _direction_point(short_trend, threshold)
    reasons.append(f"short trend {short_trend:+.4f}")

    total_volume = sum(volumes)
    vwap = sum(close * volume for close, volume in zip(closes, volumes)) / total_volume
    vwap_distance = latest - vwap
    score += _direction_point(vwap_distance, threshold)
    reasons.append(f"price versus VWAP {vwap_distance:+.4f}")

    average_volume = total_volume / len(volumes)
    if volumes[-1] >= average_volume:
        candle_move = latest - bars[-1]["o"]
        score += _direction_point(candle_move, threshold)
        reasons.append(f"volume-confirmed candle {candle_move:+.4f}")

    return score, reasons


def _valid_bars(bars: Iterable[dict[str, Any]]) -> list[dict[str, float]]:
    valid: list[dict[str, float]] = []
    for bar in bars:
        try:
            open_price = float(bar.get("o", bar.get("open")))
            close_price = float(bar.get("c", bar.get("close")))
            volume = float(bar.get("v", bar.get("volume")))
        except (AttributeError, TypeError, ValueError):
            continue
        if open_price <= 0 or close_price <= 0 or volume <= 0:
            continue
        valid.append({"o": open_price, "c": close_price, "v": volume})
    return valid


def _direction_point(value: float, threshold: float) -> float:
    if value > threshold:
        return 1.0
    if value < -threshold:
        return -1.0
    return 0.0


def _spread_percent(bid: float | None, ask: float | None) -> float | None:
    if bid is None or ask is None or ask < bid:
        return None
    midpoint = (bid + ask) / 2
    if midpoint <= 0:
        return None
    return round(((ask - bid) / midpoint) * 100.0, 2)


def _positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _valid_percent(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return max(0.0, min(number, 100.0))
