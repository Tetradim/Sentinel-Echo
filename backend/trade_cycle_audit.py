from __future__ import annotations

from typing import Any


def build_trade_cycle_audit(
    positions: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    alert_by_id = {str(item.get("id") or ""): item for item in alerts}
    cycles = [
        _build_cycle(position, trades, alert_by_id, events)
        for position in positions
        if str(position.get("id") or "").strip()
    ]
    cycles.sort(key=lambda item: str(item.get("opened_at") or ""), reverse=True)

    closed = [cycle for cycle in cycles if cycle["status"] == "closed"]
    wins = [cycle for cycle in closed if cycle["realized_pnl"] > 0]
    losses = [cycle for cycle in closed if cycle["realized_pnl"] < 0]
    gross_profit = round(sum(item["realized_pnl"] for item in wins), 2)
    gross_loss = round(sum(item["realized_pnl"] for item in losses), 2)
    return {
        "summary": {
            "cycles": len(cycles),
            "open_cycles": len(cycles) - len(closed),
            "closed_cycles": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round((len(wins) / len(closed) * 100.0) if closed else 0.0, 2),
            "net_pnl": round(sum(item["realized_pnl"] for item in cycles), 2),
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "profit_factor": round(gross_profit / abs(gross_loss), 3) if gross_loss < 0 else None,
            "reentries": sum(1 for item in cycles if item.get("reentry_of_position_id")),
            "decision_evidence_coverage": round(
                sum(1 for item in cycles if item["data_quality"]["has_decision_evidence"])
                / len(cycles)
                * 100.0,
                1,
            ) if cycles else 0.0,
        },
        "cycles": cycles,
    }


def _build_cycle(
    position: dict[str, Any],
    trades: list[dict[str, Any]],
    alert_by_id: dict[str, dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    position_id = str(position.get("id") or "")
    trade_ids = {str(value) for value in (position.get("trade_ids") or [])}
    cycle_trades = [
        trade for trade in trades
        if str(trade.get("position_id") or "") == position_id
        or str(trade.get("id") or "") in trade_ids
    ]
    cycle_events = [
        event for event in events
        if _event_matches_cycle(event, position_id, trade_ids)
    ]
    alert = alert_by_id.get(str(position.get("alert_id") or ""), {})
    sell_fills = [
        trade for trade in cycle_trades
        if str(trade.get("side") or "").upper() == "SELL"
        and str(trade.get("status") or "").lower() in {"executed", "filled", "partial"}
    ]
    exit_quantity = sum(_number(item.get("quantity")) for item in sell_fills)
    weighted_exit = (
        sum(_number(item.get("exit_price")) * _number(item.get("quantity")) for item in sell_fills)
        / exit_quantity
        if exit_quantity > 0 else 0.0
    )
    decision_evidence = [
        dict(item.get("exit_decision_audit") or {})
        for item in cycle_trades
        if isinstance(item.get("exit_decision_audit"), dict) and item.get("exit_decision_audit")
    ]
    timeline = []
    if alert:
        timeline.append({
            "kind": "alert",
            "timestamp": alert.get("timestamp"),
            "label": "Discord alert received",
            "details": {
                "source": alert.get("source_name") or alert.get("source_label"),
                "channel": alert.get("channel_name"),
                "author": alert.get("author_name"),
                "raw_message": alert.get("raw_message"),
            },
        })
    for trade in cycle_trades:
        side = str(trade.get("side") or "").upper()
        timeline.append({
            "kind": "fill" if trade.get("executed_at") else "order",
            "timestamp": trade.get("executed_at") or trade.get("created_at"),
            "label": f"{side or 'Order'} {trade.get('status') or ''}".strip(),
            "details": {
                "trade_id": trade.get("id"),
                "order_id": trade.get("order_id"),
                "quantity": trade.get("quantity"),
                "price": trade.get("exit_price") if side == "SELL" else trade.get("entry_price"),
                "exit_trigger": trade.get("exit_trigger"),
                "decision": trade.get("exit_decision_audit"),
            },
        })
    for event in cycle_events:
        timeline.append({
            "kind": "decision",
            "timestamp": event.get("timestamp") or event.get("created_at"),
            "label": event.get("summary") or event.get("action") or "Decision event",
            "details": event.get("details") or {},
        })
    timeline.sort(key=lambda item: str(item.get("timestamp") or ""))

    realized_pnl = round(_number(position.get("realized_pnl")), 2)
    return {
        "id": position_id,
        "trade_cycle_id": position.get("trade_cycle_id") or position_id,
        "contract_key": position.get("contract_key"),
        "reentry_of_position_id": position.get("reentry_of_position_id"),
        "ticker": position.get("ticker"),
        "strike": position.get("strike"),
        "option_type": position.get("option_type"),
        "expiration": position.get("expiration"),
        "broker": position.get("broker"),
        "status": str(position.get("status") or "unknown").lower(),
        "opened_at": position.get("opened_at"),
        "closed_at": position.get("closed_at"),
        "entry_price": round(_number(position.get("entry_price")), 4),
        "original_quantity": int(_number(position.get("original_quantity"))),
        "remaining_quantity": int(_number(position.get("remaining_quantity"))),
        "weighted_exit_price": round(weighted_exit, 4) if weighted_exit > 0 else None,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": round(_number(position.get("unrealized_pnl")), 2),
        "return_percent": round(
            realized_pnl / max(1.0, _number(position.get("total_cost"))) * 100.0,
            2,
        ),
        "max_favorable_excursion_percent": _optional_number(position.get("max_favorable_excursion_percent")),
        "max_adverse_excursion_percent": _optional_number(position.get("max_adverse_excursion_percent")),
        "post_exit_highest_return_percent": _optional_number(position.get("post_exit_highest_return_percent")),
        "exit_triggers": sorted({
            str(item.get("exit_trigger")) for item in sell_fills if item.get("exit_trigger")
        }),
        "source": {
            "name": alert.get("source_name") or alert.get("source_label"),
            "channel": alert.get("channel_name"),
            "author": alert.get("author_name"),
            "raw_message": alert.get("raw_message"),
        },
        "strategy_snapshot": position.get("entry_strategy_snapshot") or {},
        "decision_evidence": decision_evidence,
        "orders": cycle_trades,
        "timeline": timeline,
        "data_quality": {
            "has_source_alert": bool(alert),
            "has_entry_fill": any(str(item.get("side") or "").upper() == "BUY" for item in cycle_trades),
            "has_decision_evidence": bool(decision_evidence),
            "broker_quantity": position.get("broker_quantity"),
            "local_quantity": position.get("remaining_quantity"),
            "quantity_mismatch": (
                position.get("broker_quantity") is not None
                and int(_number(position.get("broker_quantity")))
                != int(_number(position.get("remaining_quantity")))
            ),
        },
    }


def _event_matches_cycle(event: dict[str, Any], position_id: str, trade_ids: set[str]) -> bool:
    details = event.get("details") if isinstance(event.get("details"), dict) else {}
    return (
        str(details.get("position_id") or "") == position_id
        or str(details.get("trade_id") or "") in trade_ids
    )


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    return round(_number(value), 3)
