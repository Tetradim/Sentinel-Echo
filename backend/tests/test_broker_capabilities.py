import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class BrokerCapabilityTests(unittest.TestCase):
    def test_known_broker_capabilities_expose_order_status_and_cancel_support(self):
        from broker_capabilities import get_broker_capabilities

        alpaca = get_broker_capabilities("alpaca")

        self.assertTrue(alpaca["supports_options"])
        self.assertTrue(alpaca["supports_order_status"])
        self.assertTrue(alpaca["supports_cancel_order"])
        self.assertEqual(alpaca["auth_mode"], "api_key")

    def test_unknown_broker_capabilities_are_safe(self):
        from broker_capabilities import get_broker_capabilities

        unknown = get_broker_capabilities("unknown")

        self.assertFalse(unknown["supports_live_trading"])
        self.assertFalse(unknown["supports_order_status"])
        self.assertFalse(unknown["supports_cancel_order"])

    def test_broker_configured_requires_each_required_auth_field(self):
        from broker_capabilities import is_broker_configured

        required_fields_by_broker = {
            "alpaca": ("api_key", "api_secret"),
            "ibkr": ("gateway_url", "account_id"),
            "tradier": ("access_token", "account_id"),
            "tradestation": ("ts_client_id", "ts_client_secret", "ts_refresh_token"),
            "td_ameritrade": ("client_id", "refresh_token"),
            "thinkorswim": ("tos_consumer_key", "tos_refresh_token", "tos_account_id"),
            "webull": ("username", "password", "device_id", "trade_token"),
            "robinhood": ("username", "password"),
            "wealthsimple": ("ws_email", "ws_password"),
        }

        for broker_id, required_fields in required_fields_by_broker.items():
            with self.subTest(broker_id=broker_id):
                config = {"broker_type": broker_id}
                config.update({field: f"value-{field}" for field in required_fields})
                self.assertTrue(is_broker_configured({broker_id: config}, broker_id))

                for missing_field in required_fields:
                    incomplete = dict(config)
                    incomplete[missing_field] = " "
                    self.assertFalse(
                        is_broker_configured({broker_id: incomplete}, broker_id),
                        f"{broker_id} should require {missing_field}",
                    )

    def test_alpaca_config_ignores_defaults_without_credentials(self):
        from broker_capabilities import is_broker_configured

        self.assertFalse(
            is_broker_configured(
                {
                    "alpaca": {
                        "broker_type": "alpaca",
                        "base_url": "https://paper-api.alpaca.markets",
                        "gateway_url": "https://localhost:5000",
                    }
                },
                "alpaca",
            )
        )

    def test_missing_broker_config_fields_reports_blank_required_values(self):
        from broker_capabilities import missing_broker_config_fields

        missing = missing_broker_config_fields(
            {
                "broker_type": "alpaca",
                "api_key": "key",
                "api_secret": " ",
                "base_url": "https://paper-api.alpaca.markets",
            },
            "alpaca",
        )

        self.assertEqual(missing, ("api_secret",))


if __name__ == "__main__":
    unittest.main()
