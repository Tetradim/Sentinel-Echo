import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


READY_SETTINGS = {
    "discord_token": "discord-token",
    "discord_channel_ids": ["123456789"],
    "active_broker": "alpaca",
    "broker_configs": {"alpaca": {"broker_type": "alpaca", "api_key": "key"}},
    "auto_trading_enabled": True,
    "simulation_mode": False,
    "max_position_size": 1000.0,
    "source_overrides": {
        "alerts": {
            "enabled": True,
            "paper_only": False,
            "paper_shadow": False,
            "require_manual_confirm": False,
        }
    },
}


READY_ENV = {
    "API_KEY": "key",
    "CREDENTIAL_KEY": "0" * 64,
    "HOST": "0.0.0.0",
    "USE_SQLITE": "false",
}


class LiveReadinessTests(unittest.TestCase):
    def test_ready_settings_pass_live_readiness(self):
        from live_readiness import evaluate_live_readiness

        result = evaluate_live_readiness(
            READY_SETTINGS,
            {"shutdown_triggered": False},
            status={"broker_connected": True, "discord_connected": True},
            env=READY_ENV,
        )

        self.assertTrue(result["ready_for_live"])
        self.assertEqual(result["blocking_issues"], [])

    def test_readiness_reports_core_blockers(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings.update(
            {
                "auto_trading_enabled": False,
                "simulation_mode": True,
                "active_broker": "ibkr",
                "broker_configs": {},
                "source_overrides": {},
            }
        )
        result = evaluate_live_readiness(
            settings,
            {"shutdown_triggered": True},
            status={"broker_connected": False, "discord_connected": False},
            env={"HOST": "0.0.0.0", "USE_SQLITE": "false"},
        )
        codes = {issue["code"] for issue in result["blocking_issues"]}

        self.assertIn("api_key_missing", codes)
        self.assertIn("credential_key_missing", codes)
        self.assertIn("simulation_mode_enabled", codes)
        self.assertIn("auto_trading_disabled", codes)
        self.assertIn("active_broker_not_configured", codes)
        self.assertIn("no_live_source", codes)
        self.assertIn("runtime_shutdown_active", codes)
        self.assertIn("broker_not_connected", codes)

    def test_authless_local_desktop_mode_does_not_block_readiness_on_api_key(self):
        from live_readiness import evaluate_live_readiness

        env = dict(READY_ENV)
        env.update({"API_KEY": "", "HOST": "127.0.0.1", "USE_SQLITE": "true"})
        result = evaluate_live_readiness(
            READY_SETTINGS,
            {"shutdown_triggered": False},
            status={"broker_connected": True, "discord_connected": True},
            env=env,
        )
        codes = {issue["code"] for issue in result["blocking_issues"]}

        self.assertNotIn("api_key_missing", codes)

    def test_order_status_requirement_is_reported_even_without_broker_config(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings.update(
            {
                "active_broker": "ibkr",
                "broker_configs": {},
                "simulation_mode": False,
                "auto_trading_enabled": True,
            }
        )

        result = evaluate_live_readiness(
            settings,
            {"shutdown_triggered": False},
            status={"broker_connected": False, "discord_connected": False},
            env=READY_ENV,
        )
        codes = {issue["code"] for issue in result["blocking_issues"]}

        self.assertIn("broker_order_status_unsupported", codes)

    def test_live_readiness_blocks_when_no_alert_ingestion_path_is_healthy(self):
        from live_readiness import evaluate_live_readiness

        result = evaluate_live_readiness(
            READY_SETTINGS,
            {"shutdown_triggered": False},
            status={
                "broker_connected": True,
                "discord_connected": False,
                "chrome_bridge_healthy": False,
            },
            env=READY_ENV,
        )
        codes = {issue["code"] for issue in result["blocking_issues"]}

        self.assertIn("no_live_ingestion", codes)
        self.assertFalse(result["ready_for_live"])

    def test_discord_connected_flag_requires_configured_token_and_channel(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings.update({"discord_token": "", "discord_channel_ids": []})
        result = evaluate_live_readiness(
            settings,
            {"shutdown_triggered": False},
            status={
                "broker_connected": True,
                "discord_connected": True,
                "chrome_bridge_healthy": False,
            },
            env=READY_ENV,
        )
        codes = {issue["code"] for issue in result["blocking_issues"]}

        self.assertIn("no_live_ingestion", codes)
        self.assertFalse(result["checks"]["signal_ingestion"]["discord_configured"])
        self.assertFalse(result["ready_for_live"])

    def test_live_readiness_allows_chrome_bridge_as_alert_ingestion_path(self):
        from live_readiness import evaluate_live_readiness

        result = evaluate_live_readiness(
            READY_SETTINGS,
            {"shutdown_triggered": False},
            status={
                "broker_connected": True,
                "discord_connected": False,
                "chrome_bridge_healthy": True,
            },
            env=READY_ENV,
        )
        codes = {issue["code"] for issue in result["blocking_issues"]}

        self.assertNotIn("no_live_ingestion", codes)
        self.assertTrue(result["ready_for_live"])


if __name__ == "__main__":
    unittest.main()
