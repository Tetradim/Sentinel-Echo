import pathlib
import sys
import asyncio
import os
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
os.environ.setdefault("USE_SQLITE", "true")
sys.path.insert(0, str(BACKEND_DIR))


class PaperShadowTests(unittest.TestCase):
    def test_build_entry_shadow_records_creates_linked_simulated_trade_and_position(self):
        from models import Alert
        from paper_shadow import build_entry_shadow_records

        alert = Alert(
            id="alert-123",
            ticker="SPY",
            strike=500,
            option_type="CALL",
            expiration="6/21",
            entry_price=1.25,
        )

        trade, position = build_entry_shadow_records(
            alert=alert,
            quantity=2,
            broker="alpaca",
        )

        self.assertEqual(trade.alert_id, "alert-123")
        self.assertEqual(trade.status, "paper_shadow")
        self.assertEqual(trade.broker, "alpaca:paper_shadow")
        self.assertTrue(trade.simulated)
        self.assertEqual(trade.order_id, "paper-shadow:alert-123")
        self.assertEqual(position.trade_ids, [trade.id])
        self.assertEqual(position.remaining_quantity, 2)
        self.assertEqual(position.total_cost, 250.0)
        self.assertTrue(position.simulated)
        self.assertEqual(position.broker, "alpaca:paper_shadow")

    def test_live_paper_shadow_exit_updates_shadow_position_without_live_order(self):
        from models import Alert, Settings
        from server import process_exit_alert

        class FakeDatabase:
            def __init__(self):
                self.inserted_trades = []
                self.updated_positions = []
                self.positions_by_status = {
                    "open": [
                        {
                            "id": "shadow-pos",
                            "ticker": "SPY",
                            "strike": 500.0,
                            "option_type": "CALL",
                            "expiration": "6/21",
                            "entry_price": 1.00,
                            "current_price": 1.00,
                            "original_quantity": 2,
                            "remaining_quantity": 2,
                            "total_cost": 200.0,
                            "broker": "alpaca:paper_shadow",
                            "status": "open",
                            "realized_pnl": 0.0,
                            "simulated": True,
                            "trade_ids": ["entry-shadow-trade"],
                        }
                    ],
                    "partial": [],
                }

            async def get_positions(self, status):
                return self.positions_by_status[status]

            async def insert_trade(self, trade):
                self.inserted_trades.append(trade)

            async def update_position(self, position_id, updates):
                self.updated_positions.append((position_id, updates))

        fake_db = FakeDatabase()

        import server

        original_get_db = server.get_db
        server.get_db = lambda: fake_db
        try:
            processed = asyncio.run(
                process_exit_alert(
                    Alert(
                        id="exit-alert",
                        ticker="SPY",
                        strike=500.0,
                        option_type="CALL",
                        expiration="6/21",
                        entry_price=1.50,
                        alert_type="sell",
                        sell_percentage=50.0,
                    ),
                    {
                        "alert_type": "sell",
                        "ticker": "SPY",
                        "strike": 500.0,
                        "option_type": "CALL",
                        "expiration": "6/21",
                        "entry_price": 1.50,
                        "sell_percentage": 50.0,
                    },
                    Settings(simulation_mode=False, active_broker="alpaca"),
                    {"simulation_mode": False},
                    source_config={"paper_shadow": True},
                )
            )
        finally:
            server.get_db = original_get_db

        self.assertTrue(processed)
        self.assertEqual(len(fake_db.inserted_trades), 1)
        self.assertEqual(fake_db.inserted_trades[0]["side"], "SELL")
        self.assertEqual(fake_db.inserted_trades[0]["status"], "paper_shadow")
        self.assertTrue(fake_db.inserted_trades[0]["simulated"])
        self.assertEqual(fake_db.inserted_trades[0]["broker"], "alpaca:paper_shadow")
        self.assertEqual(fake_db.inserted_trades[0]["realized_pnl"], 50.0)
        self.assertEqual(fake_db.updated_positions[0][0], "shadow-pos")
        self.assertEqual(fake_db.updated_positions[0][1]["$set"]["remaining_quantity"], 1)
        self.assertEqual(fake_db.updated_positions[0][1]["$set"]["status"], "partial")


if __name__ == "__main__":
    unittest.main()
