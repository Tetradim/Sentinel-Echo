import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeDiagnosticsDb:
    def __init__(self, settings):
        self.settings = settings

    async def get_settings(self):
        return dict(self.settings)


class SetupDiagnosticsTests(unittest.TestCase):
    def test_setup_diagnostics_reports_live_ready_without_exposing_secrets(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "discord-secret-token",
                    "discord_channel_ids": ["123", "456"],
                    "active_broker": "alpaca",
                    "broker_configs": {
                        "alpaca": {
                            "api_key": "broker-secret-key",
                            "api_secret": "broker-secret-secret",
                        }
                    },
                    "source_overrides": {
                        "alerts": {
                            "paper_only": False,
                            "require_manual_confirm": False,
                            "paper_shadow": True,
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "shutdown_triggered": False,
                }
            )
        )

        result = asyncio.run(health_route.setup_diagnostics())

        self.assertTrue(result["ready_for_live"])
        self.assertTrue(result["discord"]["token_configured"])
        self.assertTrue(result["discord"]["message_content_intent_requested"])
        self.assertEqual(result["discord"]["channel_count"], 2)
        self.assertTrue(result["broker"]["configured"])
        self.assertTrue(result["broker"]["order_status_supported"])
        self.assertEqual(result["source_policy"]["override_count"], 1)
        self.assertEqual(result["source_policy"]["paper_shadow_sources"], 1)
        self.assertNotIn("broker-secret", str(result))
        self.assertNotIn("discord-secret", str(result))

    def test_setup_diagnostics_reports_actionable_warnings(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "active_broker": "ibkr",
                    "broker_configs": {"ibkr": {"gateway_url": "http://localhost"}},
                    "source_overrides": {},
                    "auto_trading_enabled": False,
                    "simulation_mode": True,
                    "shutdown_triggered": True,
                }
            )
        )

        result = asyncio.run(health_route.setup_diagnostics())

        self.assertFalse(result["ready_for_live"])
        self.assertFalse(result["discord"]["token_configured"])
        self.assertFalse(result["broker"]["order_status_supported"])
        self.assertIn("Discord token is not configured.", result["warnings"])
        self.assertIn("No source overrides are configured.", result["warnings"])
        self.assertIn(
            "Active broker does not support live fill status polling.",
            result["warnings"],
        )
        self.assertIn("Auto trading is disabled.", result["warnings"])
        self.assertIn("Simulation mode is enabled.", result["warnings"])
        self.assertIn("Runtime shutdown is active.", result["warnings"])

    def test_setup_diagnostics_warns_when_no_source_can_auto_live_trade(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "discord-secret-token",
                    "discord_channel_ids": ["123"],
                    "active_broker": "alpaca",
                    "broker_configs": {
                        "alpaca": {
                            "api_key": "broker-secret-key",
                            "api_secret": "broker-secret-secret",
                        }
                    },
                    "source_overrides": {
                        "paper": {"paper_only": True},
                        "manual": {"require_manual_confirm": True},
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "shutdown_triggered": False,
                }
            )
        )

        result = asyncio.run(health_route.setup_diagnostics())

        self.assertFalse(result["ready_for_live"])
        self.assertEqual(result["source_policy"]["auto_live_sources"], 0)
        self.assertIn(
            "No source override can submit live orders automatically.",
            result["warnings"],
        )


if __name__ == "__main__":
    unittest.main()
