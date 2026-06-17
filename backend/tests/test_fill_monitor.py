import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeDb:
    def __init__(self):
        self.trade_updates = []
        self.positions = {}
        self.inserted_positions = []

    async def update_trade(self, trade_id, updates):
        self.trade_updates.append((trade_id, updates))

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
        self.positions[position_id] = position


class BrokerWithoutStatus:
    pass


class BrokerWithFilledStatus:
    async def get_order_status(self, order_id):
        return {"status": "filled", "filled_qty": 2, "avg_fill_price": 1.25}


class FillMonitorTests(unittest.TestCase):
    def test_missing_order_status_marks_trade_unconfirmed_not_executed(self):
        from fill_reconciliation import OrderContext
        from fill_monitor import monitor_fill

        db = FakeDb()
        context = OrderContext(
            trade_id="trade-1",
            order_id="order-1",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
        )

        asyncio.run(
            monitor_fill(
                order_context=context,
                broker_client=BrokerWithoutStatus(),
                db=db,
                settings={},
                poll_interval_secs=0,
                max_polls=1,
            )
        )

        self.assertEqual(len(db.trade_updates), 1)
        _, update = db.trade_updates[0]
        self.assertEqual(update["status"], "unconfirmed")
        self.assertEqual(update["quantity"], 2)
        self.assertNotIn("executed_at", update)

    def test_filled_order_status_reconciles_position_from_broker_fill(self):
        from fill_reconciliation import OrderContext
        from fill_monitor import monitor_fill

        db = FakeDb()
        context = OrderContext(
            trade_id="trade-2",
            order_id="order-2",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
        )

        asyncio.run(
            monitor_fill(
                order_context=context,
                broker_client=BrokerWithFilledStatus(),
                db=db,
                settings={},
                poll_interval_secs=0,
                max_polls=1,
            )
        )

        self.assertEqual(db.trade_updates[0][1]["status"], "executed")
        self.assertEqual(db.trade_updates[0][1]["entry_price"], 1.25)
        self.assertEqual(len(db.inserted_positions), 1)
        self.assertEqual(db.inserted_positions[0]["remaining_quantity"], 2)


if __name__ == "__main__":
    unittest.main()
