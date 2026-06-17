import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakePatternDb:
    def __init__(self, patterns=None):
        self.patterns = patterns or {}
        self.updated_patterns = []

    async def get_discord_patterns(self):
        return dict(self.patterns)

    async def update_discord_patterns(self, patterns):
        self.updated_patterns.append(patterns)
        self.patterns.update(patterns)


class DiscordPatternValidationTests(unittest.TestCase):
    def test_bulk_pattern_update_rejects_empty_patterns(self):
        from fastapi import HTTPException
        from models import DiscordAlertPatternsUpdate
        from routes import discord as discord_route

        fake_db = FakePatternDb()
        discord_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                discord_route.update_discord_alert_patterns(
                    DiscordAlertPatternsUpdate(buy_patterns=["BUY", "  "])
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("Pattern cannot be empty", caught.exception.detail)
        self.assertEqual(fake_db.updated_patterns, [])

    def test_bulk_pattern_update_rejects_oversized_patterns(self):
        from fastapi import HTTPException
        from models import DiscordAlertPatternsUpdate
        from routes import discord as discord_route

        fake_db = FakePatternDb()
        discord_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                discord_route.update_discord_alert_patterns(
                    DiscordAlertPatternsUpdate(sell_patterns=["X" * 201])
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("Pattern too long", caught.exception.detail)
        self.assertEqual(fake_db.updated_patterns, [])

    def test_bulk_pattern_update_rejects_invalid_ticker_regex(self):
        from fastapi import HTTPException
        from models import DiscordAlertPatternsUpdate
        from routes import discord as discord_route

        fake_db = FakePatternDb()
        discord_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                discord_route.update_discord_alert_patterns(
                    DiscordAlertPatternsUpdate(ticker_pattern="[")
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("Ticker pattern is not valid regex", caught.exception.detail)
        self.assertEqual(fake_db.updated_patterns, [])

    def test_bulk_pattern_update_requires_ticker_capture_group(self):
        from fastapi import HTTPException
        from models import DiscordAlertPatternsUpdate
        from routes import discord as discord_route

        fake_db = FakePatternDb()
        discord_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                discord_route.update_discord_alert_patterns(
                    DiscordAlertPatternsUpdate(ticker_pattern=r"\$[A-Z]{1,5}\b")
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("capture group", caught.exception.detail)
        self.assertEqual(fake_db.updated_patterns, [])

    def test_bulk_pattern_update_rejects_redos_shaped_ticker_regex(self):
        from fastapi import HTTPException
        from models import DiscordAlertPatternsUpdate
        from routes import discord as discord_route

        fake_db = FakePatternDb()
        discord_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                discord_route.update_discord_alert_patterns(
                    DiscordAlertPatternsUpdate(ticker_pattern=r"\$((A+)+)\b")
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("unsafe nested quantifier", caught.exception.detail)
        self.assertEqual(fake_db.updated_patterns, [])


if __name__ == "__main__":
    unittest.main()
