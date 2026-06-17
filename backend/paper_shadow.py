from __future__ import annotations

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
