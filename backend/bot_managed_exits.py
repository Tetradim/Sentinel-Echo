from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from fill_reconciliation import (
    BrokerOrderUpdate,
    OrderContext,
    fresh_position_lifecycle_state,
    reconcile_order_update,
    trade_owns_alert_status,
)
from order_execution import build_client_order_id
from operator_audit import record_operator_event
from position_identity import (
    canonical_expiration_yyyymmdd,
    contract_position_id,
    parse_alpaca_option_symbol,
    same_option_contract,
)
from settings_flags import coerce_bool
from market_exit_intelligence import MarketExitDecision, evaluate_market_exit_intelligence
from options_exit_policy import evaluate_coordinated_exit
from trailing_stop_engine import evaluate_trailing_stop


logger = logging.getLogger(__name__)

BROKER_CLOSED_POSITION_GRACE_SECONDS = 30
EASTERN = ZoneInfo("America/New_York")


async def run_bot_managed_exit_cycle(
    db,
    settings: dict[str, Any],
    broker_client,
    *,
    schedule_monitor: Callable[..., Any] | None = None,
    now: datetime | None = None,
) -> int:
    """Evaluate open positions and place Echo-managed SELL orders for hit exits."""
    settings = settings if isinstance(settings, dict) else {}
    if not _exit_worker_enabled(settings):
        return 0

    observed_at = _eastern_now(now)
    broker_positions, broker_positions_failed = await get_broker_positions_snapshot(broker_client)
    await _cancel_expiring_entry_orders(broker_client, settings, observed_at)
    await reconcile_pending_exit_orders(db, broker_client, settings)
    await _reconcile_missing_broker_positions(
        db,
        broker_client,
        settings,
        broker_positions=broker_positions,
        broker_positions_failed=broker_positions_failed,
    )
    await _reconcile_stale_local_positions(
        db,
        broker_client,
        settings,
        broker_positions=broker_positions,
        broker_positions_failed=broker_positions_failed,
    )
    open_positions = await db.get_positions("open")
    partial_positions = await db.get_positions("partial")
    positions = list(open_positions or []) + list(partial_positions or [])
    await _refresh_positions_from_broker(
        db,
        positions,
        broker_client,
        settings,
        broker_positions=broker_positions,
        broker_positions_failed=broker_positions_failed,
    )
    await _refresh_recent_closed_position_telemetry(
        db,
        broker_client,
        settings,
        now=observed_at,
    )
    pending_sells = await _pending_sell_trades_by_position(db)
    terminal_sells = await _terminal_sell_position_ids(db)
    submitted = 0

    for position in positions:
        position_id = str(position.get("id") or "").strip()
        if not position_id:
            continue
        pending_trade = pending_sells.get(position_id)
        if coerce_bool(position.get("exit_order_pending"), default=False):
            if pending_trade is None and position_id in terminal_sells:
                await _release_exit_reservation(db, position, position_id)
            elif pending_trade is None:
                continue
        if _is_expired(position.get("expiration"), today=observed_at.date()):
            continue
        if _active_broker(settings) and _position_broker(position) != _active_broker(settings):
            continue

        intelligence = await _refresh_market_exit_intelligence(
            db,
            position,
            settings,
            broker_client,
            now=observed_at,
        )
        evaluation_position = dict(position)
        pending_trigger = str((pending_trade or {}).get("exit_trigger") or "").strip().lower()
        if pending_trigger in {"profit_stage_1", "profit_stage_2"}:
            evaluation_position["profit_stage_1_completed"] = True
            evaluation_position["profit_stage_2_completed"] = True
        mandatory_exit = evaluate_zero_dte_liquidation(position, settings, now=observed_at)
        decision = mandatory_exit if mandatory_exit.get("triggered") else evaluate_position_exit(
            evaluation_position,
            settings,
            intelligence=intelligence,
            now=observed_at,
        )
        decision_updates = decision.get("position_updates") or {}
        if decision_updates:
            position.update(decision_updates)
            await db.update_position(position_id, {"$set": decision_updates})
        if decision.get("action") == "peak_updated":
            if not decision_updates:
                await db.update_position(position_id, {"$set": {"highest_price": decision["highest_price"]}})
            if pending_trade is None and position.get("exit_target_remaining_quantity") is None:
                continue

        target_decision = _maintained_target_decision(position)
        if target_decision is not None:
            if not decision.get("triggered") or _decision_target(position, target_decision) < _decision_target(position, decision):
                decision = target_decision

        if pending_trade is not None:
            if not _pending_exit_requires_replacement(
                position,
                pending_trade,
                decision,
                settings,
                now=observed_at,
            ):
                continue
            if not await _cancel_and_reconcile_pending_exit(
                db,
                broker_client,
                pending_trade,
                settings,
            ):
                continue
            refreshed = await db.get_position_by_id(position_id)
            if not refreshed:
                continue
            position = refreshed
            remaining = _remaining_quantity(position)
            decision_target = _decision_target(position, decision)
            target = (
                decision_target
                if decision.get("target_remaining_quantity") is not None
                else min(_stored_exit_target(position, remaining), decision_target)
            )
            if remaining <= target:
                await _clear_exit_target(db, position, position_id)
                continue
            decision = {
                **decision,
                "triggered": True,
                "action": "triggered",
                "quantity": remaining - target,
                "reason": f"maintaining exit target after replacing {pending_trade.get('exit_trigger') or 'pending exit'}",
            }

        if not decision.get("triggered"):
            continue

        trade = await _submit_exit_order(
            db,
            position,
            decision,
            settings,
            broker_client,
            schedule_monitor=schedule_monitor,
        )
        if trade:
            if decision.get("exit_trigger") == "mandatory_0dte_liquidation":
                started_at = observed_at.isoformat()
                position["zero_dte_liquidation_started_at"] = started_at
                await db.update_position(
                    position_id,
                    {"$set": {"zero_dte_liquidation_started_at": started_at}},
                )
                await record_operator_event(
                    db,
                    "trading",
                    "zero_dte_liquidation_started",
                    f"Mandatory 0DTE liquidation submitted for {position.get('ticker') or position_id}.",
                    severity="warning",
                    details={
                        "position_id": position_id,
                        "trade_id": trade.get("id"),
                        "quantity": trade.get("quantity"),
                        "cutoff": settings.get("zero_dte_liquidation_time") or "15:40",
                    },
                )
            pending_sells[position_id] = trade
            submitted += 1
    return submitted


async def _refresh_recent_closed_position_telemetry(
    db,
    broker_client,
    settings: dict[str, Any],
    *,
    now: datetime | None = None,
) -> int:
    """Record bounded post-exit option quotes without creating broker orders."""
    if not coerce_bool(settings.get("post_exit_telemetry_enabled"), default=True):
        return 0
    loader = getattr(broker_client, "get_option_market_context", None)
    if loader is None:
        return 0
    observed_at = _eastern_now(now)
    horizon_minutes = max(1.0, _positive_float(settings.get("post_exit_telemetry_minutes")) or 60.0)
    try:
        closed_positions = await db.get_positions("closed")
    except Exception as exc:
        logger.warning("Unable to load closed positions for post-exit telemetry: %s", exc)
        return 0

    refreshed = 0
    for position in closed_positions or []:
        position_id = str(position.get("id") or "").strip()
        closed_at = _parsed_datetime(position.get("closed_at"))
        if not position_id or closed_at is None:
            continue
        closed_at = closed_at.astimezone(EASTERN)
        telemetry_until = closed_at + timedelta(minutes=horizon_minutes)
        if observed_at < closed_at or observed_at > telemetry_until:
            continue
        if _active_broker(settings) and _position_broker(position) != _active_broker(settings):
            continue
        try:
            context = await loader(
                ticker=str(position.get("ticker") or "").upper(),
                strike=float(position.get("strike") or 0.0),
                option_type=str(position.get("option_type") or "").upper(),
                expiration=str(position.get("expiration") or ""),
            )
        except Exception as exc:
            logger.debug("Post-exit telemetry unavailable for %s: %s", position_id, exc)
            continue
        context = context if isinstance(context, dict) else {}
        bid = _positive_float(context.get("option_bid"))
        entry_price = _positive_float(position.get("entry_price"))
        if bid <= 0 or entry_price <= 0:
            continue
        highest_bid = max(bid, _positive_float(position.get("post_exit_highest_bid")))
        updates = {
            "post_exit_last_bid": bid,
            "post_exit_highest_bid": highest_bid,
            "post_exit_highest_return_percent": round(
                (highest_bid - entry_price) / entry_price * 100.0,
                3,
            ),
            "post_exit_quote_observed_at": (
                context.get("option_quote_observed_at") or observed_at.isoformat()
            ),
            "post_exit_telemetry_until": telemetry_until.isoformat(),
        }
        position.update(updates)
        await db.update_position(position_id, {"$set": updates})
        refreshed += 1
    return refreshed


def evaluate_position_exit(
    position: dict[str, Any],
    settings: dict[str, Any],
    *,
    intelligence: MarketExitDecision | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if coerce_bool(settings.get("coordinated_exit_enabled"), default=False):
        return evaluate_coordinated_exit(
            position,
            settings,
            now=now,
            intelligence=intelligence,
        )
    current_price = _positive_float(position.get("current_price"))
    entry_price = _positive_float(position.get("entry_price"))
    if current_price <= 0 or entry_price <= 0:
        return {"triggered": False, "action": "invalid", "reason": "missing current or entry price"}

    if coerce_bool(settings.get("take_profit_enabled"), default=False):
        take_profit_pct = _positive_float(settings.get("take_profit_percentage")) or 0.0
        take_profit = round(entry_price * (1 + take_profit_pct / 100), 4)
        take_profit_sell_pct = _positive_float(settings.get("take_profit_sell_percentage")) or 100.0
        partial_stage_completed = (
            take_profit_sell_pct < 100.0
            and coerce_bool(position.get("take_profit_stage_completed"), default=False)
        )
        if take_profit_pct > 0 and current_price >= take_profit and not partial_stage_completed:
            return {
                "triggered": True,
                "action": "triggered",
                "reason": "take profit hit",
                "exit_trigger": "take_profit",
                "exit_price": round(current_price, 2),
            }

    if coerce_bool(settings.get("stop_loss_enabled"), default=False):
        stop_loss_pct = _positive_float(settings.get("stop_loss_percentage")) or 0.0
        stop_loss = round(max(entry_price * (1 - stop_loss_pct / 100), 0.01), 4)
        if stop_loss_pct > 0 and current_price <= stop_loss:
            return {
                "triggered": True,
                "action": "triggered",
                "reason": "stop loss hit",
                "exit_trigger": "stop_loss",
                "exit_price": round(current_price, 2),
            }

    if coerce_bool(settings.get("break_even_enabled"), default=False):
        activation_type = str(settings.get("break_even_activation_type") or "percent").strip().lower()
        highest_price = _positive_float(position.get("highest_price")) or current_price
        if activation_type == "cents":
            activation_cents = _positive_float(settings.get("break_even_activation_cents")) or 0.0
            activation_price = round(entry_price + (activation_cents / 100), 4)
        else:
            activation_pct = _positive_float(settings.get("break_even_activation_percentage")) or 0.0
            activation_price = round(entry_price * (1 + activation_pct / 100), 4)
        break_even_price = round(entry_price, 4)
        if activation_price > entry_price and highest_price >= activation_price and current_price <= break_even_price:
            return {
                "triggered": True,
                "action": "triggered",
                "reason": "break even hit",
                "exit_trigger": "break_even",
                "exit_price": round(current_price, 2),
            }

    if intelligence is not None and intelligence.triggered:
        return {
            "triggered": True,
            "action": "triggered",
            "reason": "; ".join(intelligence.reasons),
            "exit_trigger": intelligence.exit_trigger,
            "exit_price": round(_positive_float(position.get("option_bid")) or current_price, 2),
            "sell_percentage": intelligence.sell_percent,
        }

    trailing_settings = dict(settings)
    adaptive_percent = _positive_float(position.get("adaptive_trailing_percent"))
    if adaptive_percent > 0:
        trailing_settings["trailing_stop_percent"] = adaptive_percent
    trailing = evaluate_trailing_stop(position, trailing_settings, current_price=current_price)
    if trailing.get("action") == "peak_updated":
        return trailing
    if trailing.get("triggered"):
        return {
            **trailing,
            "exit_trigger": "trailing_stop",
            "exit_price": round(float(trailing.get("exit_price") or current_price), 2),
        }

    return {"triggered": False, "action": "held", "reason": "no exit trigger hit"}


def evaluate_zero_dte_liquidation(
    position: dict[str, Any],
    settings: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not coerce_bool(settings.get("zero_dte_liquidation_enabled"), default=True):
        return {"triggered": False, "action": "disabled", "reason": "0DTE liquidation disabled"}
    observed_at = _eastern_now(now)
    if canonical_expiration_yyyymmdd(position.get("expiration")) != observed_at.date().isoformat():
        return {"triggered": False, "action": "held", "reason": "position does not expire today"}
    cutoff = _cutoff_time(settings.get("zero_dte_liquidation_time"))
    if observed_at.time().replace(tzinfo=None) < cutoff:
        return {"triggered": False, "action": "held", "reason": "0DTE cutoff not reached"}
    return {
        "triggered": True,
        "action": "triggered",
        "reason": "mandatory 0DTE liquidation cutoff reached",
        "exit_trigger": "mandatory_0dte_liquidation",
        "exit_price": round(
            _positive_float(position.get("option_bid"))
            or _positive_float(position.get("current_price")),
            2,
        ),
        "sell_percentage": 100.0,
    }


async def _refresh_market_exit_intelligence(
    db,
    position: dict[str, Any],
    settings: dict[str, Any],
    broker_client,
    *,
    now: datetime | None = None,
) -> MarketExitDecision | None:
    loader = getattr(broker_client, "get_option_market_context", None)
    if loader is None:
        await _mark_market_context_unavailable(db, position, now=now)
        return None
    previous_state = str(position.get("reversal_state") or "").strip().lower()
    previous_adaptive_percent = _positive_float(position.get("adaptive_trailing_percent"))
    try:
        context = await loader(
            ticker=str(position.get("ticker") or "").upper(),
            strike=float(position.get("strike") or 0.0),
            option_type=str(position.get("option_type") or "").upper(),
            expiration=str(position.get("expiration") or ""),
        )
    except Exception as exc:
        logger.warning("Market exit context unavailable for %s: %s", position.get("id"), exc)
        await _mark_market_context_unavailable(db, position, now=now)
        return None

    context = context if isinstance(context, dict) else {}
    intelligence = evaluate_market_exit_intelligence(
        position,
        settings,
        bars=context.get("bars") or [],
        option_bid=context.get("option_bid"),
        option_ask=context.get("option_ask"),
        now=now,
    )
    updates = dict(intelligence.position_updates)
    option_bid = _positive_float(context.get("option_bid"))
    option_ask = _positive_float(context.get("option_ask"))
    if option_bid > 0:
        updates.update(
            {
                "option_bid": option_bid,
                "option_ask": option_ask or None,
                "option_quote_observed_at": (
                    context.get("option_quote_observed_at") or _eastern_now(now).isoformat()
                ),
            }
        )
    if not intelligence.context_available and option_bid <= 0:
        updates.update(
            {
                "option_bid": None,
                "option_ask": None,
                "option_spread_percent": None,
                "adaptive_trailing_percent": None,
            }
        )
    elif not intelligence.context_available:
        updates.update(
            {
                "option_spread_percent": None,
                "adaptive_trailing_percent": None,
            }
        )
    position_id = str(position.get("id") or "").strip()
    if position_id and updates:
        position.update(updates)
        await db.update_position(position_id, {"$set": updates})
        await _record_intelligence_events(
            db,
            position,
            intelligence,
            previous_state=previous_state,
            previous_adaptive_percent=previous_adaptive_percent,
        )
    return intelligence


async def _mark_market_context_unavailable(
    db,
    position: dict[str, Any],
    *,
    now: datetime | None,
) -> None:
    position_id = str(position.get("id") or "").strip()
    if not position_id:
        return
    updates = {
        "option_bid": None,
        "option_ask": None,
        "option_spread_percent": None,
        "adaptive_trailing_percent": None,
        "market_intelligence_context_available": False,
        "market_intelligence_checked_at": _eastern_now(now).isoformat(),
    }
    position.update(updates)
    await db.update_position(position_id, {"$set": updates})


async def _record_intelligence_events(
    db,
    position: dict[str, Any],
    intelligence: MarketExitDecision,
    *,
    previous_state: str,
    previous_adaptive_percent: float,
) -> None:
    position_id = str(position.get("id") or "").strip()
    new_state = intelligence.reversal_state
    if new_state != previous_state and new_state in {
        "watching",
        "warning",
        "warning_observed",
        "confirmed",
        "reversal_observed",
        "reversal_reduce",
        "reversal_confirmed",
    }:
        await record_operator_event(
            db,
            "trading",
            "reversal_state_changed",
            f"Reversal state changed for {position.get('ticker') or position_id}: {new_state}.",
            severity="warning"
            if new_state in {"warning", "confirmed", "reversal_reduce", "reversal_confirmed"}
            else "info",
            details={
                "position_id": position_id,
                "from_state": previous_state or "unobserved",
                "to_state": new_state,
                "alignment_score": intelligence.alignment_score,
                "premium_drawdown_percent": intelligence.premium_drawdown_percent,
            },
        )

    new_adaptive_percent = _positive_float(intelligence.adaptive_trailing_percent)
    if (
        previous_adaptive_percent > 0
        and new_adaptive_percent > 0
        and abs(new_adaptive_percent - previous_adaptive_percent) >= 2.0
    ):
        await record_operator_event(
            db,
            "trading",
            "adaptive_trailing_changed",
            f"Adaptive trailing distance changed for {position.get('ticker') or position_id}.",
            details={
                "position_id": position_id,
                "from_percent": previous_adaptive_percent,
                "to_percent": new_adaptive_percent,
            },
        )


async def _cancel_expiring_entry_orders(
    broker_client,
    settings: dict[str, Any],
    now: datetime,
) -> int:
    if not coerce_bool(settings.get("zero_dte_liquidation_enabled"), default=True):
        return 0
    if now.time().replace(tzinfo=None) < _cutoff_time(settings.get("zero_dte_liquidation_time")):
        return 0
    list_orders = getattr(broker_client, "list_open_orders", None)
    cancel_order = getattr(broker_client, "cancel_order", None)
    if list_orders is None or cancel_order is None:
        return 0
    try:
        orders = await list_orders()
    except Exception as exc:
        logger.warning("Unable to list open orders at 0DTE cutoff: %s", exc)
        return 0

    cancelled = 0
    for order in orders or []:
        if not isinstance(order, dict) or str(order.get("side") or "").strip().lower() != "buy":
            continue
        parsed = parse_alpaca_option_symbol(order.get("symbol") or order.get("option_symbol")) or {}
        expiration = canonical_expiration_yyyymmdd(order.get("expiration") or parsed.get("expiration"))
        if expiration != now.date().isoformat():
            continue
        order_id = str(order.get("order_id") or order.get("id") or "").strip()
        if not order_id:
            continue
        try:
            result = await cancel_order(order_id)
        except Exception as exc:
            logger.warning("Unable to cancel expiring BUY order %s: %s", order_id, exc)
            continue
        if result is not False:
            cancelled += 1
    return cancelled


async def _refresh_positions_from_broker(
    db,
    positions: list[dict[str, Any]],
    broker_client,
    settings: dict[str, Any],
    *,
    broker_positions: list[dict[str, Any]] | None = None,
    broker_positions_failed: bool = False,
) -> None:
    if not positions or broker_client is None or not hasattr(broker_client, "list_positions"):
        return
    if broker_positions_failed:
        return
    if broker_positions is None:
        broker_positions, broker_positions_failed = await get_broker_positions_snapshot(broker_client)
        if broker_positions_failed:
            return
    if not broker_positions:
        return

    active_broker = _active_broker(settings)
    normalized = [
        position
        for raw_position in broker_positions
        if (position := _normalize_broker_position(raw_position, active_broker))
    ]
    if not normalized:
        return

    for local_position in positions:
        broker_position = next(
            (
                candidate
                for candidate in normalized
                if same_option_contract(candidate, local_position)
            ),
            None,
        )
        if not broker_position:
            continue
        position_id = str(local_position.get("id") or "").strip()
        if not position_id:
            continue
        current_price = _positive_float(broker_position.get("current_price"))
        entry_price = _positive_float(local_position.get("entry_price")) or _positive_float(
            broker_position.get("entry_price")
        )
        quantity = _remaining_quantity(broker_position)
        highest_price = max(
            _positive_float(local_position.get("highest_price")),
            current_price,
            entry_price,
        )
        updates = {
            "current_price": current_price,
            "highest_price": highest_price,
            "unrealized_pnl": round((current_price - entry_price) * quantity * 100, 2),
            "broker_quantity": quantity,
            "broker_mark_refreshed_at": _now(),
        }
        # The fill monitor owns quantity and realized-P&L reconciliation while an
        # exit is pending. Broker snapshots can reflect the fill first and must
        # not race that accounting update.
        if not coerce_bool(local_position.get("exit_order_pending"), default=False):
            updates.update(
                {
                    "remaining_quantity": quantity,
                    "quantity": quantity,
                }
            )
            if any(
                key in local_position
                for key in (
                    "core_runner_candidate_quantity",
                    "core_runner_dedicated_quantity",
                    "core_runner_core_quantity",
                )
            ):
                candidate = min(
                    quantity,
                    _int_quantity(local_position.get("core_runner_candidate_quantity")),
                )
                dedicated = min(
                    candidate,
                    _int_quantity(local_position.get("core_runner_dedicated_quantity")),
                )
                protected = (
                    dedicated
                    if coerce_bool(local_position.get("core_runner_activated"), default=False)
                    else candidate
                )
                updates.update(
                    {
                        "core_runner_candidate_quantity": candidate,
                        "core_runner_dedicated_quantity": dedicated,
                        "core_runner_core_quantity": max(0, quantity - protected),
                    }
                )
        local_position.update(updates)
        await db.update_position(position_id, {"$set": updates})


async def reconcile_broker_positions(
    db,
    broker_client,
    settings: dict[str, Any],
    *,
    broker_positions: list[dict[str, Any]] | None = None,
    broker_positions_failed: bool = False,
) -> int:
    """Insert local records for broker option positions missing from Echo state."""
    if broker_positions_failed:
        return 0
    if broker_positions is None:
        broker_positions, broker_positions_failed = await get_broker_positions_snapshot(broker_client)
        if broker_positions_failed:
            return 0
    if not broker_positions:
        return 0

    open_positions = await db.get_positions("open")
    partial_positions = await db.get_positions("partial")
    existing = list(open_positions or []) + list(partial_positions or [])
    all_positions = await db.get_positions()
    historical_by_id = {
        str(position.get("id") or ""): position
        for position in all_positions or []
        if str(position.get("id") or "")
    }
    inserted = 0
    active_broker = _active_broker(settings)

    for raw_position in broker_positions:
        position = _normalize_broker_position(raw_position, active_broker)
        if not position:
            continue
        if any(same_option_contract(position, local_position) for local_position in existing):
            continue
        historical_position = historical_by_id.get(position["id"])
        if historical_position and _recently_closed_position(historical_position):
            continue
        if historical_position:
            await db.update_position(position["id"], {"$set": position})
            existing.append(position)
            inserted += 1
            continue
        await db.insert_position(position)
        existing.append(position)
        inserted += 1
    return inserted


async def reconcile_local_positions_against_broker(
    db,
    broker_client,
    settings: dict[str, Any],
    *,
    broker_positions: list[dict[str, Any]] | None = None,
    broker_positions_failed: bool = False,
) -> dict[str, int]:
    """Close local option rows that the broker no longer reports as open."""
    if broker_client is None or not hasattr(broker_client, "list_positions"):
        return {"checked": 0, "closed": 0}

    if broker_positions_failed:
        return {"checked": 0, "closed": 0}
    if broker_positions is None:
        broker_positions, broker_positions_failed = await get_broker_positions_snapshot(broker_client)
        if broker_positions_failed:
            return {"checked": 0, "closed": 0}

    active_broker = _active_broker(settings)
    normalized_broker_positions = [
        position
        for raw_position in broker_positions or []
        if (position := _normalize_broker_position(raw_position, active_broker))
    ]
    open_positions = await db.get_positions("open")
    partial_positions = await db.get_positions("partial")
    local_positions = list(open_positions or []) + list(partial_positions or [])

    checked = 0
    closed = 0
    for local_position in local_positions:
        if active_broker and _position_broker(local_position) != active_broker:
            continue
        if not _is_option_position(local_position):
            continue
        if not _has_broker_position_evidence(local_position):
            continue
        if coerce_bool(local_position.get("exit_order_pending"), default=False):
            continue
        checked += 1
        if any(same_option_contract(candidate, local_position) for candidate in normalized_broker_positions):
            continue

        position_id = str(local_position.get("id") or "").strip()
        if not position_id:
            continue
        await db.update_position(
            position_id,
            {
                "$set": {
                    "status": "closed",
                    "remaining_quantity": 0,
                    "quantity": 0,
                    "unrealized_pnl": 0.0,
                    "closed_at": _now(),
                    "broker_reconciliation": "closed_absent_at_broker",
                }
            },
        )
        closed += 1

    return {"checked": checked, "closed": closed}


def _recently_closed_position(position: dict[str, Any]) -> bool:
    if str(position.get("status") or "").strip().lower() != "closed":
        return False
    raw_closed_at = str(position.get("closed_at") or "").strip()
    if not raw_closed_at:
        return False
    try:
        closed_at = datetime.fromisoformat(raw_closed_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if closed_at.tzinfo is None:
        closed_at = closed_at.replace(tzinfo=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - closed_at).total_seconds()
    return 0 <= age_seconds <= BROKER_CLOSED_POSITION_GRACE_SECONDS


def _exit_worker_interval_seconds(
    settings: dict[str, Any],
    *,
    default_interval: float = 5.0,
) -> float:
    intervals = [max(1.0, float(default_interval))]
    for key in ("exit_reprice_interval_seconds", "profit_exit_reprice_interval_seconds"):
        try:
            configured = float(settings.get(key))
        except (TypeError, ValueError):
            continue
        if configured > 0:
            intervals.append(max(1.0, configured))
    return min(intervals)


async def start_bot_managed_exit_worker(
    db,
    settings: dict[str, Any],
    *,
    broker_client=None,
    interval_seconds: float = 5.0,
) -> asyncio.Task | None:
    if not _exit_worker_enabled(settings):
        return None
    if broker_client is None:
        from order_execution import get_configured_broker_client

        broker_client = get_configured_broker_client(
            settings,
            _active_broker(settings),
            require_order_status=True,
        )

    async def loop() -> None:
        while True:
            loop_settings = settings
            try:
                if hasattr(db, "get_settings"):
                    loaded_settings = await db.get_settings()
                    if isinstance(loaded_settings, dict):
                        loop_settings = loaded_settings
                await run_bot_managed_exit_cycle(db, loop_settings, broker_client)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Bot-managed exit cycle failed: %s", exc)
            await asyncio.sleep(
                _exit_worker_interval_seconds(
                    loop_settings,
                    default_interval=interval_seconds,
                )
            )

    return asyncio.create_task(loop())


async def _submit_exit_order(
    db,
    position: dict[str, Any],
    decision: dict[str, Any],
    settings: dict[str, Any],
    broker_client,
    *,
    schedule_monitor: Callable[..., Any] | None,
) -> dict[str, Any] | None:
    remaining = _remaining_quantity(position)
    requested_quantity = _exit_quantity_for_decision(position, settings, decision)
    requested_target = (
        _decision_target(position, decision)
        if decision.get("target_remaining_quantity") is not None
        else max(0, remaining - requested_quantity)
    )
    target = (
        requested_target
        if decision.get("target_remaining_quantity") is not None
        else min(_stored_exit_target(position, remaining), requested_target)
    )
    quantity = max(0, remaining - target)
    exit_trigger = str(decision.get("exit_trigger") or "bot_managed_exit")
    allocation_target = str(
        decision.get("exit_allocation_target") or "entire_position"
    ).strip().lower()
    executable_bid = (
        _positive_float(position.get("option_bid"))
        or _positive_float(decision.get("exit_price"))
        or _positive_float(position.get("current_price"))
    )
    price = executable_bid
    if exit_trigger in {"profit_stage_1", "profit_stage_2"}:
        offset = _non_negative_float(
            settings.get("profit_exit_marketable_offset_cents"),
            default=1.0,
        )
        price = max(0.01, executable_bid - offset / 100.0)
    price = round(price, 2)
    if quantity <= 0 or price <= 0:
        return None

    trade_id = f"trade-{uuid.uuid4()}"
    position_id = str(position.get("id") or "")
    reservation_token = str(uuid.uuid4())
    reservation = {
        "exit_order_pending": True,
        "exit_order_id": None,
        "exit_reservation_token": reservation_token,
        "exit_reservation_trigger": exit_trigger,
        "exit_reservation_created_at": _now(),
        "exit_target_remaining_quantity": target,
        "exit_target_trigger": exit_trigger,
        "exit_target_allocation_target": allocation_target,
        "exit_target_updated_at": _now(),
    }
    await db.update_position(position_id, {"$set": reservation})
    position.update(reservation)
    try:
        order_result = await broker_client.place_order(
            ticker=str(position.get("ticker") or "").upper(),
            strike=float(position.get("strike") or 0.0),
            option_type=str(position.get("option_type") or "").upper(),
            expiration=str(position.get("expiration") or ""),
            side="SELL",
            quantity=quantity,
            price=price,
            client_order_id=build_client_order_id(trade_id, exit_trigger, position_id),
        )
    except Exception:
        await _release_exit_reservation(db, position, position_id)
        raise
    order_id = str(order_result.get("order_id") or "").strip()
    if not order_id:
        logger.error("Bot-managed exit order failed for %s: %s", position_id, order_result.get("error"))
        await _release_exit_reservation(db, position, position_id)
        return None
    await db.update_position(position_id, {"$set": {"exit_order_id": order_id}})
    position["exit_order_id"] = order_id

    trade = {
        "id": trade_id,
        "alert_id": position.get("alert_id", ""),
        "position_id": position_id,
        "ticker": position.get("ticker"),
        "strike": position.get("strike"),
        "option_type": position.get("option_type"),
        "expiration": position.get("expiration"),
        "entry_price": position.get("entry_price"),
        "exit_price": price,
        "quantity": quantity,
        "side": "SELL",
        "broker": _active_broker(settings) or position.get("broker", ""),
        "status": "pending",
        "order_id": order_id,
        "exit_trigger": exit_trigger,
        "exit_allocation_target": allocation_target,
        "target_remaining_quantity": target,
        "created_at": _now(),
        "simulated": False,
        "alert_status_owned": False,
    }
    await db.insert_trade(trade)
    try:
        await record_operator_event(
            db,
            "trading",
            "coordinated_exit_submitted",
            f"Submitted {exit_trigger} exit for {position.get('ticker') or position_id}.",
            details={
                "position_id": position_id,
                "trade_id": trade_id,
                "order_id": order_id,
                "exit_trigger": exit_trigger,
                "reason": decision.get("reason"),
                "quantity": quantity,
                "exit_allocation_target": allocation_target,
                "target_remaining_quantity": target,
                "remaining_quantity_before": _remaining_quantity(position),
                "executable_bid": _positive_float(position.get("option_bid")),
                "highest_executable_bid": _positive_float(position.get("highest_executable_bid")),
                "premium_tier": position.get("coordinated_exit_tier"),
            },
        )
    except Exception as exc:
        logger.warning("Unable to persist coordinated exit audit for %s: %s", position_id, exc)

    monitor_scheduler = schedule_monitor or _default_schedule_monitor
    result = monitor_scheduler(
        order_context=OrderContext(
            trade_id=trade_id,
            order_id=order_id,
            side="SELL",
            ticker=str(position.get("ticker") or "").upper(),
            strike=float(position.get("strike") or 0.0),
            option_type=str(position.get("option_type") or "").upper(),
            expiration=str(position.get("expiration") or ""),
            requested_quantity=quantity,
            broker=_active_broker(settings) or position.get("broker", ""),
            position_id=position_id,
            alert_id=position.get("alert_id"),
            alert_price=price,
            simulated=False,
            exit_trigger=exit_trigger,
            exit_allocation_target=allocation_target,
            target_remaining_quantity=target,
            update_alert_status=False,
        ),
        broker_client=broker_client,
        db=db,
        settings=settings,
    )
    if asyncio.iscoroutine(result):
        await result
    return trade


def _default_schedule_monitor(**kwargs) -> None:
    from fill_monitor import monitor_fill

    asyncio.create_task(monitor_fill(**kwargs))


async def get_broker_positions_snapshot(broker_client) -> tuple[list[dict[str, Any]], bool]:
    """Fetch broker positions once and return (positions, failed)."""
    if broker_client is None or not hasattr(broker_client, "list_positions"):
        return [], False
    try:
        broker_positions = await broker_client.list_positions()
    except Exception as exc:
        logger.warning("Unable to list broker positions: %s", exc)
        return [], True
    if _broker_position_list_failed(broker_client):
        logger.warning(
            "Unable to list broker positions: %s",
            str(getattr(broker_client, "last_positions_error", "") or "broker position list failed"),
        )
        return [], True
    if isinstance(broker_positions, list):
        return broker_positions, False
    if broker_positions:
        return [broker_positions], False
    return [], False


async def _reconcile_missing_broker_positions(
    db,
    broker_client,
    settings: dict[str, Any],
    *,
    broker_positions: list[dict[str, Any]] | None = None,
    broker_positions_failed: bool = False,
) -> int:
    if broker_client is None or not hasattr(broker_client, "list_positions"):
        return 0
    try:
        return await reconcile_broker_positions(
            db,
            broker_client,
            settings,
            broker_positions=broker_positions,
            broker_positions_failed=broker_positions_failed,
        )
    except Exception as exc:
        logger.warning("Unable to reconcile broker positions before exit evaluation: %s", exc)
        return 0


async def _reconcile_stale_local_positions(
    db,
    broker_client,
    settings: dict[str, Any],
    *,
    broker_positions: list[dict[str, Any]] | None = None,
    broker_positions_failed: bool = False,
) -> dict[str, int]:
    try:
        return await reconcile_local_positions_against_broker(
            db,
            broker_client,
            settings,
            broker_positions=broker_positions,
            broker_positions_failed=broker_positions_failed,
        )
    except Exception as exc:
        logger.warning("Unable to reconcile local positions against broker before exit evaluation: %s", exc)
        return {"checked": 0, "closed": 0}


async def _pending_sell_position_ids(db) -> set[str]:
    try:
        trades = await db.get_trades(limit=500)
    except Exception:
        return set()
    return {
        str(trade.get("position_id") or "").strip()
        for trade in trades
        if str(trade.get("side") or "").upper() == "SELL"
        and str(trade.get("status") or "").lower() in {"pending", "partial", "unconfirmed", "pending_broker"}
        and str(trade.get("position_id") or "").strip()
    }


async def _pending_sell_trades_by_position(db) -> dict[str, dict[str, Any]]:
    try:
        trades = await db.get_trades(limit=500)
    except Exception:
        return {}
    pending_statuses = {"pending", "partial", "unconfirmed", "pending_broker", "submitted"}
    result: dict[str, dict[str, Any]] = {}
    for trade in trades or []:
        position_id = str(trade.get("position_id") or "").strip()
        if (
            position_id
            and str(trade.get("side") or "").upper() == "SELL"
            and str(trade.get("status") or "").lower() in pending_statuses
        ):
            result.setdefault(position_id, trade)
    return result


async def reconcile_pending_exit_orders(
    db,
    broker_client,
    settings: dict[str, Any],
) -> int:
    """Repair sell state from broker truth before any position is skipped."""
    if broker_client is None or not hasattr(broker_client, "get_order_status"):
        return 0
    try:
        trades = await db.get_trades(limit=500)
        positions = list(await db.get_positions("open") or []) + list(
            await db.get_positions("partial") or []
        )
    except Exception as exc:
        logger.warning("Unable to load pending exits for reconciliation: %s", exc)
        return 0

    reserved_order_ids = {
        str(position.get("exit_order_id") or "").strip()
        for position in positions
        if coerce_bool(position.get("exit_order_pending"), default=False)
    }
    active_statuses = {"pending", "partial", "unconfirmed", "pending_broker", "submitted"}
    repaired = 0
    for trade in trades or []:
        order_id = str(trade.get("order_id") or "").strip()
        if str(trade.get("side") or "").upper() != "SELL" or not order_id:
            continue
        trade_status = str(trade.get("status") or "").lower()
        if trade_status not in active_statuses and order_id not in reserved_order_ids:
            continue
        recovered_position_id = _position_id_for_trade(trade, positions)
        if recovered_position_id and not str(trade.get("position_id") or "").strip():
            trade["position_id"] = recovered_position_id
            await db.update_trade(str(trade.get("id") or ""), {"position_id": recovered_position_id})
        context = _trade_order_context(trade)
        if context is None:
            continue
        try:
            status_data = await broker_client.get_order_status(order_id)
        except Exception as exc:
            logger.warning("Unable to reconcile pending exit %s: %s", order_id, exc)
            continue
        status = str(status_data.get("status") or "unknown").lower()
        if status not in {"filled", "cancelled", "canceled", "expired", "rejected"}:
            continue
        await reconcile_order_update(
            db,
            context,
            BrokerOrderUpdate(
                status=status,
                filled_qty=_int_quantity(status_data.get("filled_qty")),
                avg_fill_price=_positive_float(status_data.get("avg_fill_price")),
                reason=str(status_data.get("reason") or status),
            ),
            settings=settings,
        )
        repaired += 1
    return repaired


def _position_id_for_trade(
    trade: dict[str, Any],
    positions: list[dict[str, Any]],
) -> str | None:
    explicit_position_id = str(trade.get("position_id") or "").strip()
    if explicit_position_id:
        return explicit_position_id
    order_id = str(trade.get("order_id") or "").strip()
    if not order_id:
        return None
    matches = [
        str(position.get("id") or "").strip()
        for position in positions or []
        if str(position.get("exit_order_id") or "").strip() == order_id
        and str(position.get("id") or "").strip()
    ]
    return matches[0] if len(matches) == 1 else None


def _maintained_target_decision(position: dict[str, Any]) -> dict[str, Any] | None:
    if position.get("exit_target_remaining_quantity") is None:
        return None
    remaining = _remaining_quantity(position)
    target = _stored_exit_target(position, remaining)
    if remaining <= target:
        return None
    trigger = str(position.get("exit_target_trigger") or "exit_target_maintenance")
    return {
        "triggered": True,
        "action": "triggered",
        "reason": "broker exposure remains above the maintained exit target",
        "exit_trigger": trigger,
        "quantity": remaining - target,
        "target_remaining_quantity": target,
        "exit_allocation_target": str(
            position.get("exit_target_allocation_target") or "entire_position"
        ),
        "exit_price": _positive_float(position.get("option_bid"))
        or _positive_float(position.get("current_price")),
    }


def _decision_target(position: dict[str, Any], decision: dict[str, Any]) -> int:
    remaining = _remaining_quantity(position)
    explicit_target = decision.get("target_remaining_quantity")
    if explicit_target is not None:
        return min(remaining, _int_quantity(explicit_target))
    explicit_quantity = _int_quantity(decision.get("quantity"))
    if explicit_quantity > 0:
        return max(0, remaining - min(remaining, explicit_quantity))
    sell_percentage = _positive_float(decision.get("sell_percentage"))
    if sell_percentage > 0:
        quantity = max(1, int(remaining * min(100.0, sell_percentage) / 100.0))
        return max(0, remaining - min(remaining, quantity))
    return 0 if decision.get("triggered") else remaining


def _stored_exit_target(position: dict[str, Any], remaining: int) -> int:
    raw_target = position.get("exit_target_remaining_quantity")
    if raw_target is None:
        return remaining
    return min(remaining, _int_quantity(raw_target))


def _pending_exit_requires_replacement(
    position: dict[str, Any],
    pending_trade: dict[str, Any],
    decision: dict[str, Any],
    settings: dict[str, Any],
    *,
    now: datetime,
) -> bool:
    if not decision.get("triggered"):
        return False
    remaining = _remaining_quantity(position)
    raw_target = position.get("exit_target_remaining_quantity")
    if raw_target is None:
        pending_quantity = min(remaining, _int_quantity(pending_trade.get("quantity")))
        current_target = max(0, remaining - pending_quantity)
    else:
        current_target = _stored_exit_target(position, remaining)
    new_target = _decision_target(position, decision)
    if new_target != current_target:
        return True

    current_priority = _exit_trigger_priority(pending_trade.get("exit_trigger"))
    new_priority = _exit_trigger_priority(decision.get("exit_trigger"))
    if new_priority > current_priority:
        return True

    created_at = _parsed_datetime(
        position.get("exit_reservation_created_at") or pending_trade.get("created_at")
    )
    pending_trigger = str(pending_trade.get("exit_trigger") or "").strip().lower()
    patient_triggers = {"profit_stage_1", "profit_stage_2", "take_profit", "trim_alert"}
    interval_key = (
        "profit_exit_reprice_interval_seconds"
        if pending_trigger in patient_triggers
        else "exit_reprice_interval_seconds"
    )
    default_interval = 12 if pending_trigger in patient_triggers else 5
    timeout_seconds = max(1, _int_quantity(settings.get(interval_key) or default_interval))
    return created_at is not None and (now.astimezone(timezone.utc) - created_at).total_seconds() >= timeout_seconds


def _exit_trigger_priority(value: Any) -> int:
    trigger = str(value or "").strip().lower()
    if trigger in {
        "mandatory_0dte_liquidation",
        "coordinated_emergency_stop",
        "runner_catastrophic_stop",
        "runner_0dte_liquidation",
    }:
        return 100
    if trigger in {
        "profit_floor",
        "coordinated_break_even",
        "coordinated_hard_stop",
        "coordinated_trailing_stop",
        "runner_trailing_stop",
        "reversal_confirmed",
        "sell_alert",
        "close_alert",
        "discord_sell_alert",
    }:
        return 80
    if trigger in {"reversal_warning", "reversal_reduce", "trim_alert"}:
        return 50
    if trigger in {"profit_stage_1", "profit_stage_2", "take_profit"}:
        return 20
    return 10


async def _cancel_and_reconcile_pending_exit(
    db,
    broker_client,
    pending_trade: dict[str, Any],
    settings: dict[str, Any],
) -> bool:
    if not hasattr(broker_client, "cancel_order") or not hasattr(broker_client, "get_order_status"):
        return False
    context = _trade_order_context(pending_trade)
    if context is None:
        return False
    try:
        await broker_client.cancel_order(context.order_id)
        for attempt in range(8):
            status_data = await broker_client.get_order_status(context.order_id)
            status = str(status_data.get("status") or "unknown").lower()
            if status in {"filled", "cancelled", "canceled", "expired", "rejected"}:
                await reconcile_order_update(
                    db,
                    context,
                    BrokerOrderUpdate(
                        status=status,
                        filled_qty=_int_quantity(status_data.get("filled_qty")),
                        avg_fill_price=_positive_float(status_data.get("avg_fill_price")),
                        reason=str(status_data.get("reason") or "replaced by maintained exit target"),
                    ),
                    settings=settings,
                )
                return True
            if attempt < 7:
                await asyncio.sleep(0.25)
    except Exception as exc:
        logger.warning("Unable to replace pending exit %s: %s", context.order_id, exc)
    return False


def _trade_order_context(trade: dict[str, Any]) -> OrderContext | None:
    order_id = str(trade.get("order_id") or "").strip()
    trade_id = str(trade.get("id") or "").strip()
    if not trade_id or not order_id:
        return None
    return OrderContext(
        trade_id=trade_id,
        order_id=order_id,
        side=str(trade.get("side") or "SELL").upper(),
        ticker=str(trade.get("ticker") or ""),
        strike=float(trade.get("strike") or 0.0),
        option_type=str(trade.get("option_type") or ""),
        expiration=str(trade.get("expiration") or ""),
        requested_quantity=max(1, _int_quantity(trade.get("quantity"))),
        broker=str(trade.get("broker") or ""),
        position_id=trade.get("position_id"),
        alert_id=trade.get("alert_id"),
        alert_price=_positive_float(trade.get("entry_price") or trade.get("exit_price")) or None,
        simulated=bool(trade.get("simulated")),
        sell_percentage=trade.get("sell_percentage"),
        exit_trigger=trade.get("exit_trigger"),
        exit_allocation_target=trade.get("exit_allocation_target"),
        target_remaining_quantity=trade.get("target_remaining_quantity"),
        entry_risk_profile=str(trade.get("entry_risk_profile") or "normal"),
        max_loss_budget=trade.get("max_loss_budget"),
        estimated_stop_loss_percent=trade.get("estimated_stop_loss_percent"),
        source_reported_stop_price=trade.get("source_reported_stop_price"),
        source_reported_stop_percent=trade.get("source_reported_stop_percent"),
        source_reported_break_even_stop=bool(trade.get("source_reported_break_even_stop")),
        update_alert_status=trade_owns_alert_status(trade),
    )


async def _clear_exit_target(db, position: dict[str, Any], position_id: str) -> None:
    updates = {
        "exit_target_remaining_quantity": None,
        "exit_target_trigger": None,
        "exit_target_allocation_target": None,
        "exit_target_updated_at": None,
    }
    await db.update_position(position_id, {"$set": updates})
    position.update(updates)


async def _terminal_sell_position_ids(db) -> set[str]:
    try:
        trades = await db.get_trades(limit=500)
    except Exception:
        return set()
    terminal_statuses = {"failed", "cancelled", "canceled", "expired", "rejected"}
    return {
        str(trade.get("position_id") or "").strip()
        for trade in trades
        if str(trade.get("side") or "").upper() == "SELL"
        and str(trade.get("status") or "").lower() in terminal_statuses
        and str(trade.get("position_id") or "").strip()
    }


def _normalize_broker_position(raw_position: dict[str, Any], active_broker: str) -> dict[str, Any] | None:
    raw_position = raw_position if isinstance(raw_position, dict) else {}
    symbol_parts = parse_alpaca_option_symbol(raw_position.get("symbol")) or {}
    ticker = str(raw_position.get("ticker") or symbol_parts.get("ticker") or "").strip().upper()
    strike = _positive_float(raw_position.get("strike") or symbol_parts.get("strike"))
    option_type = str(raw_position.get("option_type") or symbol_parts.get("option_type") or "").strip().upper()
    expiration = canonical_expiration_yyyymmdd(raw_position.get("expiration") or symbol_parts.get("expiration"))
    quantity = _int_quantity(raw_position.get("quantity") or raw_position.get("qty"))
    if not ticker or strike <= 0 or option_type not in {"CALL", "PUT"} or not expiration or quantity <= 0:
        return None
    broker = _position_broker(raw_position) or active_broker
    entry_price = _positive_float(raw_position.get("avg_entry_price") or raw_position.get("avg_entry"))
    current_price = _positive_float(raw_position.get("current_price") or raw_position.get("market_price")) or entry_price
    position_id = contract_position_id(broker, ticker, strike, option_type, expiration)
    position = {
        "id": position_id,
        "ticker": ticker,
        "strike": strike,
        "option_type": option_type,
        "expiration": expiration,
        "entry_price": entry_price,
        "current_price": current_price,
        "highest_price": max(entry_price, current_price),
        "highest_executable_bid": entry_price,
        "original_quantity": quantity,
        "remaining_quantity": quantity,
        "total_cost": round(entry_price * quantity * 100, 2),
        "broker": broker,
        "status": "open",
        "opened_at": _now(),
        "realized_pnl": 0.0,
        "unrealized_pnl": round((current_price - entry_price) * quantity * 100, 2),
        "trade_ids": [],
        "reconciled_from_broker_only": True,
        "entry_risk_profile": "normal",
    }
    position.update(fresh_position_lifecycle_state(entry_price))
    position["reconciled_from_broker_only"] = True
    return position


def _exit_worker_enabled(settings: dict[str, Any]) -> bool:
    if "bot_managed_exit_worker_enabled" in settings:
        return coerce_bool(settings.get("bot_managed_exit_worker_enabled"), default=True)
    return (
        coerce_bool(settings.get("coordinated_exit_enabled"), default=False)
        or
        coerce_bool(settings.get("reversal_exit_enabled"), default=True)
        or coerce_bool(settings.get("zero_dte_liquidation_enabled"), default=True)
        or any(
            coerce_bool(settings.get(key), default=False)
            for key in (
                "take_profit_enabled",
                "stop_loss_enabled",
                "trailing_stop_enabled",
                "break_even_enabled",
            )
        )
    )


def _is_expired(expiration: Any, *, today: date | None = None) -> bool:
    canonical = canonical_expiration_yyyymmdd(expiration)
    try:
        return date.fromisoformat(canonical) < (today or date.today())
    except ValueError:
        return False


def _active_broker(settings: dict[str, Any]) -> str:
    broker = str(settings.get("active_broker") or "").strip().lower()
    return broker


def _position_broker(position: dict[str, Any]) -> str:
    return str(position.get("broker") or "").strip().lower()


def _broker_position_list_failed(broker_client) -> bool:
    return bool(str(getattr(broker_client, "last_positions_error", "") or "").strip())


def _is_option_position(position: dict[str, Any]) -> bool:
    option_type = str(position.get("option_type") or "").strip().upper()
    return (
        bool(str(position.get("ticker") or "").strip())
        and _positive_float(position.get("strike")) > 0
        and option_type in {"CALL", "PUT"}
        and bool(canonical_expiration_yyyymmdd(position.get("expiration")))
    )


def _has_broker_position_evidence(position: dict[str, Any]) -> bool:
    return bool(
        position.get("reconciled_from_broker_only")
        or position.get("broker_mark_refreshed_at")
        or position.get("broker_position_refreshed_at")
    )


def _remaining_quantity(position: dict[str, Any]) -> int:
    return _int_quantity(position.get("remaining_quantity") or position.get("quantity"))


def _exit_quantity_for_decision(
    position: dict[str, Any],
    settings: dict[str, Any],
    decision: dict[str, Any],
) -> int:
    remaining = _remaining_quantity(position)
    if remaining <= 0:
        return 0
    explicit_quantity = _int_quantity(decision.get("quantity"))
    if explicit_quantity > 0:
        return min(remaining, explicit_quantity)
    decision_pct = _positive_float(decision.get("sell_percentage"))
    if decision_pct > 0:
        pct = min(100.0, max(1.0, decision_pct))
        return min(remaining, max(1, int(remaining * pct / 100.0)))
    if str(decision.get("exit_trigger") or "") != "take_profit":
        return remaining
    pct = _positive_float(settings.get("take_profit_sell_percentage"))
    if pct <= 0:
        pct = 100.0
    pct = min(100.0, max(1.0, pct))
    return min(remaining, max(1, int(remaining * pct / 100.0)))


async def _release_exit_reservation(db, position: dict[str, Any], position_id: str) -> None:
    updates = {
        "exit_order_pending": False,
        "exit_order_id": None,
        "exit_reservation_token": None,
    }
    await db.update_position(position_id, {"$set": updates})
    position.update(updates)


def _int_quantity(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(int(float(value or 0)), 0)
    except (TypeError, ValueError):
        return 0


def _positive_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        return max(float(value or 0.0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _non_negative_float(value: Any, *, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return max(0.0, float(default))
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return max(0.0, float(default))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _eastern_now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(EASTERN)
    if current.tzinfo is None:
        return current.replace(tzinfo=EASTERN)
    return current.astimezone(EASTERN)


def _cutoff_time(value: Any) -> time:
    try:
        return time.fromisoformat(str(value or "15:40").strip())
    except ValueError:
        return time(15, 40)
