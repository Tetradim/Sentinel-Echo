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


if __name__ == "__main__":
    unittest.main()
