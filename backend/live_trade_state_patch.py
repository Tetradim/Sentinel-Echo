"""Keep alert/trade state aligned with broker fills rather than submission ACKs."""
from __future__ import annotations

import logging

try:
    from . import server
    from .database import get_db
    from .live_order_journal import journal
except ImportError:  # direct backend path execution
    import server
    from database import get_db
    from live_order_journal import journal


logger = logging.getLogger(__name__)
_original_process_trade = server.process_trade
_ACTIVE_ORDER_STATES = {
    "submitting",
    "ambiguous",
    "acknowledged",
    "submitted",
    "pending",
    "working",
    "partial",
    "working_unconfirmed",
}


def _alert_client_prefix(alert_id: str, side: str) -> str:
    token = server.build_client_order_id(alert_id, side)
    return token if side.upper() == "BUY" else f"{token}-"


def _journal_records_for_alert(alert_id: str, side: str) -> list[dict]:
    prefix = _alert_client_prefix(alert_id, side)
    return [
        record
        for record in journal.records()
        if (
            str(record.get("client_order_id") or "") == prefix
            if side == "BUY"
            else str(record.get("client_order_id") or "").startswith(prefix)
        )
    ]


async def _write_alert_journal_state(alert_id: str, records: list[dict]) -> None:
    if not records:
        return
    db = get_db()
    positive_fill = any(
        int(float(record.get("filled_qty") or 0)) > 0
        or str(record.get("status") or "").lower() == "filled"
        for record in records
    )
    active = any(
        str(record.get("status") or "").lower() in _ACTIVE_ORDER_STATES
        for record in records
    )
    statuses = sorted(
        {str(record.get("status") or "unknown").lower() for record in records}
    )
    await db.update_alert(
        alert_id,
        {
            "trade_executed": positive_fill,
            "order_submitted": True,
            "trade_result": (
                "filled"
                if positive_fill and not active
                else "partially_filled"
                if positive_fill
                else "submitted_waiting_for_fill"
                if active
                else "terminal_without_fill"
            ),
            "broker_order_states": statuses,
        },
    )


async def _link_journal_records(alert, parsed: dict) -> None:
    db = get_db()
    trades = await db.get_trades(5000)
    matching_trades = [
        trade for trade in trades if str(trade.get("alert_id") or "") == str(alert.id)
    ]
    side = "BUY" if parsed.get("alert_type") == "buy" else "SELL"
    records = _journal_records_for_alert(str(alert.id), side)
    # Simulation and non-executable alerts have no live journal record. Leave
    # their legacy state untouched rather than rewriting them as not executed.
    if not records:
        return

    for record in records:
        order_id = str(record.get("broker_order_id") or "")
        client_id = str(record.get("client_order_id") or "")
        candidates = [
            trade
            for trade in matching_trades
            if (
                (order_id and str(trade.get("order_id") or "") == order_id)
                or (
                    str(trade.get("ticker") or "").upper()
                    == str(record.get("ticker") or "").upper()
                    and str(trade.get("side") or "BUY").upper() == side
                    and float(trade.get("strike") or 0) == float(record.get("strike") or 0)
                    and str(trade.get("expiration") or "") == str(record.get("expiration") or "")
                )
            )
        ]
        if len(candidates) != 1:
            continue
        trade = candidates[0]
        await db.update_trade(
            str(trade.get("id")),
            {
                "client_order_id": client_id,
                "broker": record.get("broker") or trade.get("broker"),
                "broker_account_id": record.get("account_id") or "",
                "submission_journal_state": record.get("status"),
                "submission_journal_path": str(journal.path),
            },
        )

    refreshed = await db.get_trades(5000)
    matching_trades = [
        trade for trade in refreshed if str(trade.get("alert_id") or "") == str(alert.id)
    ]
    positive_fill = any(
        int(float(trade.get("applied_filled_qty") or 0)) > 0
        or (
            str(trade.get("status") or "").lower() in {"executed", "partial", "filled"}
            and int(float(trade.get("quantity") or 0)) > 0
            and str(trade.get("status") or "").lower() != "pending"
        )
        for trade in matching_trades
    )
    submitted = any(
        str(trade.get("status") or "").lower()
        in {"pending", "working", "working_unconfirmed", "partial", "executed", "filled"}
        for trade in matching_trades
    )
    await db.update_alert(
        str(alert.id),
        {
            "trade_executed": positive_fill,
            "order_submitted": submitted,
            "trade_result": (
                "filled" if positive_fill else "submitted_waiting_for_fill" if submitted else "not_executed"
            ),
        },
    )


async def process_trade_with_broker_fill_state(alert, parsed: dict):
    side = "BUY" if parsed.get("alert_type") == "buy" else "SELL"
    existing_records = _journal_records_for_alert(str(alert.id), side)
    if existing_records and not parsed.get("_force_simulation"):
        # A Discord retry or duplicate message must not create another local trade
        # or monitor for a broker order that already has a durable client ID.
        await _write_alert_journal_state(str(alert.id), existing_records)
        logger.warning(
            "Suppressed duplicate alert %s because durable broker order(s) already exist: %s",
            alert.id,
            [record.get("client_order_id") for record in existing_records],
        )
        return None

    result = await _original_process_trade(alert, parsed)
    try:
        if not parsed.get("_force_simulation"):
            await _link_journal_records(alert, parsed)
    except Exception as exc:
        logger.exception("Could not align alert %s with broker fill state: %s", alert.id, exc)
    return result


server.process_trade = process_trade_with_broker_fill_state
server.set_edge_sr_executor(process_trade_with_broker_fill_state)
