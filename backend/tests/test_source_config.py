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


if __name__ == "__main__":
    unittest.main()
