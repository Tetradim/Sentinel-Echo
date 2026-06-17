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


if __name__ == "__main__":
    unittest.main()
