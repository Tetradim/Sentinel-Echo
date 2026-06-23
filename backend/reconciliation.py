"""Build operator reconciliation rows from alerts, trades, and positions."""
from __future__ import annotations

from typing import Any, Dict, List

from bridge_contract import CHROME_BRIDGE_CONTRACT_VERSION
from settings_flags import coerce_bool


def _first_trade_for_alert(trades: list[dict], alert_id: str) -> dict | None:
    return next((trade for trade in trades if trade.get("alert_id") == alert_id), None)


def _position_trade_ids(position: dict[str, Any]) -> list[str]:
    trade_ids = position.get("trade_ids")
    if isinstance(trade_ids, list):
        values = [_clean_text(trade_id) for trade_id in trade_ids]
    else:
        values = [_clean_text(trade_ids)]
    legacy_trade_id = _clean_text(position.get("trade_id"))
    if legacy_trade_id:
        values.append(legacy_trade_id)
    return [trade_id for trade_id in values if trade_id]


def _first_position_for_trade(positions: list[dict], trade_id: str | None) -> dict | None:
    if not trade_id:
        return None
    return next((position for position in positions if trade_id in _position_trade_ids(position)), None)


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


def _first_value(*values: Any, default: Any = "") -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return default


def _chain_status(*, skipped: bool, attention_reason: str, deterministic_reason: str) -> tuple[str, bool]:
    if skipped:
        return "blocked", bool(deterministic_reason)
    if attention_reason:
        return "attention", False
    return "reconciled", True


def _has_parser_confidence_proof(parser: dict[str, Any]) -> bool:
    return _clean_text(parser.get("confidence")).lower() in {"low", "medium", "high"}


def _has_chrome_bridge_contract_proof(details: dict[str, Any]) -> bool:
    return _clean_text(details.get("contract_version")) == CHROME_BRIDGE_CONTRACT_VERSION


def _has_source_identity_proof(channel: dict[str, Any], author: dict[str, Any]) -> bool:
    return bool(
        _clean_text(channel.get("url"))
        and (_clean_text(author.get("id")) or _clean_text(author.get("name")))
    )


def _has_source_metadata_policy_proof(source: dict[str, Any]) -> bool:
    return all(
        coerce_bool(source.get(key), default=False)
        for key in (
            "parser_confidence_allowed",
            "channel_url_allowed",
            "author_id_allowed",
            "metadata_policy_passed",
        )
    )


def _has_alert_capture_proof(details: dict[str, Any]) -> bool:
    return bool(_clean_text(details.get("raw_text")) and _clean_text(details.get("capture_path")))


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
    # Entry and exit rows can be interleaved. Read a wider trade window so a page
    # of recent alerts still links to its entry trades after simulated exits.
    trades = await db.get_trades(max(limit * 4, 100))
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
                "strike": _first_value(
                    alert.get("strike"),
                    (trade or {}).get("strike"),
                    (position or {}).get("strike"),
                    default=None,
                ),
                "option_type": _first_value(
                    alert.get("option_type"),
                    (trade or {}).get("option_type"),
                    (position or {}).get("option_type"),
                ),
                "expiration": _first_value(
                    alert.get("expiration"),
                    (trade or {}).get("expiration"),
                    (position or {}).get("expiration"),
                ),
                "entry_price": _first_value(
                    alert.get("entry_price"),
                    (trade or {}).get("entry_price"),
                    (position or {}).get("entry_price"),
                    default=None,
                ),
                "sell_percentage": _first_value(
                    alert.get("sell_percentage"),
                    (trade or {}).get("sell_percentage"),
                    default=None,
                ),
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
        channel = _as_dict(details.get("channel"))
        author = _as_dict(details.get("author"))
        parser = _as_dict(details.get("parser"))
        source = _as_dict(details.get("source"))
        event_id = _clean_text(details.get("event_id") or event.get("id"))
        alert_id = _clean_text(decision.get("alert_id"))
        if alert_id:
            bridge_alert_ids.add(alert_id)
        reconciliation = reconciliation_by_alert.get(alert_id, {})
        skipped = _clean_text(decision.get("status")).lower() == "skipped"
        trade_requested = coerce_bool(decision.get("trade_requested"), default=False)
        source_override_matched = coerce_bool(source.get("override_matched"), default=False)
        decision_reason = _clean_text(decision.get("skip_reason")) or _clean_text(
            decision.get("trade_request_reason")
        )
        attention_reason = ""
        if not skipped:
            if not alert_id:
                attention_reason = "accepted bridge alert missing alert id"
            elif not reconciliation:
                attention_reason = "accepted bridge alert missing reconciliation row"
            elif not _has_chrome_bridge_contract_proof(details):
                attention_reason = "accepted bridge alert missing chrome bridge contract proof"
            elif not source_override_matched:
                attention_reason = "accepted bridge alert missing source policy proof"
            elif not _has_parser_confidence_proof(parser):
                attention_reason = "accepted bridge alert missing parser confidence proof"
            elif not _has_source_identity_proof(channel, author):
                attention_reason = "accepted bridge alert missing source identity proof"
            elif not _has_source_metadata_policy_proof(source):
                attention_reason = "accepted bridge alert missing source metadata policy proof"
            elif not _has_alert_capture_proof(details):
                attention_reason = "accepted bridge alert missing alert capture proof"
            elif trade_requested and not _clean_text(reconciliation.get("trade_id")):
                attention_reason = "trade requested but no linked trade"
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
                "contract_version": _clean_text(details.get("contract_version")),
                "event_id": event_id,
                "observed_at": _clean_text(event.get("timestamp")),
                "raw_text": _clean_text(details.get("raw_text")),
                "capture_path": _clean_text(details.get("capture_path")),
                "channel_id": _clean_text(channel.get("id")),
                "channel_url": _clean_text(channel.get("url")),
                "author_id": _clean_text(author.get("id")),
                "author_name": _clean_text(author.get("name")),
                "source_key": _clean_text(source.get("key")),
                "source_override_matched": source_override_matched,
                "source_metadata_policy_passed": coerce_bool(
                    source.get("metadata_policy_passed"),
                    default=False,
                ),
                "channel_url_allowed": coerce_bool(source.get("channel_url_allowed"), default=False),
                "author_id_allowed": coerce_bool(source.get("author_id_allowed"), default=False),
                "parser_confidence_allowed": coerce_bool(
                    source.get("parser_confidence_allowed"),
                    default=False,
                ),
                "parser_confidence": _clean_text(parser.get("confidence")),
                "min_parser_confidence": _clean_text(source.get("min_parser_confidence")),
                "alert_id": alert_id,
                "ticker": _clean_text(parsed.get("ticker") or reconciliation.get("ticker")),
                "alert_type": _clean_text(
                    _first_value(parsed.get("alert_type"), reconciliation.get("alert_type"))
                ),
                "strike": _first_value(parsed.get("strike"), reconciliation.get("strike"), default=None),
                "option_type": _clean_text(
                    _first_value(parsed.get("option_type"), reconciliation.get("option_type"))
                ),
                "expiration": _clean_text(
                    _first_value(parsed.get("expiration"), reconciliation.get("expiration"))
                ),
                "entry_price": _first_value(
                    parsed.get("entry_price"),
                    reconciliation.get("entry_price"),
                    default=None,
                ),
                "sell_percentage": _first_value(
                    parsed.get("sell_percentage"),
                    reconciliation.get("sell_percentage"),
                    default=None,
                ),
                "seen": True,
                "parsed": bool(parsed),
                "accepted": not skipped,
                "alert_inserted": coerce_bool(decision.get("alert_inserted"), default=False),
                "trade_requested": trade_requested,
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
                "alert_type": _clean_text(reconciliation.get("alert_type")),
                "strike": _first_value(reconciliation.get("strike"), default=None),
                "option_type": _clean_text(reconciliation.get("option_type")),
                "expiration": _clean_text(reconciliation.get("expiration")),
                "entry_price": _first_value(reconciliation.get("entry_price"), default=None),
                "sell_percentage": _first_value(
                    reconciliation.get("sell_percentage"),
                    default=None,
                ),
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
        "attention_reasons": sorted(
            {
                row["attention_reason"]
                for row in rows
                if row["status"] == "attention" and row["attention_reason"]
            }
        ),
        "deterministic_count": sum(1 for row in rows if row["deterministic"]),
    }
    summary["deterministic"] = summary["total"] > 0 and summary["deterministic_count"] == summary["total"]
    return {"summary": summary, "rows": rows}
