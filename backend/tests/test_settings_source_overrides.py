import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeSettingsDb:
    def __init__(self, settings=None):
        self.settings = settings or {}
        self.updated = []

    async def get_settings(self):
        return dict(self.settings)

    async def update_settings(self, update):
        self.updated.append(update)
        self.settings.update(update)
        return dict(self.settings)


class SourceOverrideRouteTests(unittest.TestCase):
    def test_update_source_overrides_normalizes_before_saving(self):
        from routes import settings as settings_route

        fake_db = FakeSettingsDb()
        settings_route.set_db(fake_db)

        response = asyncio.run(
            settings_route.update_source_overrides(
                {
                    " Alerts ": {
                        "allowed_actions": ["BUY", "Close"],
                        "ticker_allowlist": [" spy ", "$qqq"],
                        "ticker_blocklist": ["tsla"],
                        "risk_multiplier": "0.5",
                        "max_contracts": "3",
                        "require_manual_confirm": True,
                        "paper_shadow": True,
                    }
                }
            )
        )

        self.assertEqual(
            response,
            {
                "Alerts": {
                    "name": "",
                    "enabled": True,
                    "paper_only": False,
                    "parser_format": "default",
                    "max_premium": None,
                    "risk_multiplier": 0.5,
                    "notes": "",
                    "allowed_actions": ["buy", "close"],
                    "ticker_allowlist": ["SPY", "QQQ"],
                    "ticker_blocklist": ["TSLA"],
                    "max_contracts": 3,
                    "require_manual_confirm": True,
                    "paper_shadow": True,
                    "sr_watch_enabled": False,
                    "sr_watch_replace_orb": True,
                    "sr_watch_auto_act": False,
                    "sr_watch_strict_gating": False,
                    "sr_watch_strict_0dte_exits": True,
                    "sr_watch_stop_trading_after_time_enabled": False,
                    "sr_watch_stop_trading_after_time": "15:30",
                    "sr_watch_scale_in_sizing_mode": "buying_power_fraction",
                    "sr_watch_scale_in_fraction": 0.25,
                    "sr_watch_break_even_stop_enabled": False,
                    "sr_watch_pre_close_trailing_enabled": False,
                }
            },
        )
        self.assertEqual(fake_db.updated, [{"source_overrides": response}])

    def test_update_source_overrides_rejects_unknown_actions(self):
        from fastapi import HTTPException
        from routes import settings as settings_route

        settings_route.set_db(FakeSettingsDb())

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                settings_route.update_source_overrides(
                    {"alerts": {"allowed_actions": ["buy", "moon"]}}
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("unknown allowed action", caught.exception.detail)

    def test_update_source_overrides_rejects_invalid_risk_numbers(self):
        from fastapi import HTTPException
        from routes import settings as settings_route

        fake_db = FakeSettingsDb()
        settings_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                settings_route.update_source_overrides(
                    {"alerts": {"max_premium": "-0.01"}}
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("max_premium must be greater than 0", caught.exception.detail)
        self.assertEqual(fake_db.updated, [])

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                settings_route.update_source_overrides(
                    {"alerts": {"risk_multiplier": "0"}}
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("risk_multiplier must be greater than 0", caught.exception.detail)
        self.assertEqual(fake_db.updated, [])

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                settings_route.update_source_overrides(
                    {"alerts": {"max_contracts": "0"}}
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("max_contracts must be greater than 0", caught.exception.detail)
        self.assertEqual(fake_db.updated, [])

    def test_update_source_overrides_rejects_invalid_tickers(self):
        from fastapi import HTTPException
        from routes import settings as settings_route

        fake_db = FakeSettingsDb()
        settings_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                settings_route.update_source_overrides(
                    {"alerts": {"ticker_allowlist": ["SPY1"]}}
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("ticker_allowlist contains invalid ticker", caught.exception.detail)
        self.assertEqual(fake_db.updated, [])


if __name__ == "__main__":
    unittest.main()
