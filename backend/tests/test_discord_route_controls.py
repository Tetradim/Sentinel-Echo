import asyncio
from concurrent.futures import Future
import os
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeRawDiscordSettingsDb:
    def __init__(self, settings):
        self.settings = settings

    async def get_settings(self):
        return self.settings


class FakeDiscordThread:
    def __init__(self, alive=True):
        self.alive = alive
        self.started = False

    def is_alive(self):
        return self.alive

    def start(self):
        self.started = True
        self.alive = True


class FakeDiscordBot:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


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

    def test_start_discord_bot_restarts_running_bot_when_config_changed(self):
        from routes import discord as discord_route

        old_bot = FakeDiscordBot()
        old_thread = FakeDiscordThread(alive=True)
        discord_route.set_discord_bot(
            old_bot,
            old_thread,
            token="old-token",
            channel_ids=["111"],
        )
        discord_route.set_db(
            FakeRawDiscordSettingsDb(
                {
                    "discord_token": "new-token",
                    "discord_channel_ids": ["222"],
                }
            )
        )
        created_threads = []

        def create_thread(**kwargs):
            created = FakeDiscordThread(alive=False)
            created.target = kwargs["target"]
            created.args = kwargs["args"]
            created.daemon = kwargs["daemon"]
            created_threads.append(created)
            return created

        fake_server = SimpleNamespace(run_discord_bot=lambda *_args: None)
        with patch.dict(sys.modules, {"server": fake_server}):
            with patch.object(discord_route.threading, "Thread", side_effect=create_thread):
                response = asyncio.run(discord_route.start_discord_bot(BackgroundTasks()))

        self.assertEqual(response["message"], "Discord bot restarting with updated configuration...")
        self.assertTrue(old_bot.closed)
        self.assertEqual(len(created_threads), 1)
        self.assertTrue(created_threads[0].started)
        self.assertEqual(created_threads[0].args, ("new-token", ["222"]))

    def test_stop_discord_bot_closes_client_on_registered_runtime_loop(self):
        from routes import discord as discord_route

        old_bot = FakeDiscordBot()
        runtime_loop = object()
        discord_route.set_discord_bot(
            old_bot,
            FakeDiscordThread(alive=True),
            token="token",
            channel_ids=["111"],
            loop=runtime_loop,
        )
        scheduled = []

        def fake_run_coroutine_threadsafe(coro, loop):
            scheduled.append(loop)
            coro.close()
            future = Future()
            future.set_result(None)
            return future

        with patch.object(
            discord_route.asyncio,
            "run_coroutine_threadsafe",
            side_effect=fake_run_coroutine_threadsafe,
        ):
            response = asyncio.run(discord_route.stop_discord_bot())

        self.assertEqual(response["message"], "Discord bot stopped")
        self.assertEqual(scheduled, [runtime_loop])


if __name__ == "__main__":
    unittest.main()
