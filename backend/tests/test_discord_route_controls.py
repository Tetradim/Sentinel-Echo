import asyncio
import os
import pathlib
import sys
import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeRawDiscordSettingsDb:
    def __init__(self, settings):
        self.settings = settings

    async def get_settings(self):
        return self.settings


class DiscordRouteControlTests(unittest.TestCase):
    def setUp(self):
        from routes import discord as discord_route

        discord_route.set_discord_bot(None, None)

    def test_start_discord_bot_blocks_malformed_settings_as_unconfigured(self):
        from routes import discord as discord_route

        discord_route.set_db(FakeRawDiscordSettingsDb("settings"))

        with patch.dict(
            os.environ,
            {
                "DISCORD_BOT_TOKEN": "",
                "DISCORD_CHANNEL_IDS": "",
                "SENTINEL_ECHO_USE_OPENCLAW_DISCORD": "false",
            },
            clear=True,
        ):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(discord_route.start_discord_bot(BackgroundTasks()))

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "Discord token not configured")

    def test_discord_connection_reports_malformed_settings_as_not_configured(self):
        from routes import discord as discord_route

        discord_route.set_db(FakeRawDiscordSettingsDb("settings"))

        response = asyncio.run(discord_route.test_discord_connection())

        self.assertEqual(
            response,
            {
                "success": False,
                "status": "not_configured",
                "message": "Discord not configured",
                "details": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
