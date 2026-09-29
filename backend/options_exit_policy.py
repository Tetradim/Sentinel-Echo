from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from statistics import fmean
from typing import Any

from core_runner_policy import cap_exit_quantity, evaluate_runner_exit, update_runner_state
from position_identity import canonical_expiration_yyyymmdd
from settings_flags import coerce_bool


@dataclass(frozen=True)
class PremiumExitProfile:
    tier: str
    activation_percent: float
    minimum_activation_cents: float
    trailing_percent: float
    minimum_trailing_cents: float
    break_even_activation_percent: float


def select_premium_exit_profile(
    position: dict[str, Any],
    settings: dict[str, Any],
    *,
    now: datetime | None = None,
) -> PremiumExitProfile:
    observed_at = _aware_utc(now)
    expiration = canonical_expiration_yyyymmdd(position.get("expiration"))
    zero_dte = expiration == observed_at.date().isoformat()
    entry_price = _positive_float(position.get("entry_price"))

    if zero_dte or entry_price < _setting(settings, "coordinated_low_premium_threshold", 0.30):
        profile = PremiumExitProfile(
            tier="zero_dte" if zero_dte else "low",
            activation_percent=_setting(settings, "coordinated_low_activation_percent", 25.0),
            minimum_activation_cents=_setting(settings, "coordinated_low_min_activation_cents", 5.0),
            trailing_percent=_setting(settings, "coordinated_low_trailing_percent", 18.0),
            minimum_trailing_cents=_setting(settings, "coordinated_low_min_trailing_cents", 4.0),
            break_even_activation_percent=_setting(
                settings, "coordinated_low_break_even_activation_percent", 25.0
            ),
        )
    elif entry_price <= _setting(settings, "coordinated_medium_premium_threshold", 1.00):
        profile = PremiumExitProfile(
            tier="medium",
            activation_percent=_setting(settings, "coordinated_medium_activation_percent", 20.0),
            minimum_activation_cents=0.0,
            trailing_percent=_setting(settings, "coordinated_medium_trailing_percent", 15.0),
            minimum_trailing_cents=0.0,
            break_even_activation_percent=_setting(
                settings, "coordinated_medium_break_even_activation_percent", 20.0
            ),
        )
    else:
        profile = PremiumExitProfile(
            tier="high",
            activation_percent=_setting(settings, "coordinated_high_activation_percent", 12.0),
            minimum_activation_cents=0.0,
            trailing_percent=_setting(settings, "coordinated_high_trailing_percent", 10.0),
            minimum_trailing_cents=0.0,
            break_even_activation_percent=_setting(
                settings, "coordinated_high_break_even_activation_percent", 12.0
            ),
        )
    if str(position.get("entry_exit_profile") or "").strip().lower() != "swing":
        return profile
    return PremiumExitProfile(
        tier=f"{profile.tier}_swing",
        activation_percent=max(
            profile.activation_percent,
            _setting(settings, "coordinated_swing_activation_percent", 30.0),
        ),
        minimum_activation_cents=profile.minimum_activation_cents,
        trailing_percent=max(
            profile.trailing_percent,
            _setting(settings, "coordinated_swing_trailing_percent", 25.0),
        ),
        minimum_trailing_cents=profile.minimum_trailing_cents,
        break_even_activation_percent=max(
            profile.break_even_activation_percent,
            _setting(settings, "coordinated_swing_break_even_activation_percent", 30.0),
        ),
    )


def is_trailing_protection_eligible(
    position: dict[str, Any],
    settings: dict[str, Any],
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether this contract has earned control by an active trailing policy."""
    if coerce_bool(position.get("coordinated_trailing_armed"), default=False):
        return True

    entry_price = _positive_float(position.get("entry_price"))
    coordinated_highest = max(
        _positive_float(position.get("highest_executable_bid")),
        _positive_float(position.get("option_bid")),
    )
    legacy_highest = max(
        _positive_float(position.get("highest_price")),
        _positive_float(position.get("current_price")),
    )
    if entry_price <= 0:
        return False

    if (
        coordinated_highest > entry_price
        and coerce_bool(settings.get("coordinated_exit_enabled"), default=True)
    ):
        profile = select_premium_exit_profile(position, settings, now=now)
        activation_price = max(
            entry_price * (1.0 + profile.activation_percent / 100.0),
            entry_price + profile.minimum_activation_cents / 100.0,
        )
        if coordinated_highest >= activation_price:
            return True

    if coerce_bool(settings.get("trailing_stop_enabled"), default=False):
        highest = max(coordinated_highest, legacy_highest)
        activation_percent = _positive_float(settings.get("trailing_stop_activation_percent"))
        return highest >= entry_price * (1.0 + activation_percent / 100.0)
    return False


def evaluate_coordinated_exit(
    position: dict[str, Any],
    settings: dict[str, Any],
    *,
    now: datetime | None = None,
    intelligence: Any = None,
) -> dict[str, Any]:
    """Return one deterministic exit transition using the executable option bid."""
    observed_at = _aware_utc(now)
    entry_price = _positive_float(position.get("entry_price"))
    bid = _positive_float(position.get("option_bid"))
    remaining = _quantity(position.get("remaining_quantity") or position.get("quantity"))
    original = max(remaining, _quantity(position.get("original_quantity")))
    if entry_price <= 0 or bid <= 0 or remaining <= 0:
        return _hold("invalid", "missing entry price, executable bid, or quantity")

    quote_age = _quote_age_seconds(position.get("option_quote_observed_at"), observed_at)
    max_quote_age = _setting(settings, "coordinated_exit_quote_max_age_seconds", 15.0)
    if quote_age is None or quote_age > max_quote_age:
        return _hold("stale_quote", "executable option bid is stale or undated")

    profile = select_premium_exit_profile(position, settings, now=observed_at)
    recorded_executable_high = _positive_float(position.get("highest_executable_bid"))
    highest = max(entry_price, bid, recorded_executable_high)
    updates: dict[str, Any] = {
        "highest_executable_bid": highest,
        "coordinated_exit_tier": profile.tier,
        "exit_policy_checked_at": observed_at.isoformat(),
        "exit_policy_bid": bid,
        "exit_policy_quote_age_seconds": round(quote_age, 3),
    }
    return_percent = (bid - entry_price) / entry_price * 100.0
    updates["coordinated_return_percent"] = round(return_percent, 3)

    runner_state = update_runner_state(position, settings, bid=bid, now=observed_at)
    updates.update(runner_state.updates)
    runner_decision = evaluate_runner_exit(
        position,
        settings,
        runner_state,
        bid=bid,
        ask=_positive_float(position.get("option_ask")),
        now=observed_at,
    )
    if runner_decision is not None:
        updates.update(dict(runner_decision.get("position_updates") or {}))

    def finalize(decision: dict[str, Any]) -> dict[str, Any]:
        merged = {
            **decision,
            "position_updates": {
                **updates,
                **dict(decision.get("position_updates") or {}),
            },
        }
        capped = cap_exit_quantity(merged, runner_state, settings)
        if (
            runner_decision is not None
            and runner_decision.get("triggered")
            and not capped.get("triggered")
        ):
            runner_merged = {
                **runner_decision,
                "position_updates": {
                    **updates,
                    **dict(runner_decision.get("position_updates") or {}),
                },
            }
            return cap_exit_quantity(runner_merged, runner_state, settings)
        return capped

    stop_percent = _hard_stop_percent(position, settings)
    emergency_percent = max(
        stop_percent,
        _setting(settings, "coordinated_emergency_stop_loss_percent", 50.0),
    )
    emergency_price = max(0.01, entry_price * (1.0 - emergency_percent / 100.0))
    if bid <= emergency_price:
        return finalize(_exit(
            "coordinated_emergency_stop",
            f"{emergency_percent:.0f}% emergency stop hit",
            bid,
            remaining,
            updates,
        ))

    source_stop_price = _positive_float(position.get("source_reported_stop_price"))
    if source_stop_price > 0 and bid <= source_stop_price:
        decision = _exit(
            "source_card_stop",
            f"source-reported stop hit at ${source_stop_price:.2f}",
            bid,
            remaining,
            updates,
        )
        decision["exit_allocation_target"] = "entire_position"
        return finalize(decision)

    floor_hold: dict[str, Any] | None = None
    floor_armed = coerce_bool(position.get("profit_floor_armed"), default=False)
    if floor_armed:
        floor_price = _positive_float(position.get("profit_floor_price")) or round(entry_price + 0.01, 2)
        if bid <= floor_price:
            floor_decision = finalize(_exit(
                "profit_floor",
                "permanent post-profit floor hit",
                bid,
                remaining,
                updates,
            ))
            if floor_decision.get("triggered"):
                return floor_decision
            updates.update(dict(floor_decision.get("position_updates") or {}))
            floor_hold = floor_decision
    else:
        break_even_activation_price = max(
            entry_price * (1.0 + profile.break_even_activation_percent / 100.0),
            entry_price + profile.minimum_activation_cents / 100.0,
        )
        reserved_runner_quantity = _int_setting(
            settings,
            "coordinated_runner_reserve_quantity",
            1,
            minimum=0,
        )
        break_even_runner_is_reserved = (
            coerce_bool(position.get("coordinated_break_even_runner_reserved"), default=False)
            and reserved_runner_quantity > 0
            and remaining <= reserved_runner_quantity
        )
        if highest >= break_even_activation_price and not break_even_runner_is_reserved:
            updates["coordinated_break_even_armed"] = True
            break_even_floor = round(entry_price + 0.01, 2)
            updates["coordinated_break_even_floor"] = break_even_floor
            if bid <= break_even_floor:
                required_confirmations = _int_setting(
                    settings,
                    "coordinated_break_even_required_confirmations",
                    2,
                    minimum=1,
                )
                confirmation_count = _quantity(
                    position.get("coordinated_break_even_confirmation_count")
                )
                quote_observed_at = _parsed_datetime(position.get("option_quote_observed_at"))
                quote_marker = quote_observed_at.isoformat() if quote_observed_at else ""
                last_quote_marker = str(
                    position.get("coordinated_break_even_last_quote_observed_at") or ""
                ).strip()
                last_confirmation_at = _parsed_datetime(
                    position.get("coordinated_break_even_last_confirmation_at")
                )
                minimum_interval = _setting(
                    settings,
                    "coordinated_break_even_confirmation_interval_seconds",
                    1.0,
                )
                distinct_quote = bool(quote_marker and quote_marker != last_quote_marker)
                interval_elapsed = (
                    last_confirmation_at is None
                    or quote_observed_at is None
                    or (quote_observed_at - last_confirmation_at).total_seconds() >= minimum_interval
                )
                if distinct_quote and interval_elapsed:
                    confirmation_count += 1
                    updates["coordinated_break_even_last_quote_observed_at"] = quote_marker
                    updates["coordinated_break_even_last_confirmation_at"] = observed_at.isoformat()
                updates["coordinated_break_even_confirmation_count"] = confirmation_count
                if confirmation_count < required_confirmations:
                    return finalize(_hold(
                        "break_even_confirmation_pending",
                        f"break-even guard awaiting {required_confirmations} distinct quotes",
                        updates,
                    ))

                quantity = remaining
                reserve = _runner_reserve(position, settings, remaining, observed_at)
                preserve_runner = coerce_bool(
                    settings.get("coordinated_break_even_preserve_runner"),
                    default=True,
                )
                if preserve_runner and reserve > 0 and remaining > reserve:
                    quantity = remaining - reserve
                    updates["coordinated_break_even_runner_reserved"] = True
                    updates["coordinated_break_even_runner_high"] = highest
                return finalize(_exit(
                    "coordinated_break_even",
                    f"{profile.tier} premium break-even guard confirmed",
                    bid,
                    quantity,
                    updates,
                ))
            if _quantity(position.get("coordinated_break_even_confirmation_count")):
                updates.update(
                    {
                        "coordinated_break_even_confirmation_count": 0,
                        "coordinated_break_even_last_quote_observed_at": None,
                        "coordinated_break_even_last_confirmation_at": None,
                    }
                )
        ladder_decision = _evaluate_loss_ladder(
            position,
            settings,
            entry_price=entry_price,
            bid=bid,
            original=original,
            remaining=remaining,
            return_percent=return_percent,
            observed_at=observed_at,
            updates=updates,
        )
        if ladder_decision is not None:
            return finalize(ladder_decision)

        hard_stop_decision = _evaluate_confirmed_hard_stop(
            position,
            settings,
            entry_price=entry_price,
            bid=bid,
            stop_percent=stop_percent,
            emergency_price=emergency_price,
            observed_at=observed_at,
            updates=updates,
        )
        if hard_stop_decision is not None:
            return finalize(hard_stop_decision)

    if floor_hold is not None:
        ladder_decision = _evaluate_loss_ladder(
            position,
            settings,
            entry_price=entry_price,
            bid=bid,
            original=original,
            remaining=remaining,
            return_percent=return_percent,
            observed_at=observed_at,
            updates=updates,
        )
        if ladder_decision is not None:
            return finalize(ladder_decision)
        hard_stop_decision = _evaluate_confirmed_hard_stop(
            position,
            settings,
            entry_price=entry_price,
            bid=bid,
            stop_percent=stop_percent,
            emergency_price=emergency_price,
            observed_at=observed_at,
            updates=updates,
        )
        if hard_stop_decision is not None:
            return finalize(hard_stop_decision)
        return floor_hold

    exit_profile = str(position.get("entry_exit_profile") or "").strip().lower()
    fast_scalp = exit_profile == "fast_scalp"
    swing = exit_profile == "swing"
    stage_one_target = _setting(
        settings,
        (
            "coordinated_fast_scalp_profit_stage_1_percent"
            if fast_scalp
            else "coordinated_swing_profit_stage_1_percent"
            if swing
            else "coordinated_profit_stage_1_percent"
        ),
        10.0 if fast_scalp else 50.0 if swing else 25.0,
    )
    if (
        not coerce_bool(position.get("profit_stage_1_completed"), default=False)
        and return_percent >= stage_one_target
    ):
        stage_quantity = _stage_quantity(
            original,
            remaining,
            _setting(settings, "coordinated_profit_stage_1_sell_percent", 50.0) / 100.0,
            reserve=_runner_reserve(position, settings, remaining, observed_at),
        )
        if stage_quantity > 0:
            return finalize(_exit(
                "profit_stage_1",
                f"first profit stage hit at +{stage_one_target:g}%",
                bid,
                stage_quantity,
                updates,
            ))
        updates["profit_stage_1_completed"] = True

    stage_two_target = _setting(
        settings,
        (
            "coordinated_fast_scalp_profit_stage_2_percent"
            if fast_scalp
            else "coordinated_swing_profit_stage_2_percent"
            if swing
            else "coordinated_profit_stage_2_percent"
        ),
        20.0 if fast_scalp else 100.0 if swing else 35.0,
    )
    if (
        (
            coerce_bool(position.get("profit_stage_1_completed"), default=False)
            or coerce_bool(updates.get("profit_stage_1_completed"), default=False)
        )
        and not coerce_bool(position.get("profit_stage_2_completed"), default=False)
        and return_percent >= stage_two_target
    ):
        stage_quantity = _stage_quantity(
            original,
            remaining,
            _setting(settings, "coordinated_profit_stage_2_sell_percent", 25.0) / 100.0,
            reserve=_runner_reserve(position, settings, remaining, observed_at),
        )
        if stage_quantity > 0:
            return finalize(_exit(
                "profit_stage_2",
                f"second profit stage hit at +{stage_two_target:g}%",
                bid,
                stage_quantity,
                updates,
            ))
        updates["profit_stage_2_completed"] = True

    if intelligence is not None and getattr(intelligence, "triggered", False):
        trigger = str(getattr(intelligence, "exit_trigger", "") or "reversal_warning")
        sell_percent = _positive_float(getattr(intelligence, "sell_percent", 0.0))
        if trigger in {"reversal_warning", "reversal_reduce"}:
            quantity = max(1, int(remaining * min(sell_percent or 25.0, 100.0) / 100.0))
        else:
            quantity = remaining
        return finalize(_exit(
            trigger,
            "; ".join(getattr(intelligence, "reasons", ()) or ("market reversal",)),
            bid,
            quantity,
            updates,
        ))

    trailing_mode = str(settings.get("coordinated_trailing_mode") or "tightening").strip().lower()
    activation_percent = (
        _non_negative_setting(settings, "coordinated_elastic_activation_percent", 5.0)
        if trailing_mode == "elastic"
        else profile.activation_percent
    )
    minimum_activation_cents = (
        _non_negative_setting(settings, "coordinated_elastic_min_activation_cents", 3.0)
        if trailing_mode == "elastic"
        else profile.minimum_activation_cents
    )
    activation_price = max(
        entry_price * (1.0 + activation_percent / 100.0),
        entry_price + minimum_activation_cents / 100.0,
    )
    if highest >= activation_price:
        updates["coordinated_trailing_armed"] = True
        trailing_percent, trailing_step, premium_volatility = _progressive_trailing_percent(
            position,
            settings,
            entry_price=entry_price,
            highest=highest,
            activation_percent=activation_percent,
            base_percent=profile.trailing_percent,
        )
        updates.update(
            {
                "coordinated_trailing_step": trailing_step,
                "coordinated_effective_trailing_percent": trailing_percent,
                "coordinated_premium_volatility_percent": premium_volatility,
            }
        )
        spread_distance = max(
            0.0,
            _positive_float(position.get("option_ask")) - bid,
        ) * _non_negative_setting(settings, "coordinated_trailing_spread_multiplier", 2.0)
        distance = max(
            highest * trailing_percent / 100.0,
            profile.minimum_trailing_cents / 100.0,
            spread_distance,
        )
        trailing_floor = max(0.01, highest - distance)
        if coerce_bool(position.get("coordinated_trailing_armed"), default=False):
            trailing_floor = max(
                trailing_floor,
                _positive_float(position.get("coordinated_trailing_floor")),
            )
        updates["coordinated_trailing_floor"] = round(trailing_floor, 4)
        updates["coordinated_trailing_distance"] = round(distance, 4)
        if bid <= trailing_floor:
            reserve = _runner_reserve(position, settings, remaining, observed_at)
            reserved_high = _positive_float(position.get("coordinated_break_even_runner_high"))
            runner_is_reserved = (
                coerce_bool(position.get("coordinated_break_even_runner_reserved"), default=False)
                and reserve > 0
                and remaining <= reserve
                and highest <= reserved_high
            )
            if runner_is_reserved:
                return finalize(_hold(
                    "break_even_runner_held",
                    "reserved runner awaits a new executable high or a hard stop",
                    updates,
                ))
            if reserved_high > 0 and highest > reserved_high:
                updates["coordinated_break_even_runner_reserved"] = False
            return finalize(_exit(
                "coordinated_trailing_stop",
                f"{profile.tier} premium trail hit after activation",
                bid,
                remaining,
                updates,
            ))

    return finalize({
        "triggered": False,
        "action": "peak_updated" if highest > recorded_executable_high else "held",
        "reason": "coordinated exit held",
        "highest_price": highest,
        "position_updates": updates,
    })


def _progressive_trailing_percent(
    position: dict[str, Any],
    settings: dict[str, Any],
    *,
    entry_price: float,
    highest: float,
    activation_percent: float,
    base_percent: float,
) -> tuple[float, int, float]:
    history = _premium_history(position.get("premium_mark_history"))
    volatility = _premium_volatility_percent(history)
    previous_step = _quantity(position.get("coordinated_trailing_step"))
    mode = str(settings.get("coordinated_trailing_mode") or "tightening").strip().lower()
    peak_return = max(0.0, (highest - entry_price) / entry_price * 100.0)
    available_gain = max(0.0, peak_return - activation_percent)

    if mode == "fixed":
        return round(base_percent, 3), previous_step, round(volatility, 3)

    if mode == "elastic":
        step_gain = _setting(settings, "coordinated_elastic_trailing_step_gain_percent", 10.0)
        widen = _setting(settings, "coordinated_elastic_trailing_step_widen_percent", 1.0)
        start = _setting(settings, "coordinated_elastic_trailing_start_percent", 6.0)
        maximum = _setting(settings, "coordinated_elastic_trailing_max_percent", 10.0)
        earned_step = int(available_gain // step_gain)
        selected_step = max(previous_step, earned_step)
        effective = min(maximum, start + selected_step * widen)
        return round(effective, 3), selected_step, round(volatility, 3)

    if not coerce_bool(
        settings.get("coordinated_progressive_trailing_enabled"),
        default=True,
    ):
        return round(base_percent, 3), previous_step, round(volatility, 3)

    step_gain = _setting(settings, "coordinated_trailing_step_gain_percent", 10.0)
    step_tighten = _setting(settings, "coordinated_trailing_step_tighten_percent", 1.0)
    minimum_percent = _setting(settings, "coordinated_trailing_min_percent", 8.0)
    volatility_gate = _setting(
        settings,
        "coordinated_trailing_volatility_gate_percent",
        8.0,
    )
    earned_step = int(available_gain // step_gain)

    enough_history = len(history) >= 3
    selected_step = max(previous_step, earned_step) if enough_history and volatility <= volatility_gate else previous_step
    effective = max(minimum_percent, base_percent - selected_step * step_tighten)
    previous_effective = _positive_float(
        position.get("coordinated_effective_trailing_percent")
    )
    if previous_effective > 0:
        effective = min(previous_effective, effective)
    return round(effective, 3), selected_step, round(volatility, 3)


def _premium_history(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    return [price for item in value if (price := _positive_float(item)) > 0]


def _premium_volatility_percent(history: list[float]) -> float:
    if len(history) < 2:
        return 0.0
    moves = [
        abs((current - previous) / previous) * 100.0
        for previous, current in zip(history, history[1:])
        if previous > 0
    ]
    return fmean(moves) if moves else 0.0


def _evaluate_loss_ladder(
    position: dict[str, Any],
    settings: dict[str, Any],
    *,
    entry_price: float,
    bid: float,
    original: int,
    remaining: int,
    return_percent: float,
    observed_at: datetime,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    if not coerce_bool(settings.get("coordinated_loss_ladder_enabled"), default=False):
        return None
    raw_steps = settings.get("coordinated_loss_ladder")
    if not isinstance(raw_steps, list):
        return None
    completed = {
        _quantity(value)
        for value in (position.get("coordinated_loss_ladder_completed_steps") or [])
    }
    selected: tuple[int, dict[str, Any]] | None = None
    for index, raw_step in enumerate(raw_steps):
        if index in completed or not isinstance(raw_step, dict):
            continue
        loss_percent = _positive_float(raw_step.get("loss_percent"))
        if loss_percent > 0 and return_percent <= -loss_percent:
            selected = (index, raw_step)
    if selected is None:
        if position.get("coordinated_loss_ladder_confirmation_step") is not None:
            updates.update(
                {
                    "coordinated_loss_ladder_confirmation_step": None,
                    "coordinated_loss_ladder_confirmation_count": 0,
                    "coordinated_loss_ladder_last_quote_observed_at": None,
                }
            )
        return None

    index, step = selected
    required = max(1, _quantity(step.get("confirmations")) or 2)
    previous_step = position.get("coordinated_loss_ladder_confirmation_step")
    count = _quantity(position.get("coordinated_loss_ladder_confirmation_count")) if previous_step == index else 0
    quote_marker = str(position.get("option_quote_observed_at") or observed_at.isoformat())
    last_marker = str(position.get("coordinated_loss_ladder_last_quote_observed_at") or "")
    if quote_marker != last_marker:
        count += 1
        updates["coordinated_loss_ladder_last_quote_observed_at"] = quote_marker
    updates["coordinated_loss_ladder_confirmation_step"] = index
    updates["coordinated_loss_ladder_confirmation_count"] = count
    if count < required:
        return _hold(
            "loss_ladder_confirmation_pending",
            f"loss ladder step {index + 1} requires {required} confirmations",
            updates,
        )

    target_quantity = _loss_ladder_cumulative_target(raw_steps, index, original)
    recorded_sold = _quantity(position.get("coordinated_loss_ladder_sold_quantity"))
    if recorded_sold <= 0 and completed:
        recorded_sold = _loss_ladder_cumulative_target(raw_steps, max(completed), original)
    quantity = min(remaining, max(0, target_quantity - recorded_sold))
    if quantity <= 0:
        return None
    updates.update(
        {
            "coordinated_loss_ladder_pending_step": index,
            "coordinated_loss_ladder_target_quantity": target_quantity,
            "coordinated_loss_ladder_confirmation_count": 0,
        }
    )
    decision = _exit(
        f"loss_ladder_{index + 1}",
        f"loss ladder step {index + 1} hit at {return_percent:.1f}%",
        bid,
        quantity,
        updates,
    )
    decision["exit_allocation_target"] = str(
        step.get("allocation_target") or "core_only"
    ).strip().lower()
    decision["target_remaining_quantity"] = max(0, remaining - quantity)
    return decision


def _loss_ladder_cumulative_target(
    raw_steps: list[Any],
    through_index: int,
    original: int,
) -> int:
    target = 0
    for raw_step in raw_steps[: through_index + 1]:
        if not isinstance(raw_step, dict):
            continue
        quantity_value = _positive_float(raw_step.get("quantity"))
        mode = str(raw_step.get("quantity_mode") or "percent_original").strip().lower()
        if mode == "fixed":
            target += int(quantity_value)
        elif mode == "percent_remaining" and quantity_value >= 100:
            target = original
        else:
            step_quantity = int(original * min(quantity_value, 100.0) / 100.0)
            if original > 1 and quantity_value > 0:
                step_quantity = max(1, step_quantity)
            target += step_quantity
        target = min(original, target)
    return target


def _evaluate_confirmed_hard_stop(
    position: dict[str, Any],
    settings: dict[str, Any],
    *,
    entry_price: float,
    bid: float,
    stop_percent: float,
    emergency_price: float,
    observed_at: datetime,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    stop_price = max(0.01, entry_price * (1.0 - stop_percent / 100.0))
    required_confirmations = _int_setting(
        settings,
        "coordinated_stop_required_confirmations",
        2,
        minimum=1,
    )
    updates.update(
        {
            "coordinated_stop_price": round(stop_price, 4),
            "coordinated_emergency_stop_price": round(emergency_price, 4),
            "coordinated_stop_required_confirmations": required_confirmations,
            "coordinated_stop_checked_at": observed_at.isoformat(),
        }
    )
    if bid <= stop_price:
        confirmation_count = _quantity(position.get("coordinated_stop_confirmation_count"))
        quote_observed_at = _parsed_datetime(position.get("option_quote_observed_at"))
        quote_marker = quote_observed_at.isoformat() if quote_observed_at else ""
        last_quote_marker = str(
            position.get("coordinated_stop_last_quote_observed_at") or ""
        ).strip()
        last_confirmation_at = _parsed_datetime(
            position.get("coordinated_stop_last_confirmation_at")
        )
        minimum_interval = _setting(
            settings,
            "coordinated_stop_confirmation_interval_seconds",
            1.0,
        )
        distinct_quote = bool(quote_marker and quote_marker != last_quote_marker)
        interval_elapsed = (
            last_confirmation_at is None
            or quote_observed_at is None
            or (quote_observed_at - last_confirmation_at).total_seconds() >= minimum_interval
        )
        if distinct_quote and interval_elapsed:
            confirmation_count += 1
            updates["coordinated_stop_last_quote_observed_at"] = quote_marker
            updates["coordinated_stop_last_confirmation_at"] = observed_at.isoformat()
        updates["coordinated_stop_confirmation_count"] = confirmation_count
        if confirmation_count >= required_confirmations:
            return _exit(
                "coordinated_hard_stop",
                f"{stop_percent:.0f}% hard stop confirmed by {confirmation_count} quotes",
                bid,
                _quantity(position.get("remaining_quantity") or position.get("quantity")),
                updates,
            )
        return _hold(
            "stop_confirmation_pending",
            f"hard stop awaiting {required_confirmations} distinct quotes",
            updates,
        )
    if _quantity(position.get("coordinated_stop_confirmation_count")):
        updates.update(
            {
                "coordinated_stop_confirmation_count": 0,
                "coordinated_stop_last_quote_observed_at": None,
                "coordinated_stop_last_confirmation_at": None,
            }
        )
    return None


def _hard_stop_percent(position: dict[str, Any], settings: dict[str, Any]) -> float:
    if str(position.get("entry_risk_profile") or "").strip().lower() == "high_risk":
        return _setting(settings, "coordinated_high_risk_stop_loss_percent", 50.0)
    return _setting(settings, "coordinated_normal_stop_loss_percent", 35.0)


def _stage_quantity(original: int, remaining: int, fraction: float, *, reserve: int = 0) -> int:
    available = max(0, remaining - max(0, reserve))
    if available <= 0:
        return 0
    return min(available, max(1, int(original * fraction)))


def _runner_reserve(
    position: dict[str, Any],
    settings: dict[str, Any],
    remaining: int,
    now: datetime,
) -> int:
    if not is_trailing_protection_eligible(position, settings, now=now):
        return 0
    configured = _int_setting(
        settings,
        "coordinated_runner_reserve_quantity",
        1,
        minimum=0,
    )
    return min(remaining, configured)


def _exit(
    trigger: str,
    reason: str,
    price: float,
    quantity: int,
    updates: dict[str, Any],
) -> dict[str, Any]:
    return {
        "triggered": True,
        "action": "triggered",
        "reason": reason,
        "exit_trigger": trigger,
        "exit_price": round(price, 2),
        "quantity": max(1, quantity),
        "position_updates": updates,
    }


def _hold(
    action: str,
    reason: str,
    updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "triggered": False,
        "action": action,
        "reason": reason,
        "position_updates": updates or {},
    }


def _quote_age_seconds(value: Any, now: datetime) -> float | None:
    if isinstance(value, datetime):
        observed_at = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            observed_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - observed_at.astimezone(timezone.utc)).total_seconds())


def _aware_utc(value: datetime | None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _parsed_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _setting(settings: dict[str, Any], key: str, default: float) -> float:
    try:
        value = float(settings.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _non_negative_setting(settings: dict[str, Any], key: str, default: float) -> float:
    try:
        value = float(settings.get(key, default))
    except (TypeError, ValueError):
        return default
    return max(0.0, value)


def _int_setting(
    settings: dict[str, Any],
    key: str,
    default: int,
    *,
    minimum: int,
) -> int:
    try:
        value = int(settings.get(key, default))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def _quantity(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def _positive_float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0
