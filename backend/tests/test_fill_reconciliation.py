import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from fill_reconciliation import BrokerOrderUpdate, OrderContext
from fill_reconciliation_v2 import reconcile_order_update


class FakeLifecycleDb:
    def __init__(self):
        self.trade_updates = []
        self.alert_updates = []
        self.positions = {}
        self.inserted_positions = []
        self.trades = {}

    async def get_trades(self, limit=1000):
        return list(self.trades.values())[:limit]

    async def update_trade(self, trade_id, updates):
        self.trade_updates.append((trade_id, updates))
        self.trades.setdefault(trade_id, {"id": trade_id}).update(updates)

    async def update_alert(self, alert_id, updates):
        self.alert_updates.append((alert_id, updates))

    async def insert_position(self, position):
        self.positions[position["id"]] = position
        self.inserted_positions.append(position)
        return position["id"]

    async def get_position_by_id(self, position_id):
        return self.positions.get(position_id)

    async def update_position(self, position_id, updates):
        position = dict(self.positions[position_id])
        if "$set" in updates:
            position.update(updates["$set"])
        if "$push" in updates:
            for key, value in updates["$push"].items():
                position.setdefault(key, []).append(value)
        if "$set" not in updates and "$push" not in updates:
            position.update(updates)
        self.positions[position_id] = position


class FillReconciliationTests(unittest.TestCase):
    def test_rejected_entry_order_does_not_leave_open_position(self):
        db = FakeLifecycleDb()
        context = OrderContext(
            trade_id="trade-entry",
            order_id="order-entry",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
            alert_id="alert-entry",
        )

        result = asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="rejected", reason="insufficient buying power"),
            )
        )

        self.assertEqual(result.trade_status, "failed")
        self.assertEqual(db.trade_updates[0][1]["status"], "failed")
        self.assertEqual(db.trade_updates[0][1]["error_message"], "insufficient buying power")
        self.assertEqual(
            db.alert_updates,
            [
                (
                    "alert-entry",
                    {
                        "processed": True,
                        "trade_executed": False,
                        "trade_result": "failed: insufficient buying power",
                    },
                )
            ],
        )
        self.assertEqual(db.inserted_positions, [])

    def test_filled_entry_order_creates_open_position_from_fill_price(self):
        db = FakeLifecycleDb()
        context = OrderContext(
            trade_id="trade-entry",
            order_id="order-entry",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
            alert_id="alert-entry",
        )

        result = asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.35),
            )
        )

        self.assertEqual(result.trade_status, "executed")
        self.assertEqual(result.position_status, "open")
        self.assertEqual(db.trade_updates[0][1]["quantity"], 2)
        self.assertEqual(db.trade_updates[0][1]["entry_price"], 1.35)
        self.assertEqual(
            db.alert_updates,
            [
                (
                    "alert-entry",
                    {
                        "processed": True,
                        "trade_executed": True,
                        "trade_result": "filled",
                    },
                )
            ],
        )
        position = db.inserted_positions[0]
        self.assertEqual(position["ticker"], "SPY")
        self.assertEqual(position["original_quantity"], 2)
        self.assertEqual(position["remaining_quantity"], 2)
        self.assertEqual(position["entry_price"], 1.35)
        self.assertEqual(position["total_cost"], 270.0)

    def test_filled_exit_order_reduces_remaining_quantity_and_closes_when_zero(self):
        db = FakeLifecycleDb()
        db.positions["position-1"] = {
            "id": "position-1",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "entry_price": 1.00,
            "remaining_quantity": 2,
            "realized_pnl": 25.0,
            "trade_ids": ["trade-entry"],
            "status": "partial",
            "broker": "alpaca",
            "simulated": False,
        }
        context = OrderContext(
            trade_id="trade-exit",
            order_id="order-exit",
            side="SELL",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            position_id="position-1",
            broker="alpaca",
        )

        result = asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.50),
            )
        )

        self.assertEqual(result.trade_status, "executed")
        self.assertEqual(result.position_status, "closed")
        trade_update = db.trade_updates[0][1]
        self.assertEqual(trade_update["side"], "SELL")
        self.assertEqual(trade_update["exit_price"], 1.50)
        self.assertEqual(trade_update["realized_pnl"], 100.0)
        position = db.positions["position-1"]
        self.assertEqual(position["remaining_quantity"], 0)
        self.assertEqual(position["status"], "closed")
        self.assertEqual(position["realized_pnl"], 125.0)
        self.assertIn("trade-exit", position["trade_ids"])
        self.assertIn("closed_at", position)


if __name__ == "__main__":
    unittest.main()
