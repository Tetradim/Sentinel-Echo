import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeLifecycleDb:
    def __init__(self):
        self.trade_updates = []
        self.alert_updates = []
        self.position_updates = []
        self.positions = {}
        self.inserted_positions = []

    async def update_trade(self, trade_id, updates):
        self.trade_updates.append((trade_id, updates))

    async def update_alert(self, alert_id, updates):
        self.alert_updates.append((alert_id, updates))

    async def insert_position(self, position):
        self.positions[position["id"]] = position
        self.inserted_positions.append(position)
        return position["id"]

    async def get_position_by_id(self, position_id):
        return self.positions.get(position_id)

    async def update_position(self, position_id, updates):
        self.position_updates.append((position_id, updates))
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
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

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
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        context = OrderContext(
            trade_id="trade-entry",
            order_id="order-entry",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=3,
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

    def test_filled_entry_order_adds_metadata_oco_plan_from_actual_fill_price(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

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
            alert_price=2.00,
        )
        settings = {
            "take_profit_enabled": True,
            "take_profit_percentage": 50.0,
            "stop_loss_enabled": True,
            "stop_loss_percentage": 20.0,
            "stop_loss_order_type": "market",
            "trailing_stop_enabled": True,
            "trailing_stop_type": "percent",
            "trailing_stop_percent": 10.0,
        }

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.35),
                settings=settings,
            )
        )

        position = db.inserted_positions[0]
        plan = position["oco_exit_plan"]
        self.assertEqual(plan["entry_price"], 1.35)
        self.assertEqual(plan["quantity"], 2)
        self.assertEqual(plan["take_profit"]["trigger_price"], 2.03)
        self.assertEqual(plan["stop_loss"]["trigger_price"], 1.08)
        self.assertEqual(position["oco_exit_status"], "metadata_only")
        self.assertFalse(position["oco_exit_protected"])

    def test_repeated_filled_entry_order_does_not_insert_duplicate_position(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

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
        update = BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.35)

        first = asyncio.run(reconcile_order_update(db, context, update))
        second = asyncio.run(reconcile_order_update(db, context, update))

        self.assertEqual(first.position_id, second.position_id)
        self.assertEqual(len(db.inserted_positions), 1)
        self.assertEqual(db.inserted_positions[0]["remaining_quantity"], 2)

    def test_filled_average_down_buy_updates_existing_position(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-1"] = {
            "id": "position-1",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "entry_price": 1.00,
            "original_quantity": 4,
            "remaining_quantity": 4,
            "total_cost": 400.0,
            "average_down_count": 0,
            "initial_entry_price": None,
            "trade_ids": ["trade-entry"],
            "status": "open",
            "broker": "alpaca",
            "simulated": False,
        }
        context = OrderContext(
            trade_id="trade-average-down",
            order_id="order-average-down",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            position_id="position-1",
            broker="alpaca",
            alert_id="alert-average-down",
        )

        result = asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=0.80),
            )
        )

        self.assertEqual(result.trade_status, "executed")
        self.assertEqual(result.position_status, "open")
        self.assertEqual(len(db.inserted_positions), 0)
        trade_update = db.trade_updates[0][1]
        self.assertEqual(trade_update["side"], "BUY")
        self.assertEqual(trade_update["quantity"], 2)
        self.assertEqual(trade_update["entry_price"], 0.80)
        position = db.positions["position-1"]
        self.assertEqual(position["remaining_quantity"], 6)
        self.assertEqual(position["original_quantity"], 6)
        self.assertAlmostEqual(position["entry_price"], 0.9333333333)
        self.assertEqual(position["total_cost"], 560.0)
        self.assertEqual(position["average_down_count"], 1)
        self.assertEqual(position["initial_entry_price"], 1.00)
        self.assertIn("trade-average-down", position["trade_ids"])
        self.assertEqual(
            db.alert_updates,
            [
                (
                    "alert-average-down",
                    {
                        "processed": True,
                        "trade_executed": True,
                        "trade_result": "filled",
                    },
                )
            ],
        )

    def test_filled_exit_order_reduces_remaining_quantity_and_closes_when_zero(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

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

    def test_repeated_filled_exit_order_does_not_reduce_position_twice(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-1"] = {
            "id": "position-1",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "entry_price": 1.00,
            "remaining_quantity": 2,
            "realized_pnl": 0.0,
            "trade_ids": ["trade-entry"],
            "status": "open",
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
            requested_quantity=1,
            position_id="position-1",
            broker="alpaca",
        )
        update = BrokerOrderUpdate(status="filled", filled_qty=1, avg_fill_price=1.50)

        asyncio.run(reconcile_order_update(db, context, update))
        asyncio.run(reconcile_order_update(db, context, update))

        position = db.positions["position-1"]
        self.assertEqual(position["remaining_quantity"], 1)
        self.assertEqual(position["realized_pnl"], 50.0)
        self.assertEqual(position["trade_ids"].count("trade-exit"), 1)
        self.assertEqual(len(db.position_updates), 1)


if __name__ == "__main__":
    unittest.main()
