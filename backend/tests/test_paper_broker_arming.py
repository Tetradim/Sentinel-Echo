import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class PaperBrokerArmingTests(unittest.TestCase):
    def test_alpaca_paper_broker_does_not_require_live_money_arming(self):
        from models import Settings
        from server import _requires_live_arming

        settings = Settings(active_broker="alpaca", simulation_mode=False)
        settings_raw = {
            "active_broker": "alpaca",
            "broker_configs": {
                "alpaca": {
                    "broker_type": "alpaca",
                    "base_url": "https://paper-api.alpaca.markets",
                }
            },
        }

        self.assertFalse(_requires_live_arming(settings, settings_raw))

    def test_alpaca_live_broker_still_requires_live_money_arming(self):
        from models import Settings
        from server import _requires_live_arming

        settings = Settings(active_broker="alpaca", simulation_mode=False)
        settings_raw = {
            "active_broker": "alpaca",
            "broker_configs": {
                "alpaca": {
                    "broker_type": "alpaca",
                    "base_url": "https://api.alpaca.markets",
                }
            },
        }

        self.assertTrue(_requires_live_arming(settings, settings_raw))

    def test_non_simulation_non_paper_broker_requires_live_money_arming(self):
        from models import Settings
        from server import _requires_live_arming

        settings = Settings(active_broker="ibkr", simulation_mode=False)
        settings_raw = {
            "active_broker": "ibkr",
            "broker_configs": {
                "ibkr": {
                    "broker_type": "ibkr",
                    "gateway_url": "https://localhost:5000",
                }
            },
        }

        self.assertTrue(_requires_live_arming(settings, settings_raw))


if __name__ == "__main__":
    unittest.main()
