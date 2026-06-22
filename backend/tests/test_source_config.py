import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class SourceConfigTests(unittest.TestCase):
    def test_channel_id_override_forces_paper_and_caps_premium(self):
        from source_config import resolve_source_config, source_skip_reason

        settings = {
            "source_overrides": {
                "123": {
                    "name": "Wizard",
                    "enabled": True,
                    "paper_only": True,
                    "max_premium": 2.0,
                    "parser_format": "wizard",
                }
            }
        }

        config = resolve_source_config(settings, channel_id="123", channel_name="alerts")

        self.assertTrue(config["paper_only"])
        self.assertEqual(config["name"], "Wizard")
        self.assertEqual(config["parser_format"], "wizard")
        self.assertEqual(
            source_skip_reason({"alert_type": "buy", "entry_price": 2.25}, config),
            "premium 2.25 exceeds source max 2.00",
        )

    def test_missing_source_uses_safe_defaults(self):
        from source_config import resolve_source_config, source_skip_reason

        config = resolve_source_config({}, channel_id="999", channel_name="unknown")

        self.assertTrue(config["enabled"])
        self.assertFalse(config["paper_only"])
        self.assertIsNone(source_skip_reason({"alert_type": "buy", "entry_price": 1.0}, config))

    def test_disabled_source_skips_every_alert(self):
        from source_config import resolve_source_config, source_skip_reason

        settings = {"source_overrides": {"alerts": {"enabled": False}}}
        config = resolve_source_config(settings, channel_id="999", channel_name="alerts")

        self.assertEqual(
            source_skip_reason({"alert_type": "sell", "entry_price": 1.0}, config),
            "source disabled",
        )

    def test_manual_confirmation_source_allows_insert_but_blocks_auto_request(self):
        from source_config import resolve_source_config, source_skip_reason

        settings = {"source_overrides": {"alerts": {"require_manual_confirm": True}}}
        config = resolve_source_config(settings, channel_id="999", channel_name="alerts")

        self.assertTrue(config["require_manual_confirm"])
        self.assertIsNone(
            source_skip_reason({"alert_type": "buy", "ticker": "SPY", "entry_price": 1.0}, config)
        )

    def test_paper_shadow_source_normalizes_without_blocking_alerts(self):
        from source_config import resolve_source_config, source_skip_reason

        settings = {"source_overrides": {"alerts": {"paper_shadow": True}}}
        config = resolve_source_config(settings, channel_id="999", channel_name="alerts")

        self.assertTrue(config["paper_shadow"])
        self.assertIsNone(
            source_skip_reason({"alert_type": "buy", "ticker": "SPY", "entry_price": 1.0}, config)
        )

    def test_source_policy_summary_reports_auto_live_blockers(self):
        from source_config import summarize_source_policy

        summary = summarize_source_policy(
            {
                "paper": {"name": "Paper Alerts", "paper_only": True},
                "manual": {"require_manual_confirm": True},
                "disabled": {"enabled": False, "paper_shadow": True},
                "live": {"paper_shadow": True},
            }
        )

        self.assertTrue(summary["valid"])
        self.assertEqual(summary["override_count"], 4)
        self.assertEqual(summary["enabled_sources"], 3)
        self.assertEqual(summary["disabled_sources"], 1)
        self.assertEqual(summary["paper_only_sources"], 1)
        self.assertEqual(summary["paper_shadow_sources"], 2)
        self.assertEqual(summary["manual_confirm_sources"], 1)
        self.assertEqual(summary["auto_live_sources"], 1)
        self.assertEqual(summary["auto_live_source_keys"], ["live"])

        blocked = {item["key"]: item for item in summary["blocked_sources"]}
        self.assertEqual(blocked["paper"]["name"], "Paper Alerts")
        self.assertEqual(blocked["paper"]["reasons"], ["paper_only"])
        self.assertEqual(blocked["manual"]["reasons"], ["manual_confirm_required"])
        self.assertEqual(blocked["disabled"]["reasons"], ["disabled"])

    def test_source_policy_summary_reports_invalid_overrides_without_crashing(self):
        from source_config import summarize_source_policy

        summary = summarize_source_policy("alerts")

        self.assertFalse(summary["valid"])
        self.assertEqual(summary["error"], "source overrides must be an object")
        self.assertEqual(summary["override_count"], 0)
        self.assertEqual(summary["auto_live_sources"], 0)
        self.assertEqual(summary["blocked_sources"], [])

    def test_allowed_actions_block_unapproved_lifecycle_alerts(self):
        from source_config import resolve_source_config, source_skip_reason

        settings = {
            "source_overrides": {
                "alerts": {
                    "allowed_actions": ["buy", "average_down"],
                }
            }
        }
        config = resolve_source_config(settings, channel_id="999", channel_name="alerts")

        self.assertEqual(config["allowed_actions"], ["buy", "average_down"])
        self.assertEqual(
            source_skip_reason({"alert_type": "sell", "ticker": "SPY"}, config),
            "action sell not allowed for source",
        )
        self.assertIsNone(
            source_skip_reason({"alert_type": "buy", "ticker": "SPY", "entry_price": 1.0}, config)
        )

    def test_ticker_allowlist_and_blocklist_are_enforced(self):
        from source_config import resolve_source_config, source_skip_reason

        settings = {
            "source_overrides": {
                "alerts": {
                    "ticker_allowlist": ["SPY", "QQQ"],
                    "ticker_blocklist": ["TSLA"],
                }
            }
        }
        config = resolve_source_config(settings, channel_id="999", channel_name="alerts")

        self.assertEqual(config["ticker_allowlist"], ["SPY", "QQQ"])
        self.assertEqual(config["ticker_blocklist"], ["TSLA"])
        self.assertEqual(
            source_skip_reason({"alert_type": "buy", "ticker": "AAPL", "entry_price": 1.0}, config),
            "ticker AAPL not allowed for source",
        )
        self.assertEqual(
            source_skip_reason({"alert_type": "buy", "ticker": "TSLA", "entry_price": 1.0}, config),
            "ticker TSLA blocked for source",
        )
        self.assertIsNone(
            source_skip_reason({"alert_type": "buy", "ticker": "SPY", "entry_price": 1.0}, config)
        )

    def test_normalize_source_overrides_rejects_unknown_actions(self):
        from source_config import normalize_source_overrides

        with self.assertRaisesRegex(ValueError, "unknown allowed action"):
            normalize_source_overrides({"alerts": {"allowed_actions": ["moon"]}})

    def test_normalize_source_overrides_rejects_invalid_risk_numbers(self):
        from source_config import normalize_source_overrides

        with self.assertRaisesRegex(ValueError, "max_premium must be greater than 0"):
            normalize_source_overrides({"alerts": {"max_premium": -1}})

        with self.assertRaisesRegex(ValueError, "risk_multiplier must be greater than 0"):
            normalize_source_overrides({"alerts": {"risk_multiplier": 0}})

    def test_max_contracts_caps_source_quantity(self):
        from source_config import apply_source_quantity_limits, resolve_source_config

        settings = {"source_overrides": {"alerts": {"max_contracts": "2"}}}
        config = resolve_source_config(settings, channel_id="999", channel_name="alerts")

        self.assertEqual(config["max_contracts"], 2)
        self.assertEqual(apply_source_quantity_limits(5, config), 2)
        self.assertEqual(apply_source_quantity_limits(1, config), 1)
        self.assertEqual(apply_source_quantity_limits(0, config), 0)

    def test_normalize_source_overrides_rejects_invalid_max_contracts(self):
        from source_config import normalize_source_overrides

        with self.assertRaisesRegex(ValueError, "max_contracts must be greater than 0"):
            normalize_source_overrides({"alerts": {"max_contracts": 0}})

    def test_normalize_source_overrides_rejects_invalid_tickers(self):
        from source_config import normalize_source_overrides

        with self.assertRaisesRegex(ValueError, "ticker_allowlist contains invalid ticker"):
            normalize_source_overrides({"alerts": {"ticker_allowlist": ["SPY1"]}})

        with self.assertRaisesRegex(ValueError, "ticker_blocklist contains invalid ticker"):
            normalize_source_overrides({"alerts": {"ticker_blocklist": ["BAD TICKER"]}})


if __name__ == "__main__":
    unittest.main()
