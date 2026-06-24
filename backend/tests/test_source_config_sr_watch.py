import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class SourceConfigSrWatchTests(unittest.TestCase):
    def test_sr_watch_defaults_are_safe(self):
        from source_config import resolve_source_config

        config = resolve_source_config({}, channel_id="123", channel_name="alerts")

        self.assertFalse(config["sr_watch_enabled"])
        self.assertFalse(config["sr_watch_auto_act"])
        self.assertTrue(config["sr_watch_replace_orb"])
        self.assertFalse(config["sr_watch_stop_trading_after_time_enabled"])
        self.assertTrue(config["sr_watch_strict_0dte_exits"])

    def test_sr_watch_override_can_replace_orb_for_channel(self):
        from source_config import resolve_source_config

        settings = {
            "source_overrides": {
                "alerts": {
                    "sr_watch_enabled": True,
                    "sr_watch_replace_orb": True,
                    "sr_watch_strict_gating": True,
                    "sr_watch_stop_trading_after_time_enabled": True,
                    "sr_watch_stop_trading_after_time": "15:15",
                }
            }
        }

        config = resolve_source_config(settings, channel_id="999", channel_name="alerts")

        self.assertTrue(config["sr_watch_enabled"])
        self.assertTrue(config["sr_watch_replace_orb"])
        self.assertTrue(config["sr_watch_strict_gating"])
        self.assertTrue(config["sr_watch_stop_trading_after_time_enabled"])
        self.assertEqual(config["sr_watch_stop_trading_after_time"], "15:15")

    def test_sr_watch_uses_buying_power_scale_in_by_default(self):
        from source_config import resolve_source_config

        config = resolve_source_config(
            {"source_overrides": {"alerts": {"sr_watch_enabled": True}}},
            channel_id="999",
            channel_name="alerts",
        )

        self.assertEqual(config["sr_watch_scale_in_sizing_mode"], "buying_power_fraction")
        self.assertEqual(config["sr_watch_scale_in_fraction"], 0.25)


if __name__ == "__main__":
    unittest.main()
