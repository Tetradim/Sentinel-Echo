"""Persistent live option-position risk supervisor.

The fill monitor owns working broker orders. This supervisor owns open positions:
it refreshes executable option marks and submits durable exits for configured
profit, stop-loss and trailing-stop conditions.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import logging
import os
from typing import Any

from fill_monitor import monitor_fill
from fill_reconciliation import OrderContext
from live_order_journal import journal
from order_execution import get_configured_broker_client


logger = logging.getLogger(__name__)
_SUPERVISOR_TASK: asyncio.Task | None = None
_SUPPORTED_BROKERS = {"alpaca", "tradier"}


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _integer(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _active_exit(position_id: str) -> bool:
    return any(
        str(record.get("position_id") or "") == str(position_id)
        and str(record.get("side") or "").upper() == "SELL"
        for record in journal.records(active_only=True)
    )


def _filled_exit_waiting_for_position(position_id: str) -> bool:
    return any(
        str(record.get("position_id") or "") == str(position_id)
        and str(record.get("side") or "").upper() == "SELL"
        and str(record.get("status") or "").lower() == "filled"
        for record in journal.records()
    )


def _exit_reason(position: dict, settings: dict, mark: float, highest: float) -> str | None:
    entry = _num(position.get("entry_price"))
    if entry <= 0 or mark <= 0:
        return None
    pnl_pct = (mark - entry) / entry * 100.0

    if settings.get("stop_loss_enabled") and pnl_pct <= -abs(
        _num(settings.get("stop_loss_percentage")) or 25.0
    ):
        return "stop_loss"

    if settings.get("trailing_stop_enabled") and highest > 0:
        trailing_type = str(settings.get("trailing_stop_type") or "percent").lower()
        if trailing_type == "premium":
            distance = (_num(settings.get("trailing_stop_cents")) or 50.0) / 100.0
            if mark <= highest - distance:
                return "trailing_stop"
        else:
            percent = abs(_num(settings.get("trailing_stop_percent")) or 10.0)
            if mark <= highest * (1.0 - percent / 100.0):
                return "trailing_stop"

    if settings.get("take_profit_enabled") and pnl_pct >= abs(
        _num(settings.get("take_profit_percentage")) or 50.0
    ):
        return "take_profit"
    return None


def _client_id(position_id: str, reason: str, attempt: int) -> str:
    digest = hashlib.sha256(str(position_id).encode("utf-8")).hexdigest()[:20]
    return f"echo-risk-{reason}-{digest}-{attempt}"


async def _submit_exit(db, settings: dict, position: dict, reason: str, quote: dict) -> bool:
    position_id = str(position.get("id") or "")
    quantity = _integer(position.get("remaining_quantity"))
    if not position_id or quantity <= 0:
        return False

    broker = str(position.get("broker") or "").lower()
    if broker not in _SUPPORTED_BROKERS:
        logger.critical(
            "Cannot supervise live position %s: broker %s lacks complete live option lifecycle",
            position_id,
            broker,
        )
        return False

    attempt = _integer(position.get("risk_exit_attempts")) + 1
    client_id = _client_id(position_id, reason, attempt)
    trade_id = f"risk-{hashlib.sha256(client_id.encode('utf-8')).hexdigest()[:24]}"
    mark = round(_num(quote.get("mid")) or _num(quote.get("bid")), 2)
    trade = {
        "id": trade_id,
        "alert_id": None,
        "ticker": str(position.get("ticker") or "").upper(),
        "strike": _num(position.get("strike")),
        "option_type": str(position.get("option_type") or "").upper(),
        "expiration": str(position.get("expiration") or ""),
        "entry_price": _num(position.get("entry_price")),
        "exit_price": mark,
        "quantity": quantity,
        "side": "SELL",
        "status": "submitting",
        "broker": broker,
        "client_order_id": client_id,
        "simulated": False,
        "realized_pnl": 0.0,
        "created_at": _now(),
        "risk_exit_reason": reason,
        "position_id": position_id,
        "execution_quote": quote,
    }
    await db.insert_trade(trade)
    await db.update_position(
        position_id,
        {
            "$set": {
                "risk_exit_attempts": attempt,
                "risk_exit_reason": reason,
                "risk_exit_trade_id": trade_id,
                "risk_exit_requested_at": _now(),
            }
        },
    )

    client = get_configured_broker_client(
        settings,
        broker,
        require_order_status=True,
    )
    try:
        result = await client.place_order(
            ticker=trade["ticker"],
            strike=trade["strike"],
            option_type=trade["option_type"],
            expiration=trade["expiration"],
            side="SELL",
            quantity=quantity,
            price=mark,
            client_order_id=client_id,
        )
        order_id = str((result or {}).get("order_id") or "")
        if not order_id:
            await db.update_trade(
                trade_id,
                {
                    "status": "failed",
                    "error_message": str((result or {}).get("error") or "Broker did not return order id"),
                },
            )
            await client.close()
            return False

        routed_broker = str(getattr(client, "routed_broker_id", broker) or broker)
        context = OrderContext(
            trade_id=trade_id,
            order_id=order_id,
            side="SELL",
            ticker=trade["ticker"],
            strike=trade["strike"],
            option_type=trade["option_type"],
            expiration=trade["expiration"],
            requested_quantity=quantity,
            broker=routed_broker,
            position_id=position_id,
            alert_price=mark,
            simulated=False,
        )
        await db.update_trade(
            trade_id,
            {
                "status": "pending",
                "order_id": order_id,
                "broker": routed_broker,
                "requested_quantity": quantity,
                "reconciliation_context": context.to_dict(),
                "monitor_state": "scheduled",
                "submitted_limit_price": (result or {}).get("submitted_limit_price", mark),
                "execution_quote": (result or {}).get("execution_quote", quote),
            },
        )
        asyncio.create_task(
            monitor_fill(
                order_context=context,
                broker_client=client,
                db=db,
                settings=settings,
            ),
            name=f"risk-exit:{routed_broker}:{order_id}",
        )
        logger.critical(
            "Submitted autonomous %s exit for %s quantity=%s order=%s",
            reason,
            position_id,
            quantity,
            order_id,
        )
        return True
    except Exception as exc:
        await db.update_trade(
            trade_id,
            {"status": "failed", "error_message": str(exc)},
        )
        try:
            await client.close()
        except Exception:
            pass
        logger.exception("Autonomous exit failed for %s: %s", position_id, exc)
        return False


async def supervise_once(db) -> dict:
    settings = await db.get_settings()
    positions = await db.get_positions("open")
    positions += await db.get_positions("partial")
    checked = 0
    submitted = 0

    for position in positions:
        if position.get("simulated"):
            continue
        position_id = str(position.get("id") or "")
        remaining = _integer(position.get("remaining_quantity"))
        if not position_id or remaining <= 0:
            continue
        if _active_exit(position_id) or _filled_exit_waiting_for_position(position_id):
            continue
        broker = str(position.get("broker") or "").lower()
        if broker not in _SUPPORTED_BROKERS:
            continue

        client = get_configured_broker_client(
            settings,
            broker,
            require_order_status=True,
        )
        client.routed_broker_id = broker
        try:
            quote = await client.get_option_quote(
                position.get("ticker"),
                position.get("strike"),
                position.get("option_type"),
                position.get("expiration"),
            )
        except Exception as exc:
            logger.warning("Could not quote live option position %s: %s", position_id, exc)
            await client.close()
            continue
        await client.close()

        checked += 1
        mark = _num(quote.get("mid"))
        entry = _num(position.get("entry_price"))
        highest = max(_num(position.get("highest_price")), mark)
        unrealized = (mark - entry) * remaining * 100.0
        await db.update_position(
            position_id,
            {
                "$set": {
                    "current_price": mark,
                    "highest_price": highest,
                    "unrealized_pnl": unrealized,
                    "last_quote": quote,
                    "last_quote_at": _now(),
                }
            },
        )
        reason = _exit_reason(position, settings, mark, highest)
        if reason and await _submit_exit(db, settings, {**position, "highest_price": highest}, reason, quote):
            submitted += 1

    return {"checked": checked, "submitted": submitted}


async def _supervisor_loop(db) -> None:
    interval = max(1.0, _num(os.getenv("ECHO_POSITION_SUPERVISOR_INTERVAL_SECONDS", 5.0)))
    while True:
        try:
            await supervise_once(db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Option position supervisor cycle failed: %s", exc)
        await asyncio.sleep(interval)


def start_position_supervisor(db) -> asyncio.Task:
    global _SUPERVISOR_TASK
    if _SUPERVISOR_TASK is None or _SUPERVISOR_TASK.done():
        _SUPERVISOR_TASK = asyncio.create_task(
            _supervisor_loop(db),
            name="echo-option-position-supervisor",
        )
    return _SUPERVISOR_TASK


async def stop_position_supervisor() -> None:
    global _SUPERVISOR_TASK
    if _SUPERVISOR_TASK is None:
        return
    _SUPERVISOR_TASK.cancel()
    await asyncio.gather(_SUPERVISOR_TASK, return_exceptions=True)
    _SUPERVISOR_TASK = None
