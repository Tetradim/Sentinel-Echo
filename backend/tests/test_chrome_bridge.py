import asyncio
import os
import pathlib
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeChromeBridgeDb:
    def __init__(self, settings):
        self.settings = settings
        self.alerts = []
        self.operator_events = []
        self.patterns = {}

    async def get_settings(self):
        return dict(self.settings)

    async def insert_alert(self, alert):
        self.alerts.append(alert)
        return alert["id"]

    async def get_discord_patterns(self):
        return dict(self.patterns)

    async def insert_operator_event(self, event):
        self.operator_events.append(event)
        return event["id"]


class FakeRawChromeBridgeDb(FakeChromeBridgeDb):
    async def get_settings(self):
        return self.settings


class ChromeBridgeRouteTests(unittest.TestCase):
    def setUp(self):
        from routes import discord as discord_route
        import bridge_health

        discord_route._chrome_bridge_seen_event_ids.clear()
        discord_route._chrome_bridge_seen_event_order.clear()
        bridge_health._last_heartbeat = None
        bridge_health._last_attention_key = None
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_capture_dir = os.environ.get("ALERT_CAPTURE_DIR")
        self.old_event_dir = os.environ.get("BOT_EVENT_BUS_DIR")
        os.environ["ALERT_CAPTURE_DIR"] = str(pathlib.Path(self.temp_dir.name) / "captures")
        os.environ["BOT_EVENT_BUS_DIR"] = str(pathlib.Path(self.temp_dir.name) / "events")

    def tearDown(self):
        if self.old_capture_dir is None:
            os.environ.pop("ALERT_CAPTURE_DIR", None)
        else:
            os.environ["ALERT_CAPTURE_DIR"] = self.old_capture_dir
        if self.old_event_dir is None:
            os.environ.pop("BOT_EVENT_BUS_DIR", None)
        else:
            os.environ["BOT_EVENT_BUS_DIR"] = self.old_event_dir
        self.temp_dir.cleanup()

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
        self.assertTrue(pathlib.Path(result["capture_path"]).exists())
        self.assertTrue(result["bus_event_id"])

    def test_chrome_bridge_message_preserves_target_and_channel_metadata(self):
        from routes import discord as discord_route
        import bot_event_bus

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {},
                },
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-message-target-metadata",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            channel_url="https://discord.com/channels/1/chrome-alerts",
            bridge_target_id="consolidation",
            bridge_target_name="Consolidation",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
            url="https://discord.com/channels/1/chrome-alerts/999",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))
        events = bot_event_bus.event_bus.recent(event_type="signal.observed")

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["channel_url"], "https://discord.com/channels/1/chrome-alerts")
        self.assertEqual(result["bridge_target_id"], "consolidation")
        self.assertEqual(events[0]["payload"]["channel_url"], "https://discord.com/channels/1/chrome-alerts")
        self.assertEqual(events[0]["payload"]["bridge_target_id"], "consolidation")
        self.assertEqual(events[0]["payload"]["bridge_target_name"], "Consolidation")
        self.assertEqual(events[0]["payload"]["url"], "https://discord.com/channels/1/chrome-alerts/999")

    def test_chrome_bridge_message_treats_malformed_settings_as_safe_defaults(self):
        from routes import discord as discord_route

        fake_db = FakeRawChromeBridgeDb("settings")
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-message-malformed-settings",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "skipped")
        self.assertFalse(result["alert_inserted"])
        self.assertFalse(result["trade_requested"])
        self.assertEqual(result["skip_reason"], "source override required for chrome bridge")
        self.assertEqual(fake_db.alerts, [])
        self.assertTrue(pathlib.Path(result["capture_path"]).exists())

    def test_chrome_bridge_heartbeat_records_health(self):
        from routes import discord as discord_route

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeHeartbeat(
            status="ok",
            bridge_enabled=True,
            channel_id="chrome-alerts",
            observed_at=datetime.now(timezone.utc).isoformat(),
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_heartbeat(payload, request))

        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["issues"], [])

    def test_chrome_bridge_disabled_heartbeat_is_unhealthy(self):
        from routes import discord as discord_route

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeHeartbeat(
            status="ok",
            bridge_enabled=False,
            channel_id="chrome-extension-service-worker",
            observed_at=datetime.now(timezone.utc).isoformat(),
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_heartbeat(payload, request))

        self.assertEqual(result["status"], "unhealthy")
        self.assertIn("chrome bridge is disabled", result["issues"])

    def test_chrome_bridge_raw_heartbeat_parses_string_disabled_flag(self):
        import bridge_health

        result = bridge_health.record_bridge_heartbeat(
            {
                "status": "ok",
                "bridge_enabled": "false",
                "channel_id": "chrome-extension-service-worker",
                "observed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        self.assertEqual(result["status"], "unhealthy")
        self.assertFalse(result["last_heartbeat"]["bridge_enabled"])
        self.assertIn("chrome bridge is disabled", result["issues"])

    def test_chrome_bridge_dedupes_replayed_dom_events(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {},
                },
            }
        )
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

    def test_chrome_bridge_blocks_low_confidence_alert_before_insert_or_trade(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": True,
                "source_overrides": {
                    "chrome-alerts": {
                        "min_parser_confidence": "medium",
                    }
                },
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-low-confidence",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_id="mike",
            author_name="MikeInvesting",
            content="SPY 500C 6/21 @ 1.25",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "skipped")
        self.assertFalse(result["alert_inserted"])
        self.assertFalse(result["trade_requested"])
        self.assertEqual(result["skip_reason"], "parser confidence low below required medium")
        self.assertEqual(result["parser_metadata"]["confidence"], "low")
        self.assertEqual(fake_db.alerts, [])
        self.assertEqual(fake_db.operator_events[-1]["action"], "bridge_alert_decision")
        self.assertEqual(fake_db.operator_events[-1]["severity"], "warning")
        self.assertEqual(
            fake_db.operator_events[-1]["details"]["decision"]["skip_reason"],
            "parser confidence low below required medium",
        )

    def test_chrome_bridge_requires_source_override_when_strict_policy_is_enabled(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": True,
                "chrome_bridge_require_source_override": True,
                "source_overrides": {},
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-missing-source-policy",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_id="mike",
            author_name="MikeInvesting",
            content="BTO SPY 500C 6/21 @ 1.25",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["skip_reason"], "source override required for chrome bridge")
        self.assertEqual(fake_db.alerts, [])
        self.assertEqual(fake_db.operator_events[-1]["details"]["source"]["override_matched"], False)

    def test_chrome_bridge_blocks_unapproved_channel_url_and_author(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": True,
                "source_overrides": {
                    "chrome-alerts": {
                        "allowed_channel_urls": ["https://discord.com/channels/1/approved"],
                        "allowed_author_ids": ["mike"],
                    }
                },
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-unapproved-source-metadata",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            channel_url="https://discord.com/channels/1/other",
            author_id="other",
            author_name="Other",
            content="BTO SPY 500C 6/21 @ 1.25",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["skip_reason"], "channel URL not allowed for source")
        self.assertEqual(fake_db.alerts, [])
        self.assertEqual(fake_db.operator_events[-1]["details"]["source"]["key"], "chrome-alerts")


if __name__ == "__main__":
    unittest.main()
