import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


READY_SETTINGS = {
    "discord_token": "discord-token",
    "discord_channel_ids": ["123456789"],
    "active_broker": "alpaca",
    "broker_configs": {"alpaca": {"broker_type": "alpaca", "api_key": "key", "api_secret": "secret"}},
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

    def test_broker_enum_value_is_normalized_for_readiness(self):
        from live_readiness import evaluate_live_readiness
        from models import BrokerType

        settings = dict(READY_SETTINGS)
        settings["active_broker"] = BrokerType.ALPACA

        result = evaluate_live_readiness(
            settings,
            {"shutdown_triggered": False},
            status={"broker_connected": True, "discord_connected": True},
            env=READY_ENV,
        )

        self.assertTrue(result["ready_for_live"])
        self.assertEqual(result["checks"]["broker"]["active_broker"], "alpaca")
        self.assertNotIn("active_broker_not_configured", result["blocking_codes"])

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

    def test_malformed_status_and_runtime_do_not_crash_readiness(self):
        from live_readiness import evaluate_live_readiness

        try:
            result = evaluate_live_readiness(
                READY_SETTINGS,
                "shutdown",
                status="connected",
                env=READY_ENV,
            )
        except AttributeError as exc:
            self.fail(f"readiness should treat malformed status/runtime as empty instead of raising: {exc}")
        codes = {issue["code"] for issue in result["blocking_issues"]}

        self.assertIn("no_live_ingestion", codes)
        self.assertFalse(result["checks"]["runtime"]["shutdown_triggered"])
        self.assertFalse(result["ready_for_live"])

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

    def test_malformed_broker_configs_do_not_count_active_broker_configured(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings["broker_configs"] = "alpaca"

        result = evaluate_live_readiness(
            settings,
            {"shutdown_triggered": False},
            status={"broker_connected": True, "discord_connected": True},
            env=READY_ENV,
        )
        codes = {issue["code"] for issue in result["blocking_issues"]}

        self.assertIn("active_broker_not_configured", codes)
        self.assertFalse(result["checks"]["broker"]["configured"])
        self.assertFalse(result["ready_for_live"])

    def test_empty_active_broker_config_does_not_count_configured(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings["broker_configs"] = {"alpaca": {}}

        result = evaluate_live_readiness(
            settings,
            {"shutdown_triggered": False},
            status={"broker_connected": True, "discord_connected": True},
            env=READY_ENV,
        )

        self.assertIn("active_broker_not_configured", result["blocking_codes"])
        self.assertFalse(result["checks"]["broker"]["configured"])
        self.assertFalse(result["ready_for_live"])

    def test_blank_active_broker_config_does_not_count_configured(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings["broker_configs"] = {"alpaca": {"api_key": "  ", "api_secret": ""}}

        result = evaluate_live_readiness(
            settings,
            {"shutdown_triggered": False},
            status={"broker_connected": True, "discord_connected": True},
            env=READY_ENV,
        )

        self.assertIn("active_broker_not_configured", result["blocking_codes"])
        self.assertFalse(result["checks"]["broker"]["configured"])
        self.assertFalse(result["ready_for_live"])

    def test_incomplete_active_broker_config_does_not_count_configured(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings["broker_configs"] = {
            "alpaca": {
                "broker_type": "alpaca",
                "api_key": "key",
                "base_url": "https://paper-api.alpaca.markets",
            }
        }

        result = evaluate_live_readiness(
            settings,
            {"shutdown_triggered": False},
            status={"broker_connected": True, "discord_connected": True},
            env=READY_ENV,
        )

        self.assertIn("active_broker_not_configured", result["blocking_codes"])
        self.assertFalse(result["checks"]["broker"]["configured"])
        self.assertEqual(result["checks"]["broker"]["missing_required_fields"], ["api_secret"])
        self.assertTrue(
            any(
                issue["code"] == "active_broker_not_configured"
                and "api_secret" in issue["summary"]
                for issue in result["blocking_issues"]
            )
        )
        self.assertNotIn("key", str(result["blocking_issues"]))
        self.assertFalse(result["ready_for_live"])

    def test_malformed_source_overrides_report_invalid_policy_without_crashing(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings["source_overrides"] = "alerts"

        try:
            result = evaluate_live_readiness(
                settings,
                {"shutdown_triggered": False},
                status={"broker_connected": True, "discord_connected": True},
                env=READY_ENV,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            self.fail(f"readiness should report malformed source_overrides instead of raising: {exc}")
        codes = {issue["code"] for issue in result["blocking_issues"]}

        self.assertIn("source_policy_invalid", codes)
        self.assertFalse(result["checks"]["source_policy"]["valid"])
        self.assertFalse(result["ready_for_live"])

    def test_source_policy_check_reports_blocked_source_reasons(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings["source_overrides"] = {
            "paper": {"paper_only": True},
            "manual": {"require_manual_confirm": True},
            "disabled": {"enabled": False},
        }

        result = evaluate_live_readiness(
            settings,
            {"shutdown_triggered": False},
            status={"broker_connected": True, "discord_connected": True},
            env=READY_ENV,
        )
        source_policy = result["checks"]["source_policy"]
        blocked = {item["key"]: item["reasons"] for item in source_policy["blocked_sources"]}

        self.assertIn("no_live_source", result["blocking_codes"])
        self.assertEqual(source_policy["override_count"], 3)
        self.assertEqual(source_policy["auto_live_sources"], 0)
        self.assertEqual(source_policy["paper_only_sources"], 1)
        self.assertEqual(source_policy["manual_confirm_sources"], 1)
        self.assertEqual(source_policy["disabled_sources"], 1)
        self.assertEqual(blocked["paper"], ["paper_only"])
        self.assertEqual(blocked["manual"], ["manual_confirm_required"])
        self.assertEqual(blocked["disabled"], ["disabled"])

    def test_invalid_max_position_size_reports_blocker_without_crashing(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings["max_position_size"] = "not-a-number"

        try:
            result = evaluate_live_readiness(
                settings,
                {"shutdown_triggered": False},
                status={"broker_connected": True, "discord_connected": True},
                env=READY_ENV,
            )
        except (TypeError, ValueError) as exc:
            self.fail(f"readiness should report invalid max_position_size instead of raising: {exc}")
        codes = {issue["code"] for issue in result["blocking_issues"]}

        self.assertIn("max_position_size_invalid", codes)
        self.assertFalse(result["ready_for_live"])

    def test_nonfinite_max_position_size_reports_blocker(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings["max_position_size"] = "inf"

        result = evaluate_live_readiness(
            settings,
            {"shutdown_triggered": False},
            status={"broker_connected": True, "discord_connected": True},
            env=READY_ENV,
        )
        codes = {issue["code"] for issue in result["blocking_issues"]}

        self.assertIn("max_position_size_invalid", codes)
        self.assertFalse(result["checks"]["trading"]["max_position_size_valid"])
        self.assertFalse(result["ready_for_live"])

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

    def test_malformed_status_channel_count_does_not_crash_or_configure_discord(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings.update({"discord_token": "", "discord_channel_ids": []})

        try:
            result = evaluate_live_readiness(
                settings,
                {"shutdown_triggered": False},
                status={
                    "broker_connected": True,
                    "discord_connected": True,
                    "discord_token_configured": True,
                    "discord_channel_count": "not-a-number",
                    "chrome_bridge_healthy": False,
                },
                env=READY_ENV,
            )
        except (TypeError, ValueError) as exc:
            self.fail(f"readiness should treat malformed channel counts as zero instead of raising: {exc}")
        codes = {issue["code"] for issue in result["blocking_issues"]}
        signal = result["checks"]["signal_ingestion"]

        self.assertEqual(signal["discord_channel_count"], 0)
        self.assertFalse(signal["discord_configured"])
        self.assertIn("no_live_ingestion", codes)
        self.assertFalse(result["ready_for_live"])

    def test_malformed_saved_channel_ids_do_not_crash_or_configure_discord(self):
        from live_readiness import evaluate_live_readiness

        settings = dict(READY_SETTINGS)
        settings.update({"discord_token": "discord-token", "discord_channel_ids": 12345})

        try:
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
        except TypeError as exc:
            self.fail(f"readiness should treat malformed saved channel ids as empty instead of raising: {exc}")
        codes = {issue["code"] for issue in result["blocking_issues"]}
        signal = result["checks"]["signal_ingestion"]

        self.assertEqual(signal["discord_channel_count"], 0)
        self.assertFalse(signal["discord_configured"])
        self.assertIn("no_live_ingestion", codes)
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
