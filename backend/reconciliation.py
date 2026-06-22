"""Build operator reconciliation rows from alerts, trades, and positions."""
from __future__ import annotations

from typing import Any, Dict, List


def _first_trade_for_alert(trades: list[dict], alert_id: str) -> dict | None:
    return next((trade for trade in trades if trade.get("alert_id") == alert_id), None)


def _first_position_for_trade(positions: list[dict], trade_id: str | None) -> dict | None:
    if not trade_id:
        return None
    return next((position for position in positions if trade_id in (position.get("trade_ids") or [])), None)


def _attention_reason(alert: dict, trade: dict | None, position: dict | None) -> str:
    if alert.get("processed") and not trade:
        return "processed alert has no trade"
    if trade and str(trade.get("status", "")).lower() in {"pending", "submitted", "unconfirmed"}:
        return "order pending fill"
    if trade and str(trade.get("side", "BUY")).upper() == "BUY" and not position:
        return "entry trade has no position"
    return ""


def summarize_reconciliation_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize unresolved alert/trade/position chains for readiness checks."""
    unresolved_reasons: list[str] = []
    unresolved_count = 0
    simulated_unresolved_count = 0
    for row in rows:
        reason = str(row.get("attention_reason") or "").strip()
        if not reason:
            continue
        if bool(row.get("simulated", False)):
            simulated_unresolved_count += 1
            continue
        unresolved_count += 1
        if reason not in unresolved_reasons:
            unresolved_reasons.append(reason)

    return {
        "row_count": len(rows),
        "unresolved_count": unresolved_count,
        "simulated_unresolved_count": simulated_unresolved_count,
        "unresolved_reasons": unresolved_reasons,
    }


async def build_reconciliation_rows(db, *, limit: int = 100) -> List[Dict[str, Any]]:
    """Return alert/trade/position chain summaries for operator review."""
    alerts = await db.get_alerts(limit)
    trades = await db.get_trades(limit)
    positions = await db.get_positions()
    rows: List[Dict[str, Any]] = []
    for alert in alerts:
        trade = _first_trade_for_alert(trades, alert.get("id", ""))
        position = _first_position_for_trade(positions, trade.get("id") if trade else None)
        rows.append(
            {
                "alert_id": alert.get("id", ""),
                "ticker": alert.get("ticker", trade.get("ticker") if trade else ""),
                "alert_type": alert.get("alert_type") or alert.get("action") or "",
                "processed": bool(alert.get("processed", False)),
                "trade_executed": bool(alert.get("trade_executed", False)),
                "trade_id": trade.get("id") if trade else "",
                "trade_status": trade.get("status") if trade else "",
                "order_id": trade.get("order_id") if trade else "",
                "position_id": position.get("id") if position else "",
                "position_status": position.get("status") if position else "",
                "simulated": bool(
                    (trade or {}).get("simulated", alert.get("simulated", True))
                ),
                "attention_reason": _attention_reason(alert, trade, position),
            }
        )
    return rows
