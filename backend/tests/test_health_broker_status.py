import asyncio
import pathlib
import sys
import unittest
from unittest.mock import patch


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class HealthBrokerStatusTests(unittest.TestCase):
    def test_broker_health_uses_direct_configured_client_when_status_flag_is_stale(self):
        from routes.health import resolve_broker_connected

        class FakeClient:
            async def check_connection(self):
                return True

        connected = asyncio.run(
            resolve_broker_connected(
                {
                    "active_broker": "alpaca",
                    "broker_configs": {
                        "alpaca": {
                            "broker_type": "alpaca",
                            "api_key": "key",
                            "api_secret": "secret",
                            "base_url": "https://paper-api.alpaca.markets",
                        }
                    },
                },
                {"broker_connected": False},
                client_factory=lambda settings, broker_id: FakeClient(),
            )
        )

        self.assertTrue(connected)

    def test_status_resolves_stale_broker_flag_like_health_endpoint(self):
        from routes import health as health_route

        class FakeClient:
            async def check_connection(self):
                return True

        class FakeDb:
            async def get_settings(self):
                return {
                    "active_broker": "alpaca",
                    "broker_configs": {
                        "alpaca": {
                            "broker_type": "alpaca",
                            "api_key": "key",
                            "api_secret": "secret",
                            "base_url": "https://paper-api.alpaca.markets",
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                }

            async def get_runtime_state(self):
                return {"shutdown_triggered": False, "shutdown_reason": ""}

        health_route.set_db(FakeDb())
        health_route.update_bot_status("broker_connected", False)
        try:
            with patch("order_execution.get_configured_broker_client", return_value=FakeClient()):
                result = asyncio.run(health_route.get_status())
                cached = health_route.get_bot_status()["broker_connected"]
        finally:
            health_route.set_db(None)
            health_route.update_bot_status("broker_connected", False)

        self.assertTrue(result["broker_connected"])
        self.assertTrue(cached)

    def test_status_derives_alert_counters_from_database_when_runtime_was_reset(self):
        from routes import health as health_route

        class FakeDb:
            async def get_settings(self):
                return {
                    "active_broker": "alpaca",
                    "broker_configs": {
                        "alpaca": {
                            "broker_type": "alpaca",
                            "api_key": "key",
                            "api_secret": "secret",
                            "base_url": "https://paper-api.alpaca.markets",
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                }

            async def get_runtime_state(self):
                return {"shutdown_triggered": False, "shutdown_reason": ""}

            async def get_alerts(self, limit=1000):
                return [
                    {"id": "alert-2", "received_at": "2026-08-31T14:35:00+00:00", "processed": True},
                    {"id": "alert-1", "received_at": "2026-08-31T14:20:00+00:00", "processed": True},
                ]

        health_route.set_db(FakeDb())
        health_route.update_bot_status("broker_connected", True)
        health_route.update_bot_status("alerts_processed", 0)
        health_route.update_bot_status("last_alert_time", None)
        try:
            result = asyncio.run(health_route.get_status())
        finally:
            health_route.set_db(None)
            health_route.update_bot_status("broker_connected", False)
            health_route.update_bot_status("alerts_processed", 0)
            health_route.update_bot_status("last_alert_time", None)

        self.assertEqual(result["alerts_processed"], 2)
        self.assertEqual(result["last_alert_time"], "2026-08-31T14:35:00+00:00")


if __name__ == "__main__":
    unittest.main()
