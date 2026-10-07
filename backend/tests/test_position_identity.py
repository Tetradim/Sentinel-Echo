import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class PositionIdentityTests(unittest.TestCase):
    def test_trade_cycle_position_id_is_stable_per_entry_trade(self):
        from position_identity import trade_cycle_position_id

        first = trade_cycle_position_id(
            "alpaca", "SPY", 764, "PUT", "2026-09-30", "trade-reentry-1"
        )
        repeated = trade_cycle_position_id(
            "alpaca", "SPY", 764, "PUT", "09/30/26", "trade-reentry-1"
        )
        second = trade_cycle_position_id(
            "alpaca", "SPY", 764, "PUT", "2026-09-30", "trade-reentry-2"
        )

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("position-alpaca-spy-260930-p-764-cycle-"))


if __name__ == "__main__":
    unittest.main()
