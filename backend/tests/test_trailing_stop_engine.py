import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class TrailingStopEngineTests(unittest.TestCase):
    def test_premium_trailing_stop_updates_peak_before_triggering(self):
        from trailing_stop_engine import evaluate_trailing_stop

        decision = evaluate_trailing_stop(
            {
                "id": "pos-1",
                "entry_price": 0.44,
                "highest_price": 0.44,
                "remaining_quantity": 1,
                "status": "open",
            },
            {
                "trailing_stop_enabled": True,
                "trailing_stop_type": "premium",
                "trailing_stop_cents": 0.09,
            },
            current_price=0.60,
        )

        self.assertEqual(decision["action"], "peak_updated")
        self.assertFalse(decision["triggered"])
        self.assertEqual(decision["highest_price"], 0.60)
        self.assertEqual(decision["trailing_stop_level"], 0.51)

    def test_premium_trailing_stop_triggers_from_persisted_peak(self):
        from trailing_stop_engine import evaluate_trailing_stop

        decision = evaluate_trailing_stop(
            {
                "id": "pos-1",
                "entry_price": 0.44,
                "highest_price": 0.60,
                "remaining_quantity": 1,
                "status": "open",
            },
            {
                "trailing_stop_enabled": True,
                "trailing_stop_type": "premium",
                "trailing_stop_cents": 0.09,
            },
            current_price=0.51,
        )

        self.assertEqual(decision["action"], "triggered")
        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["highest_price"], 0.60)
        self.assertEqual(decision["trailing_stop_level"], 0.51)
        self.assertEqual(decision["exit_price"], 0.51)


if __name__ == "__main__":
    unittest.main()
