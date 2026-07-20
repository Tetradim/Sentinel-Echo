import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class ExitPlanHardeningTests(unittest.TestCase):
    def test_partial_exit_percentage_applies_once_across_lots(self):
        from trade_lifecycle import build_exit_plans

        positions = [
            {
                "id": "old-lot",
                "ticker": "SPY",
                "strike": 750.0,
                "option_type": "CALL",
                "expiration": "7/17/2026",
                "current_price": 0.30,
                "remaining_quantity": 1,
                "status": "partial",
            },
            {
                "id": "re-entry-lot",
                "ticker": "SPY",
                "strike": 750.0,
                "option_type": "CALL",
                "expiration": "7/17/2026",
                "current_price": 0.30,
                "remaining_quantity": 1,
                "status": "open",
            },
        ]
        alert = {
            "alert_type": "sell",
            "ticker": "SPY",
            "strike": 750.0,
            "option_type": "CALL",
            "expiration": None,
            "sell_percentage": 10.0,
            "entry_price": 0.30,
        }

        plans = build_exit_plans(positions, alert)

        self.assertEqual(sum(plan["quantity"] for plan in plans), 1)
        self.assertEqual([plan["position"]["id"] for plan in plans], ["old-lot"])

    def test_exit_without_expiration_blocks_cross_expiration_match(self):
        from trade_lifecycle import build_exit_plans

        positions = [
            {
                "id": "zero-dte",
                "ticker": "SPY",
                "strike": 748.0,
                "option_type": "CALL",
                "expiration": "6/30/2026",
                "current_price": 0.50,
                "remaining_quantity": 5,
                "status": "open",
            },
            {
                "id": "one-dte",
                "ticker": "SPY",
                "strike": 748.0,
                "option_type": "CALL",
                "expiration": "7/1/2026",
                "current_price": 0.50,
                "remaining_quantity": 2,
                "status": "open",
            },
        ]
        alert = {
            "alert_type": "sell",
            "ticker": "SPY",
            "strike": 748.0,
            "option_type": "CALL",
            "expiration": None,
            "sell_percentage": 80.0,
            "entry_price": 0.50,
        }

        with self.assertRaisesRegex(ValueError, "ambiguous across multiple expirations"):
            build_exit_plans(positions, alert)

    def test_full_exit_still_closes_all_matching_lots(self):
        from trade_lifecycle import build_exit_plans

        positions = [
            {
                "id": "lot-a",
                "ticker": "QQQ",
                "strike": 726.0,
                "option_type": "CALL",
                "expiration": "7/14/2026",
                "current_price": 0.80,
                "remaining_quantity": 2,
                "status": "open",
            },
            {
                "id": "lot-b",
                "ticker": "QQQ",
                "strike": 726.0,
                "option_type": "CALL",
                "expiration": "7/14/2026",
                "current_price": 0.80,
                "remaining_quantity": 3,
                "status": "open",
            },
        ]
        alert = {
            "alert_type": "close",
            "ticker": "QQQ",
            "strike": 726.0,
            "option_type": "CALL",
            "expiration": None,
            "sell_percentage": 100.0,
            "entry_price": 0.80,
        }

        plans = build_exit_plans(positions, alert)

        self.assertEqual(sum(plan["quantity"] for plan in plans), 5)
        self.assertEqual([plan["quantity"] for plan in plans], [2, 3])


if __name__ == "__main__":
    unittest.main()
