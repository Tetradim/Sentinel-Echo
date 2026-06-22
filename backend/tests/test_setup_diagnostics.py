import asyncio
import pathlib
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeDiagnosticsDb:
    def __init__(self, settings):
        self.settings = settings

    async def get_settings(self):
        return dict(self.settings)

    async def get_runtime_state(self):
        return {"shutdown_triggered": False, "shutdown_reason": ""}


class FakeRawDiagnosticsDb:
    def __init__(self, settings, runtime_state):
        self.settings = settings
        self.runtime_state = runtime_state

    async def get_settings(self):
        return self.settings

    async def get_runtime_state(self):
        return self.runtime_state


class SetupDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        from routes import health as health_route
        import bridge_health

        health_route.update_bot_status("discord_connected", False)
        health_route.update_bot_status("broker_connected", False)
        bridge_health._last_heartbeat = None
        bridge_health._last_attention_key = None

    def test_update_bot_status_ignores_unknown_status_keys(self):
        from routes import health as health_route

        health_route.update_bot_status("live_trading_armed", True)

        self.assertNotIn("live_trading_armed", health_route.get_bot_status())

    def test_readiness_warning_merge_ignores_malformed_issues(self):
        from routes import health as health_route

        result = health_route._merge_readiness_warnings(
            ["Existing warning"],
            {
                "blocking_issues": [
                    "blocked",
                    {"summary": "Existing warning"},
                    {"summary": "Valid readiness warning"},
                ]
            },
        )

        self.assertEqual(result, ["Existing warning", "Valid readiness warning"])

    def test_readiness_warning_merge_treats_malformed_readiness_as_empty(self):
        from routes import health as health_route

        result = health_route._merge_readiness_warnings(["Existing warning"], "readiness")

        self.assertEqual(result, ["Existing warning"])

    def test_status_derives_trading_state_from_settings(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "active_broker": "tradier",
                    "auto_trading_enabled": True,
                    "simulation_mode": True,
                }
            )
        )
        health_route.update_bot_status("auto_trading_enabled", False)
        health_route.update_bot_status("simulation_mode", False)

        result = asyncio.run(health_route.get_status())

        self.assertEqual(result["active_broker"], "tradier")
        self.assertTrue(result["auto_trading_enabled"])
        self.assertTrue(result["simulation_mode"])

    def test_status_treats_malformed_db_state_as_empty(self):
        from routes import health as health_route

        health_route.set_db(FakeRawDiagnosticsDb("settings", "runtime"))
        health_route.update_bot_status("active_broker", "ibkr")
        health_route.update_bot_status("auto_trading_enabled", False)
        health_route.update_bot_status("simulation_mode", True)

        try:
            result = asyncio.run(health_route.get_status())
        except AttributeError as exc:
            self.fail(f"status should treat malformed db state as empty instead of raising: {exc}")

        self.assertEqual(result["active_broker"], "ibkr")
        self.assertFalse(result["auto_trading_enabled"])
        self.assertTrue(result["simulation_mode"])
        self.assertFalse(result["shutdown_triggered"])
        self.assertEqual(result["shutdown_reason"], "")

    def test_status_does_not_report_stale_discord_connected_without_config(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "",
                    "discord_channel_ids": [],
                    "active_broker": "alpaca",
                    "broker_configs": {"alpaca": {"api_key": "broker-secret-key", "api_secret": "broker-secret-secret"}},
                    "source_overrides": {},
                }
            )
        )
        health_route.update_bot_status("discord_connected", True)

        with patch.dict(
            "os.environ",
            {"DISCORD_BOT_TOKEN": "", "DISCORD_CHANNEL_IDS": ""},
        ):
            result = asyncio.run(health_route.get_status())

        self.assertFalse(result["discord_connected"])

    def test_health_degrades_stale_discord_connected_without_config(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "",
                    "discord_channel_ids": [],
                    "active_broker": "alpaca",
                    "broker_configs": {"alpaca": {"api_key": "broker-secret-key", "api_secret": "broker-secret-secret"}},
                    "source_overrides": {},
                }
            )
        )
        health_route.update_bot_status("discord_connected", True)
        health_route.update_bot_status("broker_connected", True)

        with patch.dict(
            "os.environ",
            {"DISCORD_BOT_TOKEN": "", "DISCORD_CHANNEL_IDS": ""},
        ):
            result = asyncio.run(health_route.health())

        self.assertEqual(result["status"], "degraded")
        self.assertFalse(result["discord_connected"])
        self.assertTrue(result["broker_connected"])

    def test_health_does_not_report_unconfigured_broker_connected(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "discord-secret-token",
                    "discord_channel_ids": ["123"],
                    "active_broker": "alpaca",
                    "broker_configs": {},
                    "source_overrides": {
                        "alerts": {
                            "paper_only": False,
                            "require_manual_confirm": False,
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "max_position_size": 1000.0,
                }
            )
        )
        health_route.update_bot_status("discord_connected", True)
        health_route.update_bot_status("broker_connected", True)

        result = asyncio.run(health_route.health())

        self.assertEqual(result["status"], "degraded")
        self.assertTrue(result["discord_connected"])
        self.assertFalse(result["broker_connected"])

    def test_setup_diagnostics_ready_for_live_uses_shared_readiness_result(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "discord-secret-token",
                    "discord_channel_ids": ["123", "456"],
                    "active_broker": "alpaca",
                    "broker_configs": {"alpaca": {"api_key": "broker-secret-key", "api_secret": "broker-secret-secret"}},
                    "source_overrides": {
                        "alerts": {
                            "paper_only": False,
                            "require_manual_confirm": False,
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "max_position_size": 1000.0,
                    "shutdown_triggered": False,
                }
            )
        )

        result = asyncio.run(health_route.setup_diagnostics())

        self.assertFalse(result["readiness"]["ready_for_live"])
        self.assertFalse(result["ready_for_live"])
        self.assertIn("credential_key_missing", result["readiness"]["blocking_codes"])

    def test_setup_diagnostics_treats_malformed_db_state_as_empty(self):
        from routes import health as health_route

        health_route.set_db(FakeRawDiagnosticsDb("settings", "runtime"))

        try:
            result = asyncio.run(health_route.setup_diagnostics())
        except AttributeError as exc:
            self.fail(f"setup diagnostics should treat malformed db state as empty instead of raising: {exc}")

        self.assertFalse(result["ready_for_live"])
        self.assertEqual(result["broker"]["active_broker"], "ibkr")
        self.assertFalse(result["broker"]["configured"])
        self.assertIn("Discord token is not configured.", result["warnings"])

    def test_setup_diagnostics_uses_healthy_chrome_bridge_as_ingestion_path(self):
        from routes import health as health_route
        import bridge_health

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "",
                    "discord_channel_ids": [],
                    "active_broker": "alpaca",
                    "broker_configs": {"alpaca": {"api_key": "broker-secret-key", "api_secret": "broker-secret-secret"}},
                    "source_overrides": {
                        "chrome-alerts": {
                            "paper_only": False,
                            "require_manual_confirm": False,
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "max_position_size": 1000.0,
                    "shutdown_triggered": False,
                }
            )
        )
        health_route.update_bot_status("broker_connected", True)
        bridge_health._last_heartbeat = {
            "status": "ok",
            "bridge_enabled": True,
            "url": "https://discord.com/channels/1/2",
            "channel_id": "chrome-alerts",
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "last_forward_at": "",
            "last_forward_status": "",
            "details": {},
        }

        with patch.dict(
            "os.environ",
            {
                "API_KEY": "api-key",
                "CREDENTIAL_KEY": "0" * 64,
                "DISCORD_BOT_TOKEN": "",
                "DISCORD_CHANNEL_IDS": "",
            },
        ):
            result = asyncio.run(health_route.setup_diagnostics())

        self.assertFalse(result["discord"]["connected"])
        self.assertTrue(result["readiness"]["checks"]["signal_ingestion"]["chrome_bridge_healthy"])
        self.assertNotIn("no_live_ingestion", result["readiness"]["blocking_codes"])

    def test_setup_diagnostics_normalizes_broker_enum_value(self):
        from models import BrokerType
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "discord-secret-token",
                    "discord_channel_ids": ["123", "456"],
                    "active_broker": BrokerType.ALPACA,
                    "broker_configs": {"alpaca": {"api_key": "broker-secret-key", "api_secret": "broker-secret-secret"}},
                    "source_overrides": {
                        "alerts": {
                            "paper_only": False,
                            "require_manual_confirm": False,
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "max_position_size": 1000.0,
                    "shutdown_triggered": False,
                }
            )
        )
        health_route.update_bot_status("discord_connected", True)
        health_route.update_bot_status("broker_connected", True)

        with patch.dict(
            "os.environ",
            {
                "API_KEY": "api-key",
                "CREDENTIAL_KEY": "0" * 64,
            },
        ):
            result = asyncio.run(health_route.setup_diagnostics())

        self.assertEqual(result["broker"]["active_broker"], "alpaca")
        self.assertTrue(result["broker"]["configured"])
        self.assertTrue(result["broker"]["order_status_supported"])
        self.assertNotIn("active_broker_not_configured", result["readiness"]["blocking_codes"])

    def test_setup_diagnostics_warnings_include_shared_readiness_blockers(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "discord-secret-token",
                    "discord_channel_ids": ["123"],
                    "active_broker": "alpaca",
                    "broker_configs": {"alpaca": {"api_key": "broker-secret-key", "api_secret": "broker-secret-secret"}},
                    "source_overrides": {
                        "alerts": {
                            "paper_only": False,
                            "require_manual_confirm": False,
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "max_position_size": 1000.0,
                    "shutdown_triggered": False,
                }
            )
        )
        health_route.update_bot_status("discord_connected", True)
        health_route.update_bot_status("broker_connected", False)

        result = asyncio.run(health_route.setup_diagnostics())

        self.assertIn(
            "CREDENTIAL_KEY is required so broker secrets are encrypted.",
            result["warnings"],
        )
        self.assertIn("Broker connection is not healthy.", result["warnings"])

    def test_setup_diagnostics_does_not_report_stale_discord_connected_without_config(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "",
                    "discord_channel_ids": [],
                    "active_broker": "alpaca",
                    "broker_configs": {"alpaca": {"api_key": "broker-secret-key", "api_secret": "broker-secret-secret"}},
                    "source_overrides": {
                        "alerts": {
                            "paper_only": False,
                            "require_manual_confirm": False,
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "max_position_size": 1000.0,
                    "shutdown_triggered": False,
                }
            )
        )
        health_route.update_bot_status("discord_connected", True)
        health_route.update_bot_status("broker_connected", True)

        with patch.dict(
            "os.environ",
            {"DISCORD_BOT_TOKEN": "", "DISCORD_CHANNEL_IDS": ""},
        ):
            result = asyncio.run(health_route.setup_diagnostics())

        self.assertFalse(result["discord"]["token_configured"])
        self.assertFalse(result["discord"]["connected"])
        self.assertEqual(result["discord"]["channel_count"], 0)
        self.assertIn("no_live_ingestion", result["readiness"]["blocking_codes"])

    def test_setup_diagnostics_reports_environment_discord_configuration(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "",
                    "discord_channel_ids": [],
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
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "max_position_size": 1000.0,
                    "shutdown_triggered": False,
                }
            )
        )
        health_route.update_bot_status("discord_connected", True)
        health_route.update_bot_status("broker_connected", True)

        with patch.dict(
            "os.environ",
            {
                "API_KEY": "api-key",
                "CREDENTIAL_KEY": "0" * 64,
                "DISCORD_BOT_TOKEN": "environment-discord-secret",
                "DISCORD_CHANNEL_IDS": "123,456",
                "HOST": "0.0.0.0",
                "USE_SQLITE": "false",
            },
        ):
            result = asyncio.run(health_route.setup_diagnostics())

        self.assertTrue(result["discord"]["token_configured"])
        self.assertTrue(result["discord"]["connected"])
        self.assertEqual(result["discord"]["channel_count"], 2)
        self.assertNotIn("environment-discord-secret", str(result))

    def test_setup_diagnostics_does_not_count_malformed_broker_configs(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "discord-secret-token",
                    "discord_channel_ids": ["123"],
                    "active_broker": "alpaca",
                    "broker_configs": "alpaca",
                    "source_overrides": {
                        "alerts": {
                            "paper_only": False,
                            "require_manual_confirm": False,
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "max_position_size": 1000.0,
                    "shutdown_triggered": False,
                }
            )
        )
        health_route.update_bot_status("discord_connected", True)
        health_route.update_bot_status("broker_connected", True)

        result = asyncio.run(health_route.setup_diagnostics())

        self.assertFalse(result["broker"]["configured"])
        self.assertFalse(result["broker"]["connected"])
        self.assertFalse(result["broker"]["order_status_supported"])
        self.assertIn("active_broker_not_configured", result["readiness"]["blocking_codes"])
        self.assertIn("Active broker is not configured.", result["warnings"])

    def test_setup_diagnostics_does_not_count_empty_active_broker_config(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "discord-secret-token",
                    "discord_channel_ids": ["123"],
                    "active_broker": "alpaca",
                    "broker_configs": {"alpaca": {}},
                    "source_overrides": {
                        "alerts": {
                            "paper_only": False,
                            "require_manual_confirm": False,
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "max_position_size": 1000.0,
                    "shutdown_triggered": False,
                }
            )
        )
        health_route.update_bot_status("discord_connected", True)
        health_route.update_bot_status("broker_connected", True)

        result = asyncio.run(health_route.setup_diagnostics())

        self.assertFalse(result["broker"]["configured"])
        self.assertFalse(result["broker"]["connected"])
        self.assertFalse(result["broker"]["order_status_supported"])
        self.assertIn("active_broker_not_configured", result["readiness"]["blocking_codes"])
        self.assertIn("Active broker is not configured.", result["warnings"])

    def test_setup_diagnostics_does_not_count_incomplete_active_broker_config(self):
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
                            "base_url": "https://paper-api.alpaca.markets",
                        }
                    },
                    "source_overrides": {
                        "alerts": {
                            "paper_only": False,
                            "require_manual_confirm": False,
                        }
                    },
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "max_position_size": 1000.0,
                    "shutdown_triggered": False,
                }
            )
        )
        health_route.update_bot_status("discord_connected", True)
        health_route.update_bot_status("broker_connected", True)

        result = asyncio.run(health_route.setup_diagnostics())

        self.assertFalse(result["broker"]["configured"])
        self.assertFalse(result["broker"]["connected"])
        self.assertFalse(result["broker"]["order_status_supported"])
        self.assertEqual(result["broker"]["missing_required_fields"], ["api_secret"])
        self.assertEqual(
            result["readiness"]["checks"]["broker"]["missing_required_fields"],
            ["api_secret"],
        )
        self.assertIn("active_broker_not_configured", result["readiness"]["blocking_codes"])
        self.assertIn(
            "Active broker config is missing required fields: api_secret.",
            result["warnings"],
        )
        self.assertNotIn("broker-secret-key", str(result))

    def test_setup_diagnostics_reports_malformed_source_overrides(self):
        from routes import health as health_route

        health_route.set_db(
            FakeDiagnosticsDb(
                {
                    "discord_token": "discord-secret-token",
                    "discord_channel_ids": ["123"],
                    "active_broker": "alpaca",
                    "broker_configs": {"alpaca": {"api_key": "broker-secret-key", "api_secret": "broker-secret-secret"}},
                    "source_overrides": "alerts",
                    "auto_trading_enabled": True,
                    "simulation_mode": False,
                    "max_position_size": 1000.0,
                    "shutdown_triggered": False,
                }
            )
        )
        health_route.update_bot_status("discord_connected", True)
        health_route.update_bot_status("broker_connected", True)

        try:
            result = asyncio.run(health_route.setup_diagnostics())
        except (AttributeError, TypeError, ValueError) as exc:
            self.fail(f"setup diagnostics should report malformed source_overrides instead of raising: {exc}")

        self.assertFalse(result["source_policy"]["valid"])
        self.assertIn("source_policy_invalid", result["readiness"]["blocking_codes"])
        self.assertTrue(
            any(warning.startswith("Source overrides are invalid:") for warning in result["warnings"])
        )

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
                    "max_position_size": 1000.0,
                    "shutdown_triggered": False,
                }
            )
        )
        health_route.update_bot_status("discord_connected", True)
        health_route.update_bot_status("broker_connected", True)

        with patch.dict(
            "os.environ",
            {
                "API_KEY": "api-key",
                "CREDENTIAL_KEY": "0" * 64,
                "HOST": "0.0.0.0",
                "USE_SQLITE": "false",
            },
        ):
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
                    "broker_configs": {"ibkr": {"gateway_url": "http://localhost", "account_id": "DU123456"}},
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
