import asyncio
import pathlib
import sys
import types
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeChromeBridgeDb:
    def __init__(self, settings):
        self.settings = settings
        self.alerts = []

    async def get_settings(self):
        return dict(self.settings)

    async def insert_alert(self, alert):
        self.alerts.append(alert)
        return alert["id"]


class ChromeBridgeRouteTests(unittest.TestCase):
    def setUp(self):
        from routes import discord as discord_route

        discord_route._chrome_bridge_seen_event_ids.clear()
        discord_route._chrome_bridge_seen_event_order.clear()

    def test_chrome_bridge_message_flows_through_discord_ingestion(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {
                        "paper_only": True,
                    }
                },
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-message-1",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
            url="https://discord.com/channels/1/2/3",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "accepted")
        self.assertTrue(result["alert_inserted"])
        self.assertFalse(result["trade_requested"])
        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertEqual(fake_db.alerts[0]["ticker"], "SPY")
        self.assertEqual(fake_db.alerts[0]["raw_message"], "BTO SPY 500C 6/21 @ 1.25")

    def test_chrome_bridge_dedupes_replayed_dom_events(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb({"auto_trading_enabled": False, "source_overrides": {}})
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="same-dom-message",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
        )

        first = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))
        second = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(first["status"], "accepted")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(len(fake_db.alerts), 1)

    def test_chrome_bridge_rejects_non_local_clients_by_default(self):
        from fastapi import HTTPException
        from routes import discord as discord_route

        discord_route.set_db(FakeChromeBridgeDb({}))
        request = types.SimpleNamespace(client=types.SimpleNamespace(host="192.168.1.25"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="remote-message",
            content="BTO SPY 500C 6/21 @ 1.25",
        )

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(caught.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
