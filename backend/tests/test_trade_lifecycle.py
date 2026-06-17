import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class TradeLifecycleTests(unittest.TestCase):
    def test_exit_alert_builds_partial_exit_for_matching_position(self):
        from trade_lifecycle import build_exit_plans

        positions = [
            {
                "id": "pos-1",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "CALL",
                "expiration": "6/21",
                "entry_price": 1.00,
                "current_price": 1.35,
                "remaining_quantity": 3,
                "status": "open",
            },
            {
                "id": "pos-2",
                "ticker": "QQQ",
                "strike": 450.0,
                "option_type": "PUT",
                "expiration": "6/21",
                "entry_price": 1.00,
                "current_price": 1.10,
                "remaining_quantity": 2,
                "status": "open",
            },
        ]
        alert = {
            "alert_type": "sell",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "sell_percentage": 50.0,
            "entry_price": 1.40,
        }

        plans = build_exit_plans(positions, alert)

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["position"]["id"], "pos-1")
        self.assertEqual(plans[0]["quantity"], 1)
        self.assertEqual(plans[0]["exit_price"], 1.40)

    def test_exit_alert_requires_a_known_exit_price(self):
        from trade_lifecycle import build_exit_plans

        positions = [
            {
                "id": "pos-1",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "CALL",
                "expiration": "6/21",
                "entry_price": 1.00,
                "current_price": None,
                "remaining_quantity": 1,
                "status": "open",
            }
        ]
        alert = {
            "alert_type": "sell",
            "ticker": "SPY",
            "sell_percentage": 100.0,
            "entry_price": None,
        }

        with self.assertRaises(ValueError):
            build_exit_plans(positions, alert)


if __name__ == "__main__":
    unittest.main()
