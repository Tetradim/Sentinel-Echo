from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from models import Alert, Position, Trade


def build_entry_shadow_records(
    *,
    alert: Alert,
    quantity: int,
    broker: str,
) -> tuple[Trade, Position]:
    """Build simulated entry records for comparing live orders against paper fills."""
    shadow_broker = f"{broker}:paper_shadow"
    trade = Trade(
        alert_id=alert.id,
        ticker=alert.ticker,
        strike=alert.strike,
        option_type=alert.option_type,
        expiration=alert.expiration,
        entry_price=alert.entry_price,
        quantity=quantity,
        broker=shadow_broker,
        order_id=f"paper-shadow:{alert.id}",
        status="paper_shadow",
        simulated=True,
    )
    position = Position(
        ticker=alert.ticker,
        strike=alert.strike,
        option_type=alert.option_type,
        expiration=alert.expiration,
        entry_price=alert.entry_price,
        current_price=alert.entry_price,
        original_quantity=quantity,
        remaining_quantity=quantity,
        total_cost=alert.entry_price * quantity * 100,
        broker=shadow_broker,
        status="open",
        simulated=True,
        trade_ids=[trade.id],
        highest_price=alert.entry_price,
    )
    return trade, position


def is_paper_shadow_position(position: dict[str, Any]) -> bool:
    """Return whether a persisted position belongs to the paper-shadow ledger."""
    broker = str(position.get("broker") or "").lower()
    return bool(position.get("simulated")) and broker.endswith(":paper_shadow")


def build_exit_shadow_records(
    *,
    alert: Alert,
    position: Position,
    quantity: int,
    exit_price: float,
    now: datetime | None = None,
) -> tuple[Trade, dict[str, Any]]:
    """Build a simulated sell trade and position update for a paper-shadow exit."""
    timestamp = now or datetime.now(timezone.utc)
    realized_pnl = (exit_price - position.entry_price) * quantity * 100
    new_remaining = max(0, position.remaining_quantity - quantity)

    trade = Trade(
        alert_id=alert.id,
        ticker=position.ticker,
        strike=position.strike,
        option_type=position.option_type,
        expiration=position.expiration,
        entry_price=position.entry_price,
        exit_price=exit_price,
        quantity=quantity,
        side="SELL",
        broker=position.broker,
        order_id=f"paper-shadow:{alert.id}:{position.id}:sell",
        status="paper_shadow",
        simulated=True,
        realized_pnl=realized_pnl,
        executed_at=timestamp,
    )

    update_set: dict[str, Any] = {
        "remaining_quantity": new_remaining,
        "realized_pnl": position.realized_pnl + realized_pnl,
        "current_price": exit_price,
        "unrealized_pnl": 0.0
        if new_remaining <= 0
        else (exit_price - position.entry_price) * new_remaining * 100,
        "status": "closed" if new_remaining <= 0 else "partial",
    }
    if new_remaining <= 0:
        update_set["closed_at"] = timestamp.isoformat()

    return trade, {
        "$set": update_set,
        "$push": {"trade_ids": trade.id},
    }
