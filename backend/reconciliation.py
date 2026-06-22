"""Build operator reconciliation rows from alerts, trades, and positions."""
from __future__ import annotations

from typing import Any, Dict, List

from settings_flags import coerce_bool


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


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _chain_status(*, skipped: bool, attention_reason: str, deterministic_reason: str) -> tuple[str, bool]:
    if skipped:
        return "blocked", bool(deterministic_reason)
    if attention_reason:
        return "attention", False
    return "reconciled", True


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


async def build_alert_chain_report(db, *, limit: int = 100) -> Dict[str, Any]:
    """Return deterministic see/parse/decide/place/reconcile rows for operator review."""
    reconciliation_rows = await build_reconciliation_rows(db, limit=limit)
    reconciliation_by_alert = {
        _clean_text(row.get("alert_id")): row
        for row in reconciliation_rows
        if _clean_text(row.get("alert_id"))
    }
    events = await db.get_operator_events(limit) if hasattr(db, "get_operator_events") else []
    rows: List[Dict[str, Any]] = []
    bridge_alert_ids: set[str] = set()

    for event in events:
        if event.get("action") != "bridge_alert_decision":
            continue
        details = _as_dict(event.get("details"))
        decision = _as_dict(details.get("decision"))
        parsed = _as_dict(details.get("parsed"))
        event_id = _clean_text(details.get("event_id") or event.get("id"))
        alert_id = _clean_text(decision.get("alert_id"))
        if alert_id:
            bridge_alert_ids.add(alert_id)
        reconciliation = reconciliation_by_alert.get(alert_id, {})
        skipped = _clean_text(decision.get("status")).lower() == "skipped"
        decision_reason = _clean_text(decision.get("skip_reason")) or _clean_text(
            decision.get("trade_request_reason")
        )
        attention_reason = ""
        if not skipped:
            if not alert_id:
                attention_reason = "accepted bridge alert missing alert id"
            elif not reconciliation:
                attention_reason = "accepted bridge alert missing reconciliation row"
            else:
                attention_reason = _clean_text(reconciliation.get("attention_reason"))
        status, deterministic = _chain_status(
            skipped=skipped,
            attention_reason=attention_reason,
            deterministic_reason=decision_reason,
        )
        rows.append(
            {
                "chain_key": f"bridge:{event_id}",
                "source": "chrome_bridge",
                "event_id": event_id,
                "observed_at": _clean_text(event.get("timestamp")),
                "alert_id": alert_id,
                "ticker": _clean_text(parsed.get("ticker") or reconciliation.get("ticker")),
                "seen": True,
                "parsed": bool(parsed),
                "accepted": not skipped,
                "alert_inserted": coerce_bool(decision.get("alert_inserted"), default=False),
                "trade_requested": coerce_bool(decision.get("trade_requested"), default=False),
                "decision_reason": decision_reason,
                "trade_id": _clean_text(reconciliation.get("trade_id")),
                "order_id": _clean_text(reconciliation.get("order_id")),
                "position_id": _clean_text(reconciliation.get("position_id")),
                "status": status,
                "attention_reason": attention_reason,
                "deterministic": deterministic,
            }
        )

    for reconciliation in reconciliation_rows:
        alert_id = _clean_text(reconciliation.get("alert_id"))
        if alert_id in bridge_alert_ids:
            continue
        attention_reason = _clean_text(reconciliation.get("attention_reason"))
        status, deterministic = _chain_status(
            skipped=False,
            attention_reason=attention_reason,
            deterministic_reason="stored alert",
        )
        rows.append(
            {
                "chain_key": f"alert:{alert_id}",
                "source": "stored_alert",
                "event_id": "",
                "observed_at": "",
                "alert_id": alert_id,
                "ticker": _clean_text(reconciliation.get("ticker")),
                "seen": True,
                "parsed": bool(_clean_text(reconciliation.get("ticker"))),
                "accepted": True,
                "alert_inserted": True,
                "trade_requested": coerce_bool(reconciliation.get("trade_executed"), default=False),
                "decision_reason": attention_reason,
                "trade_id": _clean_text(reconciliation.get("trade_id")),
                "order_id": _clean_text(reconciliation.get("order_id")),
                "position_id": _clean_text(reconciliation.get("position_id")),
                "status": status,
                "attention_reason": attention_reason,
                "deterministic": deterministic,
            }
        )

    summary = {
        "total": len(rows),
        "seen_count": sum(1 for row in rows if row["seen"]),
        "parsed_count": sum(1 for row in rows if row["parsed"]),
        "accepted_count": sum(1 for row in rows if row["accepted"]),
        "skipped_count": sum(1 for row in rows if not row["accepted"]),
        "blocked_count": sum(1 for row in rows if row["status"] == "blocked"),
        "alert_inserted_count": sum(1 for row in rows if row["alert_inserted"]),
        "trade_requested_count": sum(1 for row in rows if row["trade_requested"]),
        "trade_linked_count": sum(1 for row in rows if row["trade_id"]),
        "position_linked_count": sum(1 for row in rows if row["position_id"]),
        "attention_count": sum(1 for row in rows if row["status"] == "attention"),
        "deterministic_count": sum(1 for row in rows if row["deterministic"]),
    }
    summary["deterministic"] = summary["total"] > 0 and summary["deterministic_count"] == summary["total"]
    return {"summary": summary, "rows": rows}
