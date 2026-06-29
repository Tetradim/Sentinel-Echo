import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeTradeDb:
    def __init__(self, trades):
        self.trades = trades

    async def get_trades(self, limit=50):
        return list(self.trades)


class StartupFillMonitoringTests(unittest.TestCase):
    def test_startup_reschedules_pending_broker_fill_monitors(self):
        import server

        scheduled = []
        db = FakeTradeDb(
            [
                {
                    "id": "trade-pending",
                    "order_id": "broker-order-1",
                    "status": "pending",
                    "ticker": "SPY",
                    "strike": 500.0,
                    "option_type": "CALL",
                    "expiration": "2026-06-30",
                    "quantity": 2,
                    "broker": "alpaca",
                    "alert_id": "alert-1",
                    "entry_price": 1.25,
                    "simulated": False,
                },
                {"id": "trade-done", "order_id": "broker-order-2", "status": "executed"},
            ]
        )

        async def fake_schedule_monitor(**kwargs):
            scheduled.append(kwargs)

        count = asyncio.run(
            server.resume_pending_fill_monitors(
                db,
                {"active_broker": "alpaca"},
                broker_client=object(),
                schedule_monitor=fake_schedule_monitor,
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(scheduled[0]["order_context"].trade_id, "trade-pending")
        self.assertEqual(scheduled[0]["order_context"].order_id, "broker-order-1")


if __name__ == "__main__":
    unittest.main()
