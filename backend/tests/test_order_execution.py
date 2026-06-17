import pathlib
import sys
import types
import unittest
from unittest.mock import patch


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.modules.setdefault(
    "aiohttp",
    types.SimpleNamespace(
        ClientTimeout=lambda *args, **kwargs: None,
        TCPConnector=lambda *args, **kwargs: None,
        ClientSession=object,
    ),
)


class OrderExecutionTests(unittest.TestCase):
    def test_resolve_broker_config_decrypts_stored_credentials(self):
        from order_execution import resolve_broker_config

        settings = {
            "active_broker": "alpaca",
            "broker_configs": {
                "alpaca": {
                    "broker_type": "alpaca",
                    "api_key": "enc:key",
                    "api_secret": "enc:secret",
                    "paper": "true",
                }
            },
        }

        with patch(
            "order_execution.decrypt_broker_config",
            return_value={
                "broker_type": "alpaca",
                "api_key": "real-key",
                "api_secret": "real-secret",
                "paper": "true",
            },
        ) as decrypt:
            config = resolve_broker_config(settings, "alpaca")

        decrypt.assert_called_once()
        self.assertEqual(config["api_key"], "real-key")
        self.assertEqual(config["api_secret"], "real-secret")

    def test_secretstr_values_are_materialized_for_broker_clients(self):
        from models import BrokerConfig, BrokerType
        from order_execution import materialize_secret_values

        config = BrokerConfig(
            broker_type=BrokerType.ALPACA,
            api_key="real-key",
            api_secret="real-secret",
        )

        materialized = materialize_secret_values(config)

        self.assertEqual(materialized["api_key"], "real-key")
        self.assertEqual(materialized["api_secret"], "real-secret")
        self.assertNotEqual(materialized["api_key"], "**********")

    def test_legacy_alpaca_headers_use_unmasked_secret_values(self):
        from broker_clients import AlpacaClient
        from models import BrokerConfig, BrokerType

        client = AlpacaClient(
            BrokerConfig(
                broker_type=BrokerType.ALPACA,
                api_key="real-key",
                api_secret="real-secret",
            )
        )

        headers = client._get_headers()

        self.assertEqual(headers["APCA-API-KEY-ID"], "real-key")
        self.assertEqual(headers["APCA-API-SECRET-KEY"], "real-secret")

    def test_live_execution_rejects_broker_without_order_status_support(self):
        from order_execution import BrokerConfigurationError, require_order_status_support

        class BrokerWithoutStatus:
            pass

        with self.assertRaises(BrokerConfigurationError):
            require_order_status_support(BrokerWithoutStatus(), require=True)


if __name__ == "__main__":
    unittest.main()
