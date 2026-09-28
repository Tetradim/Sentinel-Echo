from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from position_identity import canonical_expiration_yyyymmdd
from settings_flags import coerce_bool


@dataclass(frozen=True)
class RunnerState:
    enabled: bool
    candidate_quantity: int
    dedicated_quantity: int
    protected_quantity: int
    core_quantity: int
    activated: bool
    mfe_percent: float
    updates: dict[str, Any]


def update_runner_state(
    position: dict[str, Any],
    settings: dict[str, Any],
    *,
    bid: float,
    now: datetime | None = None,
) -> RunnerState:
    remaining = _quantity(position.get("remaining_quantity"))
    if not coerce_bool(settings.get("core_runner_enabled"), default=False):
        return RunnerState(False, 0, 0, 0, remaining, False, 0.0, {})

    observed_at = _aware_utc(now)
    persisted_original = _quantity(position.get("core_runner_original_quantity"))
    original = persisted_original or max(
        _quantity(position.get("original_quantity")),
        _quantity(position.get("quantity")),
        remaining,
    )
    entry = _positive_float(position.get("entry_price"))
    highest = max(
        _positive_float(position.get("highest_executable_bid")),
        _positive_float(bid),
    )
    mfe = max(0.0, (highest - entry) / entry * 100.0) if entry > 0 else 0.0

    desired = _desired_runner_quantity(original, settings)
    previous_candidate = _quantity(position.get("core_runner_candidate_quantity"))
    allocation_initialized = coerce_bool(
        position.get("core_runner_allocation_initialized"),
        default="core_runner_candidate_quantity" in position,
    )
    candidate = min(
        remaining,
        previous_candidate if allocation_initialized else desired,
    )
    was_activated = coerce_bool(position.get("core_runner_activated"), default=False)
    activation_threshold = _non_negative(settings.get("core_runner_activation_mfe_percent"), 100.0)
    minimum_seconds = _quantity(settings.get("core_runner_minimum_activation_seconds"))
    opened_at = _parse_datetime(position.get("opened_at"))
    old_enough = not opened_at or (observed_at - opened_at).total_seconds() >= minimum_seconds
    previous_runner_high = _positive_float(position.get("core_runner_highest_executable_bid"))
    fresh_high = previous_runner_high <= 0 or bid > previous_runner_high
    fresh_high_required = _flag(settings, "core_runner_require_fresh_high", False)
    activated = was_activated or (
        candidate > 0
        and mfe >= activation_threshold
        and old_enough
        and (not fresh_high_required or fresh_high)
    )
    previous_dedicated = _quantity(position.get("core_runner_dedicated_quantity"))
    dedicated = min(remaining, max(previous_dedicated, candidate if activated else 0))
    protected = dedicated if activated else candidate
    updates: dict[str, Any] = {
        "core_runner_allocation_initialized": True,
        "core_runner_original_quantity": original,
        "core_runner_candidate_quantity": candidate,
        "core_runner_dedicated_quantity": dedicated,
        "core_runner_core_quantity": max(0, remaining - protected),
        "core_runner_activated": activated,
        "core_runner_mfe_percent": round(mfe, 3),
        "core_runner_highest_executable_bid": round(highest, 4),
    }
    if activated and not was_activated:
        updates["core_runner_activated_at"] = observed_at.isoformat()
        updates["core_runner_activation_mfe_percent"] = round(mfe, 3)
        updates["core_runner_activation_high"] = round(highest, 4)

    return RunnerState(
        True,
        candidate,
        dedicated,
        protected,
        max(0, remaining - protected),
        activated,
        mfe,
        updates,
    )


def protected_quantity_for_trigger(
    state: RunnerState,
    settings: dict[str, Any],
    trigger: str,
) -> int:
    if not state.enabled:
        return 0
    trigger = str(trigger or "").strip().lower()
    candidate = state.candidate_quantity
    dedicated = state.dedicated_quantity

    if trigger.startswith("profit_stage"):
        if state.activated:
            return dedicated if _flag(settings, "core_runner_protect_profit_stages", True) else 0
        return candidate if _flag(settings, "core_runner_reserve_candidates_from_profit", True) else 0
    if trigger in {"profit_floor", "coordinated_break_even"}:
        if state.activated:
            return dedicated if _flag(settings, "core_runner_protect_break_even", True) else 0
        return candidate if _flag(settings, "core_runner_reserve_candidates_from_profit", True) else 0
    if trigger.startswith("loss_ladder"):
        if state.activated:
            return dedicated if _flag(settings, "core_runner_protect_loss_ladder", True) else 0
        return 0 if _flag(settings, "core_runner_loss_ladder_consumes_candidates", True) else candidate
    if trigger in {"coordinated_hard_stop", "coordinated_emergency_stop", "hard_stop", "stop_loss"}:
        return dedicated if state.activated and _flag(settings, "core_runner_protect_hard_stop", True) else 0
    if trigger in {"coordinated_trailing_stop", "trailing_stop"}:
        return dedicated if state.activated and _flag(settings, "core_runner_protect_ordinary_trailing", True) else 0
    if trigger == "reversal_warning":
        return dedicated if state.activated and _flag(settings, "core_runner_protect_reversal_warning", True) else 0
    if trigger == "reversal_confirmed":
        return 0 if _flag(settings, "core_runner_confirmed_reversal_exits", True) else dedicated
    if trigger in {"trim_alert", "sell_alert", "close_alert", "discord_sell_alert"}:
        return (
            dedicated
            if state.activated and _flag(settings, "core_runner_protect_contextual_trims", True)
            else 0
        )
    return dedicated if state.activated else 0


def cap_exit_quantity(
    decision: dict[str, Any],
    state: RunnerState,
    settings: dict[str, Any],
) -> dict[str, Any]:
    if not state.enabled or not decision.get("triggered"):
        return _merge_updates(decision, state.updates)

    result = _merge_updates(decision, state.updates)
    allocation_target = str(result.get("exit_allocation_target") or "core_only").strip().lower()
    remaining = state.core_quantity + state.protected_quantity
    requested = min(remaining, _quantity(result.get("quantity")))
    if allocation_target == "runners_only":
        permitted = min(requested, state.dedicated_quantity)
    elif allocation_target in {"entire_position", "core_then_runners"}:
        permitted = requested
    else:
        protected = protected_quantity_for_trigger(
            state,
            settings,
            str(result.get("exit_trigger") or ""),
        )
        permitted = min(requested, max(0, remaining - protected))
        result["exit_allocation_target"] = "core_only"

    if permitted <= 0:
        trigger = str(result.get("exit_trigger") or "exit")
        updates = dict(result.get("position_updates") or {})
        updates["core_runner_suppressed_trigger"] = trigger
        return {
            **result,
            "triggered": False,
            "action": "held",
            "quantity": 0,
            "target_remaining_quantity": remaining,
            "reason": f"{trigger} held to preserve protected runner contracts",
            "position_updates": updates,
        }

    result["quantity"] = permitted
    result["target_remaining_quantity"] = max(0, remaining - permitted)
    return result


def evaluate_runner_exit(
    position: dict[str, Any],
    settings: dict[str, Any],
    state: RunnerState,
    *,
    bid: float,
    ask: float,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if not state.enabled or not state.activated or state.dedicated_quantity <= 0:
        return None
    observed_at = _aware_utc(now)
    entry = _positive_float(position.get("entry_price"))
    if entry <= 0 or bid <= 0:
        return None

    stop_percent = _non_negative(settings.get("core_runner_catastrophic_stop_percent"), 65.0)
    return_percent = (bid - entry) / entry * 100.0
    if _runner_zero_dte_liquidation_due(position, settings, observed_at):
        return _runner_exit(
            "runner_0dte_liquidation",
            "runner 0DTE liquidation time reached",
            bid,
            state.dedicated_quantity,
            dict(state.updates),
        )

    if stop_percent > 0 and return_percent <= -stop_percent:
        updates = dict(state.updates)
        confirmed = _update_confirmation(
            position,
            updates,
            prefix="core_runner_catastrophic",
            required=_quantity(settings.get("core_runner_catastrophic_confirmations")) or 2,
            interval=_positive_float(settings.get("core_runner_catastrophic_confirmation_interval_seconds")) or 3.0,
            observed_at=observed_at,
        )
        if confirmed:
            return _runner_exit(
                "runner_catastrophic_stop",
                f"runner catastrophic stop hit at {return_percent:+.1f}%",
                bid,
                state.dedicated_quantity,
                updates,
            )
        return _runner_hold("runner_catastrophic_confirmation_pending", updates)

    if not _flag(settings, "core_runner_trailing_enabled", True):
        return None
    selected = _selected_trailing_tier(state.mfe_percent, settings)
    if selected is None:
        return None
    tier_mfe, trail_percent = selected
    highest = max(
        _positive_float(position.get("core_runner_highest_executable_bid")),
        _positive_float(position.get("highest_executable_bid")),
        bid,
    )
    spread = max(0.0, ask - bid)
    distance = max(
        highest * trail_percent / 100.0,
        _non_negative(settings.get("core_runner_min_trailing_cents"), 0.0) / 100.0,
        spread * _non_negative(settings.get("core_runner_spread_multiplier"), 2.0),
    )
    floor = max(0.01, highest - distance)
    previous_floor = _positive_float(position.get("core_runner_trailing_floor"))
    if previous_floor > 0 and not _flag(settings, "core_runner_allow_floor_to_move_down", False):
        floor = max(previous_floor, floor)
    updates = {
        **state.updates,
        "core_runner_trailing_armed": True,
        "core_runner_trailing_tier_mfe_percent": tier_mfe,
        "core_runner_trailing_percent": trail_percent,
        "core_runner_trailing_distance": round(distance, 4),
        "core_runner_trailing_floor": round(floor, 4),
    }

    if str(settings.get("core_runner_trailing_mode") or "tiered") == "underlying_confirmed":
        if str(position.get("reversal_state") or "").lower() not in {"confirmed", "reversal_confirmed"}:
            return _runner_hold("runner_underlying_confirmation_pending", updates)

    if bid > previous_floor and bid > floor:
        _clear_confirmation(updates, "core_runner_trailing")
        return _runner_hold("runner_trailing_held", updates)
    if bid <= floor:
        confirmed = _update_confirmation(
            position,
            updates,
            prefix="core_runner_trailing",
            required=_quantity(settings.get("core_runner_trailing_confirmations")) or 2,
            interval=_positive_float(settings.get("core_runner_trailing_confirmation_interval_seconds")) or 3.0,
            observed_at=observed_at,
        )
        if confirmed:
            return _runner_exit(
                "runner_trailing_stop",
                f"runner {trail_percent:.1f}% trail hit after +{state.mfe_percent:.1f}% MFE",
                bid,
                state.dedicated_quantity,
                updates,
            )
        return _runner_hold("runner_trailing_confirmation_pending", updates)
    _clear_confirmation(updates, "core_runner_trailing")
    return _runner_hold("runner_trailing_held", updates)


def _desired_runner_quantity(original: int, settings: dict[str, Any]) -> int:
    if original <= 0 or (original == 1 and not _flag(settings, "core_runner_allow_single_contract", False)):
        return 0
    mode = str(settings.get("core_runner_allocation_mode") or "greater_of").strip().lower()
    percent_quantity = int(original * _non_negative(settings.get("core_runner_allocation_percent"), 20.0) / 100.0)
    fixed = _quantity(settings.get("core_runner_fixed_contracts"))
    minimum = _quantity(settings.get("core_runner_min_contracts"))
    if mode == "fixed":
        desired = fixed
    elif mode == "percent":
        desired = max(percent_quantity, minimum if percent_quantity > 0 else 0)
    else:
        desired = max(percent_quantity, fixed, minimum)
    maximum = _quantity(settings.get("core_runner_max_contracts"))
    if maximum > 0:
        desired = min(desired, maximum)
    return min(original, max(0, desired))


def _selected_trailing_tier(mfe_percent: float, settings: dict[str, Any]) -> tuple[float, float] | None:
    mode = str(settings.get("core_runner_trailing_mode") or "tiered").strip().lower()
    activation = _non_negative(settings.get("core_runner_activation_mfe_percent"), 100.0)
    if mfe_percent < activation:
        return None
    if mode == "fixed":
        return activation, _positive_float(settings.get("core_runner_fixed_trailing_percent")) or 35.0
    selected: tuple[float, float] | None = None
    tiers = settings.get("core_runner_trailing_tiers")
    if not isinstance(tiers, list):
        return None
    for raw in tiers:
        if not isinstance(raw, dict):
            continue
        tier_mfe = _non_negative(raw.get("mfe_percent"), -1.0)
        width = _positive_float(raw.get("trail_percent"))
        if tier_mfe >= 0 and width > 0 and mfe_percent >= tier_mfe:
            selected = (tier_mfe, width)
    return selected


def _runner_zero_dte_liquidation_due(
    position: dict[str, Any],
    settings: dict[str, Any],
    observed_at: datetime,
) -> bool:
    if not _flag(settings, "core_runner_zero_dte_liquidation_enabled", True):
        return False
    eastern = observed_at.astimezone(ZoneInfo("America/New_York"))
    if canonical_expiration_yyyymmdd(position.get("expiration")) != eastern.date().isoformat():
        return False
    raw_cutoff = str(settings.get("core_runner_zero_dte_liquidation_time") or "15:40").strip()
    try:
        hour_text, minute_text = raw_cutoff.split(":", 1)
        cutoff = eastern.replace(
            hour=int(hour_text),
            minute=int(minute_text),
            second=0,
            microsecond=0,
        )
    except (TypeError, ValueError):
        return False
    return eastern >= cutoff


def _update_confirmation(
    position: dict[str, Any],
    updates: dict[str, Any],
    *,
    prefix: str,
    required: int,
    interval: float,
    observed_at: datetime,
) -> bool:
    count_key = f"{prefix}_confirmation_count"
    marker_key = f"{prefix}_last_quote_observed_at"
    time_key = f"{prefix}_last_confirmation_at"
    count = _quantity(position.get(count_key))
    marker = str(position.get("option_quote_observed_at") or observed_at.isoformat())
    previous_marker = str(position.get(marker_key) or "")
    previous_at = _parse_datetime(position.get(time_key))
    if marker != previous_marker and (not previous_at or (observed_at - previous_at).total_seconds() >= interval):
        count += 1
        updates[marker_key] = marker
        updates[time_key] = observed_at.isoformat()
    updates[count_key] = count
    return count >= max(1, required)


def _clear_confirmation(updates: dict[str, Any], prefix: str) -> None:
    updates[f"{prefix}_confirmation_count"] = 0
    updates[f"{prefix}_last_quote_observed_at"] = None
    updates[f"{prefix}_last_confirmation_at"] = None


def _runner_exit(trigger: str, reason: str, bid: float, quantity: int, updates: dict[str, Any]) -> dict[str, Any]:
    return {
        "triggered": True,
        "action": "sell",
        "exit_trigger": trigger,
        "reason": reason,
        "exit_price": bid,
        "quantity": quantity,
        "exit_allocation_target": "runners_only",
        "position_updates": updates,
    }


def _runner_hold(reason: str, updates: dict[str, Any]) -> dict[str, Any]:
    return {
        "triggered": False,
        "action": "held",
        "reason": reason,
        "position_updates": updates,
    }


def _merge_updates(decision: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    return {
        **decision,
        "position_updates": {**updates, **dict(decision.get("position_updates") or {})},
    }


def _flag(settings: dict[str, Any], key: str, default: bool) -> bool:
    return coerce_bool(settings.get(key), default=default)


def _quantity(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _positive_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _non_negative(value: Any, default: float) -> float:
    if value is None:
        return default
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _aware_utc(value: datetime | None) -> datetime:
    observed = value or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        return observed.replace(tzinfo=timezone.utc)
    return observed.astimezone(timezone.utc)
