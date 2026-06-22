import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class StrategyManagerTests(unittest.TestCase):
    def test_strategy_manager_parses_serialized_disabled_flags(self):
        from strategies import create_strategy_manager

        manager = create_strategy_manager(
            {
                "trailing_stop_enabled": "false",
                "take_profit_enabled": "false",
                "time_exit_enabled": "false",
            }
        )

        self.assertFalse(manager.enable_trailing_stop)
        self.assertFalse(manager.enable_take_profit)
        self.assertFalse(manager.enable_time_exit)
        self.assertIsNone(manager.trailing_stop)
        self.assertIsNone(manager.take_profit)
        self.assertEqual(
            manager.to_dict()["enabled"],
            {"trailing": False, "take_profit": False, "time_exit": False},
        )


if __name__ == "__main__":
    unittest.main()
