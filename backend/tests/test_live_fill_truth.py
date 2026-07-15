import asyncio
import pathlib
import sys

import pytest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from fill_reconciliation import BrokerOrderUpdate, OrderContext
from fill_reconciliation_v2 import reconcile_order_update


class MemoryDb:
    def __init__(self):
        self.trades = {}
        self.positions = {}
        self.alerts = {}

    async def get_trades(self, limit=1000):
        return list(self.trades.values())[:limit]

    async def update_trade(self, trade_id, updates):
        self.trades.setdefault(trade_id, {"id": trade_id}).update(updates)

    async def update_alert(self, alert_id, updates):
        self.alerts.setdefault(alert_id, {}).update(updates)

    async def insert_position(self, position):
        if position["id"] in self.positions:
            raise AssertionError("position inserted twice")
        self.positions[position["id"]] = dict(position)
        return position["id"]

    async def get_position_by_id(self, position_id):
        value = self.positions.get(position_id)
        return dict(value) if value else None

    async def update_position(self, position_id, updates):
        position = self.positions[position_id]
        if "$set" in updates:
            position.update(updates["$set"])
        else:
            position.update(updates)


def entry_context(quantity=4):
    return OrderContext(
        trade_id="entry-trade",
        order_id="entry-order",
        side="BUY",
        ticker="SPY",
        strike=500.0,
        option_type="CALL",
        expiration="2026-09-18",
        requested_quantity=quantity,
        broker="alpaca",
        alert_id="entry-alert",
    )


def test_missing_fill_truth_is_rejected():
    db = MemoryDb()
    with pytest.raises(ValueError, match="positive filled_qty"):
        asyncio.run(
            reconcile_order_update(
                db,
                entry_context(),
                BrokerOrderUpdate(status="filled", filled_qty=0, avg_fill_price=1.2),
            )
        )
    with pytest.raises(ValueError, match="positive avg_fill_price"):
        asyncio.run(
            reconcile_order_update(
                db,
                entry_context(),
                BrokerOrderUpdate(status="filled", filled_qty=4, avg_fill_price=0),
            )
        )


def test_filled_state_must_equal_requested_quantity():
    db = MemoryDb()
    with pytest.raises(ValueError, match="is inconsistent"):
        asyncio.run(
            reconcile_order_update(
                db,
                entry_context(4),
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.2),
            )
        )


def test_partial_then_filled_buy_applies_only_fill_delta():
    db = MemoryDb()
    context = entry_context(4)

    partial = asyncio.run(
        reconcile_order_update(
            db,
            context,
            BrokerOrderUpdate(status="partial", filled_qty=2, avg_fill_price=1.00),
        )
    )
    final = asyncio.run(
        reconcile_order_update(
            db,
            context,
            BrokerOrderUpdate(status="filled", filled_qty=4, avg_fill_price=1.25),
        )
    )
    repeated = asyncio.run(
        reconcile_order_update(
            db,
            context,
            BrokerOrderUpdate(status="filled", filled_qty=4, avg_fill_price=1.25),
        )
    )

    position = db.positions["position:entry-trade"]
    assert partial.applied_quantity == 2
    assert final.applied_quantity == 2
    assert repeated.applied_quantity == 0
    assert position["original_quantity"] == 4
    assert position["remaining_quantity"] == 4
    assert position["entry_price"] == pytest.approx(1.25)
    assert position["total_cost"] == pytest.approx(500.0)


def test_partial_then_filled_sell_keeps_order_pnl_separate_from_position_history():
    db = MemoryDb()
    db.positions["position-1"] = {
        "id": "position-1",
        "entry_price": 1.00,
        "remaining_quantity": 4,
        "realized_pnl": 25.0,
        "trade_ids": ["entry-trade"],
        "status": "open",
    }
    context = OrderContext(
        trade_id="exit-trade",
        order_id="exit-order",
        side="SELL",
        ticker="SPY",
        strike=500.0,
        option_type="CALL",
        expiration="2026-09-18",
        requested_quantity=4,
        broker="alpaca",
        position_id="position-1",
    )

    first = asyncio.run(
        reconcile_order_update(
            db,
            context,
            BrokerOrderUpdate(status="partial", filled_qty=1, avg_fill_price=1.20),
        )
    )
    final = asyncio.run(
        reconcile_order_update(
            db,
            context,
            BrokerOrderUpdate(status="filled", filled_qty=4, avg_fill_price=1.50),
        )
    )

    assert first.applied_quantity == 1
    assert final.applied_quantity == 3
    assert db.positions["position-1"]["remaining_quantity"] == 0
    assert db.positions["position-1"]["realized_pnl"] == pytest.approx(225.0)
    assert db.trades["exit-trade"]["realized_pnl"] == pytest.approx(200.0)


def test_transient_status_does_not_invent_requested_quantity():
    db = MemoryDb()
    context = entry_context(5)
    result = asyncio.run(
        reconcile_order_update(
            db,
            context,
            BrokerOrderUpdate(status="error", reason="temporary timeout"),
        )
    )
    assert result.trade_status == "working_unconfirmed"
    assert "quantity" not in db.trades["entry-trade"]
    assert db.positions == {}
