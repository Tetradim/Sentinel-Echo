import pathlib
import sys
import types
import unittest
from unittest.mock import patch
import asyncio


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
try:
    import aiohttp  # noqa: F401
except ModuleNotFoundError:
    sys.modules.setdefault(
        "aiohttp",
        types.SimpleNamespace(
            ClientTimeout=lambda *args, **kwargs: None,
            TCPConnector=lambda *args, **kwargs: None,
            ClientSession=object,
        ),
    )


class OrderExecutionTests(unittest.TestCase):
    def test_build_oco_exit_plan_creates_deterministic_take_profit_and_stop_loss_orders(self):
        from order_execution import build_client_order_id, build_oco_exit_plan

        plan = build_oco_exit_plan(
            {
                "take_profit_enabled": True,
                "take_profit_percentage": 50,
                "stop_loss_enabled": True,
                "stop_loss_percentage": 25,
                "stop_loss_order_type": "limit",
                "trailing_stop_enabled": True,
                "trailing_stop_type": "percent",
                "trailing_stop_percent": 10,
            },
            alert_id="alert/ABC 123",
            position_id="position:456",
            entry_price=1.20,
            quantity=2,
        )

        self.assertEqual(plan["status"], "armed")
        self.assertEqual(plan["oco_group_id"], build_client_order_id("alert/ABC 123", "oco", "position:456"))
        self.assertEqual(plan["entry_price"], 1.20)
        self.assertEqual(plan["quantity"], 2)
        self.assertEqual(plan["take_profit"]["trigger_price"], 1.80)
        self.assertEqual(plan["take_profit"]["order_type"], "limit")
        self.assertEqual(plan["take_profit"]["client_order_id"], build_client_order_id("alert/ABC 123", "take-profit", "position:456"))
        self.assertEqual(plan["take_profit"]["oco_group_id"], plan["oco_group_id"])
        self.assertEqual(plan["stop_loss"]["trigger_price"], 0.90)
        self.assertEqual(plan["stop_loss"]["order_type"], "limit")
        self.assertEqual(plan["stop_loss"]["client_order_id"], build_client_order_id("alert/ABC 123", "stop-loss", "position:456"))
        self.assertEqual(plan["stop_loss"]["oco_group_id"], plan["oco_group_id"])
        self.assertEqual(
            plan["trailing_stop"],
            {"enabled": True, "type": "percent", "percent": 10.0, "cents": None},
        )

    def test_build_oco_exit_plan_returns_empty_when_both_guards_are_not_enabled(self):
        from order_execution import build_oco_exit_plan

        self.assertEqual(
            build_oco_exit_plan(
                {"take_profit_enabled": True, "stop_loss_enabled": False},
                alert_id="alert-1",
                position_id="pos-1",
                entry_price=1.00,
                quantity=1,
            ),
            {},
        )

    def test_build_client_order_id_is_deterministic_and_broker_safe(self):
        from order_execution import build_client_order_id

        client_order_id = build_client_order_id(
            alert_id="alert/ABC 123",
            side="BUY",
            position_id="position:456",
        )

        self.assertEqual(client_order_id, "consolidation-buy-alert-ABC-123-position-456")
        self.assertLessEqual(len(client_order_id), 128)
        self.assertEqual(
            client_order_id,
            build_client_order_id(
                alert_id="alert/ABC 123",
                side="buy",
                position_id="position:456",
            ),
        )

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

    def test_resolve_broker_config_rejects_malformed_broker_configs_container(self):
        from order_execution import BrokerConfigurationError, resolve_broker_config

        settings = {
            "active_broker": "alpaca",
            "broker_configs": "alpaca",
        }

        with self.assertRaises(BrokerConfigurationError) as raised:
            resolve_broker_config(settings, "alpaca")

        self.assertIn("No broker config for alpaca", str(raised.exception))

    def test_resolve_broker_config_rejects_missing_required_credentials_after_decrypt(self):
        from order_execution import BrokerConfigurationError, resolve_broker_config

        settings = {
            "active_broker": "alpaca",
            "broker_configs": {
                "alpaca": {
                    "broker_type": "alpaca",
                    "api_key": "enc:key",
                    "api_secret": "enc:",
                    "base_url": "https://paper-api.alpaca.markets",
                }
            },
        }

        with patch(
            "order_execution.decrypt_broker_config",
            return_value={
                "broker_type": "alpaca",
                "api_key": "real-key",
                "api_secret": " ",
                "base_url": "https://paper-api.alpaca.markets",
            },
        ):
            with self.assertRaises(BrokerConfigurationError) as raised:
                resolve_broker_config(settings, "alpaca")

        message = str(raised.exception)
        self.assertIn("Broker config for alpaca is missing required fields", message)
        self.assertIn("api_secret", message)
        self.assertNotIn("real-key", message)

    def test_resolve_broker_config_rejects_malformed_decrypted_config(self):
        from order_execution import BrokerConfigurationError, resolve_broker_config

        settings = {
            "active_broker": "alpaca",
            "broker_configs": {
                "alpaca": {
                    "broker_type": "alpaca",
                    "api_key": "enc:key",
                    "api_secret": "enc:secret",
                }
            },
        }

        with patch("order_execution.decrypt_broker_config", return_value="configured"):
            with self.assertRaises(BrokerConfigurationError) as raised:
                resolve_broker_config(settings, "alpaca")

        self.assertIn("Broker config for alpaca is malformed", str(raised.exception))

    def test_configured_broker_client_rejects_incomplete_config_before_factory(self):
        from order_execution import BrokerConfigurationError, get_configured_broker_client

        settings = {
            "active_broker": "alpaca",
            "broker_configs": {
                "alpaca": {
                    "broker_type": "alpaca",
                    "api_key": "real-key",
                }
            },
        }

        with patch("broker_clients.get_broker_client") as factory:
            with self.assertRaises(BrokerConfigurationError):
                get_configured_broker_client(settings, "alpaca")

        factory.assert_not_called()

    def test_configured_broker_client_ignores_stored_duplicate_broker_type(self):
        from models import BrokerType
        from order_execution import get_configured_broker_client

        settings = {
            "active_broker": "alpaca",
            "broker_configs": {
                "alpaca": {
                    "broker_type": "alpaca",
                    "api_key": "real-key",
                    "api_secret": "real-secret",
                }
            },
        }
        sentinel_client = object()

        with patch("broker_clients.get_broker_client", return_value=sentinel_client) as factory:
            client = get_configured_broker_client(settings, "alpaca")

        self.assertIs(client, sentinel_client)
        broker_type, broker_config = factory.call_args.args
        self.assertEqual(broker_type, BrokerType.ALPACA)
        self.assertEqual(broker_config.broker_type, BrokerType.ALPACA)
        self.assertEqual(broker_config.api_key.get_secret_value(), "real-key")

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

    def test_legacy_alpaca_order_payload_includes_client_order_id(self):
        from broker_clients import AlpacaClient
        from models import BrokerConfig, BrokerType

        class FakeResponse:
            status = 201

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return False

            async def json(self):
                return {"id": "order-123"}

        class FakeSession:
            def __init__(self):
                self.posts = []

            def post(self, url, *, headers=None, json=None, data=None, ssl=None):
                self.posts.append(
                    {
                        "url": url,
                        "headers": headers,
                        "json": json,
                        "data": data,
                        "ssl": ssl,
                    }
                )
                return FakeResponse()

        async def fake_get_session():
            return fake_session

        fake_session = FakeSession()
        client = AlpacaClient(
            BrokerConfig(
                broker_type=BrokerType.ALPACA,
                api_key="real-key",
                api_secret="real-secret",
                base_url="https://paper-api.alpaca.markets",
            )
        )
        client.connected = True
        client._get_session = fake_get_session

        result = asyncio.run(
            client.place_order(
                ticker="SPY",
                strike=500,
                option_type="CALL",
                expiration="6/21/2026",
                side="BUY",
                quantity=1,
                price=1.25,
                client_order_id="consolidation-buy-alert-123",
            )
        )

        self.assertEqual(result["order_id"], "order-123")
        self.assertEqual(
            fake_session.posts[0]["json"]["client_order_id"],
            "consolidation-buy-alert-123",
        )

    def test_legacy_alpaca_get_order_status_maps_fill_fields(self):
        from broker_clients import AlpacaClient
        from models import BrokerConfig, BrokerType

        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return False

            async def json(self):
                return {
                    "status": "partially_filled",
                    "filled_qty": "1",
                    "filled_avg_price": "1.23",
                }

        class FakeSession:
            def __init__(self):
                self.gets = []

            def get(self, url, *, headers=None):
                self.gets.append({"url": url, "headers": headers})
                return FakeResponse()

        async def fake_get_session():
            return fake_session

        fake_session = FakeSession()
        client = AlpacaClient(
            BrokerConfig(
                broker_type=BrokerType.ALPACA,
                api_key="real-key",
                api_secret="real-secret",
                base_url="https://paper-api.alpaca.markets",
            )
        )
        client._get_session = fake_get_session

        status = asyncio.run(client.get_order_status("order-123"))

        self.assertEqual(status["status"], "partial")
        self.assertEqual(status["filled_qty"], 1)
        self.assertEqual(status["avg_fill_price"], 1.23)
        self.assertEqual(
            fake_session.gets[0]["url"],
            "https://paper-api.alpaca.markets/v2/orders/order-123",
        )

    def test_legacy_tradier_get_order_status_maps_fill_fields(self):
        from broker_clients import TradierClient
        from models import BrokerConfig, BrokerType

        class FakeResponse:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return False

            async def json(self):
                return {
                    "order": {
                        "status": "partially_filled",
                        "exec_quantity": "2",
                        "avg_fill_price": "1.45",
                        "reason_description": "",
                    }
                }

        class FakeSession:
            def __init__(self):
                self.gets = []

            def get(self, url, *, headers=None):
                self.gets.append({"url": url, "headers": headers})
                return FakeResponse()

        async def fake_get_session():
            return fake_session

        fake_session = FakeSession()
        client = TradierClient(
            BrokerConfig(
                broker_type=BrokerType.TRADIER,
                access_token="real-token",
                account_id="acct-123",
            )
        )
        client._get_session = fake_get_session

        status = asyncio.run(client.get_order_status("order-456"))

        self.assertEqual(status["status"], "partial")
        self.assertEqual(status["filled_qty"], 2)
        self.assertEqual(status["avg_fill_price"], 1.45)
        self.assertEqual(
            fake_session.gets[0]["url"],
            "https://api.tradier.com/v1/accounts/acct-123/orders/order-456",
        )


if __name__ == "__main__":
    unittest.main()
