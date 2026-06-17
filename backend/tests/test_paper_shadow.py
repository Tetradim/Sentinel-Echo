import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
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


if __name__ == "__main__":
    unittest.main()
