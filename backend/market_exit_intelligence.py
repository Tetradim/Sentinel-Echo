"""Deterministic market-context decisions for Echo-managed option exits."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, time
from statistics import fmean
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from entry_alignment import evaluate_entry_alignment
from position_identity import canonical_expiration_yyyymmdd
from settings_flags import coerce_bool


EASTERN = ZoneInfo("America/New_York")
COUNTERFACTUAL_STOPS = (20, 30, 40, 50)
COUNTERFACTUAL_TRAILS = (10, 15, 20)
MARK_HISTORY_LIMIT = 12


@dataclass(frozen=True)
class MarketExitDecision:
    context_available: bool
    triggered: bool
    reversal_state: str
    exit_trigger: str | None
    sell_percent: float | None
    alignment_score: float
    option_midpoint: float | None
    option_bid: float | None
    option_ask: float | None
    spread_percent: float | None
    premium_drawdown_percent: float | None
    adaptive_trailing_percent: float | None
    reasons: list[str]
    position_updates: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_market_exit_intelligence(
    position: dict[str, Any],
    settings: dict[str, Any],
    *,
    bars: Iterable[dict[str, Any]] | None,
    option_bid: float | None,
    option_ask: float | None,
    now: datetime | None = None,
) -> MarketExitDecision:
    """Evaluate reversal persistence, adaptive trailing, and path telemetry."""
    position = position if isinstance(position, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    observed_at = _eastern_now(now)
    bid = _positive_float(option_bid)
    ask = _positive_float(option_ask)
    quote_valid = bid > 0 and ask >= bid
    midpoint = round((bid + ask) / 2, 4) if quote_valid else None
    previous_count = _non_negative_int(position.get("reversal_conflict_count"))

    alignment = evaluate_entry_alignment(
        option_type=str(position.get("option_type") or ""),
        bars=bars or [],
        option_bid=bid or None,
        option_ask=ask or None,
        source="alpaca",
    )
    context_available = alignment.context_available and midpoint is not None
    if not context_available:
        return MarketExitDecision(
            context_available=False,
            triggered=False,
            reversal_state="unavailable",
            exit_trigger=None,
            sell_percent=None,
            alignment_score=0.0,
            option_midpoint=None,
            option_bid=bid or None,
            option_ask=ask or None,
            spread_percent=alignment.quote_spread_percent,
            premium_drawdown_percent=None,
            adaptive_trailing_percent=None,
            reasons=["market context unavailable; position held"],
            position_updates={
                "reversal_conflict_count": previous_count,
                "market_intelligence_context_available": False,
                "market_intelligence_checked_at": observed_at.isoformat(),
            },
        )

    entry_price = _positive_float(position.get("entry_price"))
    previous_peak = max(
        entry_price,
        _positive_float(position.get("highest_price")),
        _positive_float(position.get("current_price")),
    )
    highest_price = max(previous_peak, midpoint)
    premium_drawdown = (
        round(max(0.0, (previous_peak - midpoint) / previous_peak * 100), 3)
        if previous_peak > 0
        else 0.0
    )
    reversal_enabled = coerce_bool(settings.get("reversal_exit_enabled"), default=True)
    required_drawdown = _positive_float(settings.get("reversal_premium_drawdown_percent")) or 12.0
    conflict_qualified = alignment.alignment_score <= -2.0 and premium_drawdown >= required_drawdown

    if not reversal_enabled:
        conflict_count = 0
    elif conflict_qualified:
        conflict_count = previous_count + 1
    elif alignment.alignment_score >= 2.0:
        conflict_count = 0
    else:
        conflict_count = max(0, previous_count - 1)

    warning_count = max(1, _positive_int(settings.get("reversal_warning_confirmations"), 3))
    confirmed_count = max(
        warning_count + 1,
        _positive_int(settings.get("reversal_confirmed_confirmations"), 5),
    )
    warning_completed = coerce_bool(
        position.get("reversal_reduce_completed", position.get("reversal_warning_completed")),
        default=False,
    )
    triggered = False
    exit_trigger = None
    sell_percent = None
    reversal_state = "held"
    reasons = list(alignment.reasons)

    current_return = ((midpoint - entry_price) / entry_price * 100.0) if entry_price > 0 else 0.0
    recorded_mfe = max(
        _float(position.get("max_favorable_excursion_percent"), 0.0),
        ((highest_price - entry_price) / entry_price * 100.0) if entry_price > 0 else 0.0,
    )
    reduce_qualified = (
        current_return >= _non_negative_float(settings.get("reversal_reduce_min_return_percent"), 5.0)
        or recorded_mfe >= _non_negative_float(settings.get("reversal_reduce_min_mfe_percent"), 20.0)
    )

    if reversal_enabled and conflict_count >= confirmed_count:
        reversal_state = "reversal_confirmed"
        triggered = True
        exit_trigger = "reversal_confirmed"
        sell_percent = 100.0
        reasons.append("persistent market reversal confirmed")
    elif reversal_enabled and conflict_count >= warning_count:
        if warning_completed:
            reversal_state = "reversal_observed"
            reasons.append("automatic reversal reduction already completed")
        elif not reduce_qualified:
            reversal_state = "reversal_observed"
            reasons.append("reversal evidence retained without reducing an unprofitable position")
        else:
            reversal_state = "reversal_reduce"
            triggered = True
            exit_trigger = "reversal_reduce"
            sell_percent = _bounded_percent(
                settings.get("reversal_warning_sell_percent"),
                default=25.0,
            )
            reasons.append("persistent reversal evidence triggered an automatic reduction")
    elif reversal_enabled and conflict_count > 0:
        reversal_state = "reversal_observed"
        reasons.append("reversal conflict requires more confirmation")
    elif not reversal_enabled:
        reversal_state = "disabled"

    mark_history = _mark_history(position.get("premium_mark_history"), midpoint)
    adaptive_percent = _adaptive_trailing_percent(
        position,
        settings,
        alignment_score=alignment.alignment_score,
        spread_percent=alignment.quote_spread_percent or 0.0,
        mark_history=mark_history,
        now=observed_at,
    )
    telemetry = _telemetry_updates(
        position,
        entry_price=entry_price,
        current_price=midpoint,
        highest_price=highest_price,
        observed_at=observed_at,
    )
    updates = {
        **telemetry,
        "current_price": midpoint,
        "highest_price": highest_price,
        "option_bid": bid,
        "option_ask": ask,
        "option_spread_percent": alignment.quote_spread_percent,
        "premium_mark_history": mark_history,
        "reversal_conflict_count": conflict_count,
        "reversal_state": reversal_state,
        "reversal_alignment_score": alignment.alignment_score,
        "reversal_premium_drawdown_percent": premium_drawdown,
        "adaptive_trailing_percent": adaptive_percent,
        "market_intelligence_context_available": True,
        "market_intelligence_checked_at": observed_at.isoformat(),
    }

    return MarketExitDecision(
        context_available=True,
        triggered=triggered,
        reversal_state=reversal_state,
        exit_trigger=exit_trigger,
        sell_percent=sell_percent,
        alignment_score=alignment.alignment_score,
        option_midpoint=midpoint,
        option_bid=bid,
        option_ask=ask,
        spread_percent=alignment.quote_spread_percent,
        premium_drawdown_percent=premium_drawdown,
        adaptive_trailing_percent=adaptive_percent,
        reasons=reasons,
        position_updates=updates,
    )


def _adaptive_trailing_percent(
    position: dict[str, Any],
    settings: dict[str, Any],
    *,
    alignment_score: float,
    spread_percent: float,
    mark_history: list[float],
    now: datetime,
) -> float | None:
    if not coerce_bool(settings.get("trailing_stop_enabled"), default=False):
        return None
    if not coerce_bool(settings.get("adaptive_trailing_enabled"), default=True):
        return None
    if str(settings.get("trailing_stop_type") or "percent").strip().lower() != "percent":
        return None

    minimum = _positive_float(settings.get("adaptive_trailing_min_percent")) or 8.0
    maximum = _positive_float(settings.get("adaptive_trailing_max_percent")) or 35.0
    if maximum < minimum:
        minimum, maximum = maximum, minimum
    base = _positive_float(settings.get("trailing_stop_percent")) or 10.0
    spread_padding = min(max(spread_percent, 0.0) * 0.25, 6.0)
    volatility_padding = min(_premium_volatility_percent(mark_history) * 0.4, 8.0)
    regime_adjustment = 3.0 if alignment_score >= 2.0 else -4.0 if alignment_score <= -2.0 else 0.0
    time_adjustment = _expiration_time_adjustment(
        position.get("expiration"),
        str(settings.get("zero_dte_liquidation_time") or "15:40"),
        now,
    )
    effective = base + spread_padding + volatility_padding + regime_adjustment + time_adjustment
    return round(min(maximum, max(minimum, effective)), 2)


def _telemetry_updates(
    position: dict[str, Any],
    *,
    entry_price: float,
    current_price: float,
    highest_price: float,
    observed_at: datetime,
) -> dict[str, Any]:
    if entry_price <= 0:
        return {}
    current_return = round((current_price - entry_price) / entry_price * 100, 3)
    peak_return = round((highest_price - entry_price) / entry_price * 100, 3)
    mfe = max(_float(position.get("max_favorable_excursion_percent"), 0.0), peak_return)
    mae = min(_float(position.get("max_adverse_excursion_percent"), 0.0), current_return)
    timestamp = observed_at.isoformat()

    stop_hits = _copy_mapping(position.get("counterfactual_stop_hits"))
    for threshold in COUNTERFACTUAL_STOPS:
        key = str(threshold)
        if current_return <= -threshold and key not in stop_hits:
            stop_hits[key] = {"timestamp": timestamp, "price": current_price, "return_percent": current_return}

    trailing_hits = _copy_mapping(position.get("counterfactual_trailing_hits"))
    if highest_price > entry_price:
        for width in COUNTERFACTUAL_TRAILS:
            key = str(width)
            level = highest_price * (1 - width / 100)
            if current_price <= level and key not in trailing_hits:
                trailing_hits[key] = {
                    "timestamp": timestamp,
                    "price": current_price,
                    "peak": highest_price,
                    "width_percent": width,
                }

    return {
        "max_favorable_excursion_percent": round(mfe, 3),
        "max_adverse_excursion_percent": round(mae, 3),
        "counterfactual_stop_hits": stop_hits,
        "counterfactual_trailing_hits": trailing_hits,
    }


def _expiration_time_adjustment(expiration: Any, cutoff_text: str, now: datetime) -> float:
    canonical = canonical_expiration_yyyymmdd(expiration)
    try:
        expiration_date = datetime.fromisoformat(canonical).date()
    except ValueError:
        return 0.0
    days = (expiration_date - now.date()).days
    if days < 0:
        return -4.0
    if days == 0:
        cutoff = _parse_time(cutoff_text, time(15, 40))
        cutoff_dt = datetime.combine(now.date(), cutoff, tzinfo=EASTERN)
        minutes = (cutoff_dt - now).total_seconds() / 60
        if minutes <= 60:
            return -4.0
        if minutes <= 120:
            return -2.0
    if days == 1:
        return -1.0
    return 0.0


def _premium_volatility_percent(history: list[float]) -> float:
    if len(history) < 2:
        return 0.0
    returns = [
        abs((current - previous) / previous) * 100
        for previous, current in zip(history, history[1:])
        if previous > 0
    ]
    return fmean(returns) if returns else 0.0


def _mark_history(raw_history: Any, current: float) -> list[float]:
    values = []
    if isinstance(raw_history, list):
        values = [_positive_float(value) for value in raw_history]
        values = [value for value in values if value > 0]
    values.append(round(current, 4))
    return values[-MARK_HISTORY_LIMIT:]


def _copy_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _eastern_now(value: datetime | None) -> datetime:
    current = value or datetime.now(EASTERN)
    if current.tzinfo is None:
        return current.replace(tzinfo=EASTERN)
    return current.astimezone(EASTERN)


def _parse_time(value: str, fallback: time) -> time:
    try:
        return time.fromisoformat(str(value).strip())
    except ValueError:
        return fallback


def _bounded_percent(value: Any, *, default: float) -> float:
    return min(100.0, max(1.0, _positive_float(value) or default))


def _positive_int(value: Any, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _positive_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        return max(float(value or 0.0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _non_negative_float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
