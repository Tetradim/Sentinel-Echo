import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeDb:
    def __init__(self):
        self.trade_updates = []

    async def update_trade(self, trade_id, updates):
        self.trade_updates.append((trade_id, updates))


class BrokerWithoutStatus:
    pass


class FillMonitorTests(unittest.TestCase):
    def test_missing_order_status_marks_trade_unconfirmed_not_executed(self):
        from fill_monitor import monitor_fill

        db = FakeDb()

        asyncio.run(
            monitor_fill(
                trade_id="trade-1",
                order_id="order-1",
                expected_qty=2,
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


if __name__ == "__main__":
    unittest.main()
