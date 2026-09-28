import asyncio
import os
import pathlib
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeChromeBridgeDb:
    def __init__(self, settings):
        self.settings = settings
        self.alerts = []
        self.alert_updates = []
        self.operator_events = []
        self.patterns = {}
        self.positions = []
        self.position_updates = []

    async def get_settings(self):
        return dict(self.settings)

    async def update_settings(self, updates):
        self.settings.update(updates)
        return dict(self.settings)

    async def insert_alert(self, alert):
        self.alerts.append(alert)
        return alert["id"]

    async def update_alert(self, alert_id, updates):
        self.alert_updates.append((alert_id, updates))
        for alert in self.alerts:
            if alert["id"] == alert_id:
                alert.update(updates)

    async def get_discord_patterns(self):
        return dict(self.patterns)

    async def insert_operator_event(self, event):
        self.operator_events.append(event)
        return event["id"]

    async def get_operator_events(self, limit=100):
        return list(reversed(self.operator_events))[:limit]

    async def get_positions(self, status=None):
        return [position for position in self.positions if status is None or position.get("status") == status]

    async def get_alerts(self, limit=50):
        return list(reversed(self.alerts))[:limit]

    async def update_position(self, position_id, updates):
        self.position_updates.append((position_id, updates))
        for position in self.positions:
            if position.get("id") == position_id:
                if "$set" in updates:
                    position.update(updates["$set"])
                else:
                    position.update(updates)


class FakeRawChromeBridgeDb(FakeChromeBridgeDb):
    async def get_settings(self):
        return self.settings


class ChromeBridgeRouteTests(unittest.TestCase):
    def setUp(self):
        from routes import discord as discord_route
        import bridge_health

        discord_route._chrome_bridge_seen_event_ids.clear()
        discord_route._chrome_bridge_seen_event_order.clear()
        discord_route._chrome_bridge_seen_alert_fingerprints.clear()
        discord_route._chrome_bridge_seen_alert_order.clear()
        import risk
        risk._seen_fingerprints.clear()
        bridge_health._last_heartbeat = None
        bridge_health._last_attention_key = None
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_capture_dir = os.environ.get("ALERT_CAPTURE_DIR")
        self.old_event_dir = os.environ.get("BOT_EVENT_BUS_DIR")
        self.old_bridge_age_minutes = os.environ.get("CHROME_BRIDGE_MAX_MESSAGE_AGE_MINUTES")
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
        if self.old_bridge_age_minutes is None:
            os.environ.pop("CHROME_BRIDGE_MAX_MESSAGE_AGE_MINUTES", None)
        else:
            os.environ["CHROME_BRIDGE_MAX_MESSAGE_AGE_MINUTES"] = self.old_bridge_age_minutes
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
            author_raw="Analyst [OPTIONS]",
            content="BTO SPY 500C 6/21 @ 1.25",
            revision_hash="abc123",
            event_type="updated",
            url="https://discord.com/channels/1/2/3",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "accepted")
        self.assertTrue(result["alert_inserted"])
        self.assertFalse(result["trade_requested"])
        self.assertEqual(result["trade_request_reason"], "auto trading disabled")
        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertEqual(result["alert_id"], fake_db.alerts[0]["id"])
        self.assertEqual(fake_db.alerts[0]["ticker"], "SPY")
        self.assertEqual(fake_db.alerts[0]["raw_message"], "BTO SPY 500C 6/21 @ 1.25")
        self.assertEqual(fake_db.operator_events[-1]["details"]["decision"]["alert_id"], result["alert_id"])
        self.assertEqual(fake_db.operator_events[-1]["details"]["decision"]["trade_request_reason"], "auto trading disabled")
        self.assertEqual(fake_db.operator_events[-1]["details"]["capture_path"], result["capture_path"])
        self.assertEqual(fake_db.operator_events[-1]["details"]["revision_hash"], "abc123")
        self.assertEqual(fake_db.operator_events[-1]["details"]["event_type"], "updated")
        self.assertEqual(fake_db.operator_events[-1]["details"]["author"]["raw_name"], "Analyst [OPTIONS]")
        self.assertTrue(pathlib.Path(result["capture_path"]).exists())
        self.assertTrue(result["bus_event_id"])

    def test_chrome_bridge_uses_only_high_confidence_ocr_as_alert_text(self):
        from routes import discord as discord_route

        high = discord_route._chrome_bridge_to_message(discord_route.ChromeBridgeMessage(
            event_id="ocr-high",
            attachment_urls=["https://cdn.discordapp.com/alert.png"],
            ocr_text="BTO SPY 500C 9/12 @ .25",
            ocr_confidence=0.91,
        ))
        low = discord_route._chrome_bridge_to_message(discord_route.ChromeBridgeMessage(
            event_id="ocr-low",
            attachment_urls=["https://cdn.discordapp.com/alert.png"],
            ocr_text="BTO SPY 500C 9/12 @ .25",
            ocr_confidence=0.45,
        ))

        self.assertEqual(high.content, "BTO SPY 500C 9/12 @ .25")
        self.assertIn("Image-only Discord alert", low.content)
        self.assertNotIn("BTO SPY", low.content)

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
            bridge_target_id="sentinel-echo",
            bridge_target_name="Sentinel Echo",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
            url="https://discord.com/channels/1/chrome-alerts/999",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))
        events = bot_event_bus.event_bus.recent(event_type="signal.observed")

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["channel_url"], "https://discord.com/channels/1/chrome-alerts")
        self.assertEqual(result["bridge_target_id"], "sentinel-echo")
        self.assertEqual(events[0]["payload"]["channel_url"], "https://discord.com/channels/1/chrome-alerts")
        self.assertEqual(events[0]["payload"]["bridge_target_id"], "sentinel-echo")
        self.assertEqual(events[0]["payload"]["bridge_target_name"], "Sentinel Echo")
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

    def test_chrome_bridge_skips_source_messages_older_than_configured_age(self):
        from routes import discord as discord_route

        os.environ["CHROME_BRIDGE_MAX_MESSAGE_AGE_MINUTES"] = "4"
        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": True,
                "source_overrides": {
                    "chrome-alerts": {},
                },
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-stale-source-message",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
            timestampIso=(datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            observed_at=datetime.now(timezone.utc).isoformat(),
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["skip_reason"], "stale chrome bridge source timestamp")
        self.assertFalse(result["alert_inserted"])
        self.assertFalse(result["trade_requested"])
        self.assertEqual(fake_db.alerts, [])

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

    def test_chrome_bridge_updates_existing_alert_when_discord_edits_same_message(self):
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
        original = discord_route.ChromeBridgeMessage(
            event_id="chat-messages-111-222",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            channel_url="https://discord.com/channels/1/chrome-alerts",
            author_id="analyst-1",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
            url="https://discord.com/channels/1/chrome-alerts/222",
        )
        edited = discord_route.ChromeBridgeMessage(
            event_id="chat-messages-111-222-edited",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            channel_url="https://discord.com/channels/1/chrome-alerts",
            author_id="analyst-1",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25\nJUST FILLED",
            url="https://discord.com/channels/1/chrome-alerts/222",
        )

        first = asyncio.run(discord_route.ingest_chrome_bridge_message(original, request))
        second = asyncio.run(discord_route.ingest_chrome_bridge_message(edited, request))

        self.assertEqual(first["status"], "accepted")
        self.assertEqual(second["status"], "updated")
        self.assertFalse(second["alert_inserted"])
        self.assertFalse(second["trade_requested"])
        self.assertEqual(len(fake_db.alerts), 1)
        self.assertEqual(fake_db.alerts[0]["raw_message"], "BTO SPY 500C 6/21 @ 1.25\nJUST FILLED")
        self.assertEqual(fake_db.alert_updates[0][0], first["alert_id"])

    def test_chrome_bridge_does_not_repeat_unchanged_dca_on_message_revision(self):
        from routes import discord as discord_route
        import risk

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {"process_actionable_edits": True},
                },
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        original = discord_route.ChromeBridgeMessage(
            event_id="1553062206533406791",
            revision_hash="3681b90b",
            event_type="created",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="MikeInvesting",
            content=(
                "$SPY $772 CALLS EXPIRATION 9/25/2026 $.35 Entry\n"
                "Added at $.17 fill to DCA"
            ),
            url="https://discord.com/channels/1/chrome-alerts/1553062206533406791",
        )
        edited = discord_route.ChromeBridgeMessage(
            event_id="1553062206533406791",
            revision_hash="fc0bc576",
            event_type="updated",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="MikeInvesting",
            content=(
                "$SPY $772 CALLS EXPIRATION 9/25/2026 $.35 Entry, $.25 AVG @everyone "
                "SPY fulfilled its technical ETH gap fill, $772 is next\n"
                "Added at $.17 fill to DCA"
            ),
            url="https://discord.com/channels/1/chrome-alerts/1553062206533406791",
        )

        first = asyncio.run(discord_route.ingest_chrome_bridge_message(original, request))
        for fingerprint in list(risk._seen_fingerprints):
            risk._seen_fingerprints[fingerprint] = datetime.now(timezone.utc) - timedelta(minutes=10)
        second = asyncio.run(discord_route.ingest_chrome_bridge_message(edited, request))

        self.assertEqual(first["status"], "accepted")
        self.assertEqual(second["status"], "updated")
        self.assertFalse(second["alert_inserted"])
        self.assertFalse(second["trade_requested"])
        self.assertEqual(len(fake_db.alerts), 1)

    def test_chrome_bridge_processes_dca_revision_when_fill_price_changes(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {"process_actionable_edits": True},
                },
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        original = discord_route.ChromeBridgeMessage(
            event_id="dca-price-correction",
            revision_hash="revision-1",
            event_type="created",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="MikeInvesting",
            content=(
                "$SPY $772 CALLS EXPIRATION 9/25/2026 $.35 Entry\n"
                "Added at $.17 fill to DCA"
            ),
            url="https://discord.com/channels/1/chrome-alerts/dca-price-correction",
        )
        corrected = discord_route.ChromeBridgeMessage(
            event_id="dca-price-correction",
            revision_hash="revision-2",
            event_type="updated",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="MikeInvesting",
            content=(
                "$SPY $772 CALLS EXPIRATION 9/25/2026 $.35 Entry\n"
                "Added at $.16 fill to DCA"
            ),
            url="https://discord.com/channels/1/chrome-alerts/dca-price-correction",
        )

        first = asyncio.run(discord_route.ingest_chrome_bridge_message(original, request))
        second = asyncio.run(discord_route.ingest_chrome_bridge_message(corrected, request))

        self.assertEqual(first["status"], "accepted")
        self.assertEqual(second["status"], "accepted")
        self.assertEqual(len(fake_db.alerts), 2)
        self.assertEqual(fake_db.alerts[1]["entry_price"], 0.16)

    def test_chrome_bridge_channel_url_does_not_identify_distinct_messages_as_edits(self):
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
        first_payload = discord_route.ChromeBridgeMessage(
            event_id="chat-messages-111-222",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            channel_url="https://discord.com/channels/1/chrome-alerts",
            author_id="analyst-1",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
            url="https://discord.com/channels/1/chrome-alerts",
        )
        second_payload = discord_route.ChromeBridgeMessage(
            event_id="chat-messages-111-333",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            channel_url="https://discord.com/channels/1/chrome-alerts",
            author_id="analyst-1",
            author_name="Analyst",
            content="BTO QQQ 450P 6/21 @ 1.10",
            url="https://discord.com/channels/1/chrome-alerts",
        )

        first = asyncio.run(discord_route.ingest_chrome_bridge_message(first_payload, request))
        second = asyncio.run(discord_route.ingest_chrome_bridge_message(second_payload, request))

        self.assertEqual(first["status"], "accepted")
        self.assertEqual(second["status"], "accepted")
        self.assertEqual(len(fake_db.alerts), 2)
        self.assertEqual(fake_db.alerts[0]["ticker"], "SPY")
        self.assertEqual(fake_db.alerts[1]["ticker"], "QQQ")
        self.assertEqual(fake_db.alert_updates, [])

    def test_chrome_bridge_restart_treats_edited_entry_replay_as_existing_alert(self):
        from routes import discord as discord_route
        import risk

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {
                        "process_actionable_edits": True,
                    },
                },
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        original = discord_route.ChromeBridgeMessage(
            event_id="bridge-capture-before-restart",
            channel_id="chrome-alerts",
            channel_name="Discord | alerts",
            channel_url="https://discord.com/channels/1/chrome-alerts",
            author_name="Analyst [ROLE]",
            content="$SPY $766 CALLS EXPIRATION 9/1/2026 $.33 Entry",
            url="https://discord.com/channels/1/chrome-alerts",
        )
        edited = discord_route.ChromeBridgeMessage(
            event_id="bridge-capture-after-restart",
            channel_id="chrome-alerts",
            channel_name="Discord | alerts",
            channel_url="https://discord.com/channels/1/chrome-alerts",
            author_name="Analyst",
            content=(
                "$SPY $766 CALLS EXPIRATION 9/1/2026 $.33 Entry, $.29 AVG\n"
                "(edited) Tuesday, September 1, 2026 at 9:48 AM\n"
                "763.5 break and close below will enact as a SL"
            ),
            url="https://discord.com/channels/1/chrome-alerts",
        )

        first = asyncio.run(discord_route.ingest_chrome_bridge_message(original, request))

        # Simulate a process restart: persisted audit history remains, in-memory
        # event and signal fingerprints do not.
        discord_route._chrome_bridge_seen_event_ids.clear()
        discord_route._chrome_bridge_seen_event_order.clear()
        discord_route._chrome_bridge_seen_alert_fingerprints.clear()
        discord_route._chrome_bridge_seen_alert_order.clear()
        risk._seen_fingerprints.clear()

        second = asyncio.run(discord_route.ingest_chrome_bridge_message(edited, request))

        self.assertEqual(first["status"], "accepted")
        self.assertEqual(second["status"], "updated")
        self.assertFalse(second["alert_inserted"])
        self.assertFalse(second["trade_requested"])
        self.assertEqual(len(fake_db.alerts), 1)
        self.assertEqual(fake_db.alert_updates[0][0], first["alert_id"])

    def test_chrome_bridge_profit_update_refreshes_matching_position_mark(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": True,
                "source_overrides": {
                    "chrome-alerts": {},
                },
            }
        )
        fake_db.positions.append(
            {
                "id": "position-1",
                "ticker": "SPY",
                "strike": 771.0,
                "option_type": "CALL",
                "expiration": "08/27/2026",
                "entry_price": 0.40,
                "current_price": 0.69,
                "highest_price": 0.69,
                "remaining_quantity": 10,
                "broker": "alpaca",
                "status": "open",
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-profit-update",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_id="analyst-1",
            author_name="Analyst",
            content="$.74 HERE ON SPY CALLS UP +90%",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["skip_reason"], "position mark update")
        self.assertFalse(result["alert_inserted"])
        self.assertEqual(fake_db.alerts, [])
        self.assertEqual(fake_db.positions[0]["current_price"], 0.74)
        self.assertEqual(fake_db.positions[0]["highest_price"], 0.74)

    def test_chrome_bridge_profit_update_respects_source_followup_toggle(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": True,
                "source_overrides": {
                    "chrome-alerts": {
                        "process_followup_updates": False,
                    },
                },
            }
        )
        fake_db.positions.append(
            {
                "id": "position-1",
                "ticker": "SPY",
                "strike": 771.0,
                "option_type": "CALL",
                "expiration": "08/27/2026",
                "entry_price": 0.40,
                "current_price": 0.69,
                "highest_price": 0.69,
                "remaining_quantity": 10,
                "broker": "alpaca",
                "status": "open",
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-profit-update-disabled",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_id="analyst-1",
            author_name="Analyst",
            content="$.74 HERE ON SPY CALLS UP +90%",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["skip_reason"], "unparsed")
        self.assertEqual(fake_db.positions[0]["current_price"], 0.69)
        self.assertEqual(fake_db.position_updates, [])

    def test_chrome_bridge_ingests_appended_break_even_stop_as_sell(self):
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
            event_id="chrome-break-even-stop-followup",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content=(
                "$SPY $760 PUTS EXPIRATION 9/1/2026 $.18 Entry high risk lotto\n"
                "Solid attempt at a selloff. Runners hit b/e SL @everyone"
            ),
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["parsed"]["alert_type"], "sell")
        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertEqual(result["parsed"]["strike"], 760.0)
        self.assertEqual(result["parsed"]["option_type"], "PUT")
        self.assertEqual(result["parsed"]["sell_percentage"], 100.0)
        self.assertEqual(fake_db.alerts[0]["alert_type"], "sell")

    def test_chrome_bridge_infers_standalone_sell_for_single_channel_position(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {
                        "allow_single_position_inferred_sell": True,
                    },
                },
            }
        )
        fake_db.alerts.append(
            {
                "id": "entry-alert-1",
                "channel_id": "chrome-alerts",
                "ticker": "SPY",
                "strike": 771.0,
                "option_type": "CALL",
                "expiration": "2026-08-27",
            }
        )
        fake_db.positions.append(
            {
                "id": "position-1",
                "alert_id": "entry-alert-1",
                "ticker": "SPY",
                "strike": 771.0,
                "option_type": "CALL",
                "expiration": "2026-08-27",
                "entry_price": 0.40,
                "current_price": 0.78,
                "remaining_quantity": 10,
                "status": "open",
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-sold-majority",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="SOLD MAJORITY",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["parsed"]["alert_type"], "sell")
        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertEqual(result["parsed"]["strike"], 771.0)
        self.assertEqual(result["parsed"]["expiration"], "2026-08-27")
        self.assertEqual(result["parsed"]["sell_percentage"], 75.0)
        self.assertEqual(result["parser_metadata"]["matched_pattern_type"], "single_position_inferred_sell")

    def test_chrome_bridge_binds_conversational_exit_words_to_single_position(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {"chrome-alerts": {"allow_single_position_inferred_sell": True}},
            }
        )
        fake_db.alerts.append(
            {
                "id": "entry-alert-767p",
                "channel_id": "chrome-alerts",
                "ticker": "SPY",
                "strike": 767.0,
                "option_type": "PUT",
                "expiration": "2026-09-04",
            }
        )
        fake_db.positions.append(
            {
                "id": "position-767p",
                "alert_id": "entry-alert-767p",
                "ticker": "SPY",
                "strike": 767.0,
                "option_type": "PUT",
                "expiration": "2026-09-04",
                "entry_price": 0.28,
                "remaining_quantity": 5,
                "status": "partial",
            }
        )
        discord_route.set_db(fake_db)

        async def infer(text):
            payload = discord_route.ChromeBridgeMessage(
                event_id=f"event-{text}",
                channel_id="chrome-alerts",
                author_name="MikeInvesting",
                content=text,
            )
            return await discord_route._infer_single_channel_position_sell(payload, text, {})

        for text, percentage in (
            ("I'm going to trim slowly now", 50.0),
            ("Sell for +20% rule here", 100.0),
            ("Fully out", 100.0),
        ):
            with self.subTest(text=text):
                parsed = asyncio.run(infer(text))
                self.assertEqual(parsed["ticker"], "SPY")
                self.assertEqual(parsed["strike"], 767.0)
                self.assertEqual(parsed["sell_percentage"], percentage)

    def test_contextual_sell_does_not_cross_newer_contract_conversation(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb({"source_overrides": {"chrome-alerts": {}}})
        fake_db.alerts.extend(
            [
                {
                    "id": "entry-767p",
                    "channel_id": "chrome-alerts",
                    "ticker": "SPY",
                    "strike": 767.0,
                    "option_type": "PUT",
                    "expiration": "2026-09-04",
                },
                {
                    "id": "newer-772c",
                    "channel_id": "chrome-alerts",
                    "ticker": "SPY",
                    "strike": 772.0,
                    "option_type": "CALL",
                    "expiration": "2026-09-04",
                },
            ]
        )
        fake_db.positions.append(
            {
                "id": "position-767p",
                "alert_id": "entry-767p",
                "ticker": "SPY",
                "strike": 767.0,
                "option_type": "PUT",
                "expiration": "2026-09-04",
                "remaining_quantity": 1,
                "status": "partial",
            }
        )
        discord_route.set_db(fake_db)
        payload = discord_route.ChromeBridgeMessage(
            event_id="context-after-newer-contract",
            channel_id="chrome-alerts",
            author_name="MikeInvesting",
            content="OUT OF THERE",
        )

        parsed = asyncio.run(
            discord_route._infer_single_channel_position_sell(payload, payload.content, {})
        )

        self.assertIsNone(parsed)

    def test_chrome_bridge_infers_contract_when_rest_is_misparsed_as_ticker(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {
                        "allow_single_position_inferred_sell": True,
                    },
                },
            }
        )
        fake_db.alerts.append(
            {
                "id": "entry-alert-rest",
                "channel_id": "chrome-alerts",
                "ticker": "SPY",
                "strike": 775.0,
                "option_type": "CALL",
                "expiration": "2026-09-03",
            }
        )
        fake_db.positions.append(
            {
                "id": "position-rest",
                "alert_id": "entry-alert-rest",
                "ticker": "SPY",
                "strike": 775.0,
                "option_type": "CALL",
                "expiration": "2026-09-03",
                "entry_price": 0.27,
                "current_price": 0.27,
                "remaining_quantity": 3,
                "status": "partial",
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-sold-rest",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="Sold rest of my $775 calls @ b/e & hands off.",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertEqual(result["parsed"]["expiration"], "2026-09-03")
        self.assertEqual(result["parsed"]["sell_percentage"], 100.0)
        self.assertTrue(result["parsed"]["market_price"])
        self.assertEqual(result["parser_metadata"]["matched_pattern_type"], "single_position_inferred_sell")

    def test_chrome_bridge_does_not_infer_standalone_sell_when_channel_is_ambiguous(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {
                        "allow_single_position_inferred_sell": True,
                    },
                },
            }
        )
        for index, strike in enumerate((771.0, 772.0), start=1):
            fake_db.alerts.append(
                {
                    "id": f"entry-alert-{index}",
                    "channel_id": "chrome-alerts",
                }
            )
            fake_db.positions.append(
                {
                    "id": f"position-{index}",
                    "alert_id": f"entry-alert-{index}",
                    "ticker": "SPY",
                    "strike": strike,
                    "option_type": "CALL",
                    "expiration": "08/27/26",
                    "entry_price": 0.40,
                    "current_price": 0.78,
                    "remaining_quantity": 10,
                    "status": "open",
                }
            )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-sold-majority-ambiguous",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="SOLD MAJORITY",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["skip_reason"], "unparsed")
        self.assertIsNone(result["parsed"])

    def test_chrome_bridge_infers_conversational_reentry_from_recent_channel_contract(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {
                        "process_followup_updates": True,
                    },
                },
            }
        )
        fake_db.alerts.append(
            {
                "id": "entry-alert-tsla",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "channel_id": "chrome-alerts",
                "alert_type": "buy",
                "ticker": "TSLA",
                "strike": 400.0,
                "option_type": "CALL",
                "expiration": "09/04/26",
                "entry_price": 0.90,
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-tsla-conversational-reentry",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="IN TSLA CALLS AT $.6 FILL @everyone",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["parsed"]["alert_type"], "buy")
        self.assertEqual(result["parsed"]["ticker"], "TSLA")
        self.assertEqual(result["parsed"]["strike"], 400.0)
        self.assertEqual(result["parsed"]["option_type"], "CALL")
        self.assertEqual(result["parsed"]["expiration"], "09/04/26")
        self.assertEqual(result["parsed"]["entry_price"], 0.60)
        self.assertEqual(
            result["parser_metadata"]["matched_pattern_type"],
            "recent_channel_contract_inferred_buy",
        )

    def test_chrome_bridge_does_not_rebuy_conversational_entry_from_appended_profit_edit(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {"chrome-alerts": {"process_followup_updates": True}},
            }
        )
        fake_db.alerts.append(
            {
                "id": "entry-alert-tsla-edit",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "channel_id": "chrome-alerts",
                "alert_type": "buy",
                "ticker": "TSLA",
                "strike": 400.0,
                "option_type": "CALL",
                "expiration": "09/04/26",
                "entry_price": 0.60,
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-tsla-conversational-entry-profit-edit",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content=(
                "IN TSLA CALLS AT $.6 FILL @everyone\n"
                "$.96 HERE ON TSLA CALLS UP +60% @everyone"
            ),
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "skipped")
        self.assertFalse(result["alert_inserted"])
        self.assertIsNone(result["parsed"])

    def test_chrome_bridge_dedupes_same_alert_with_different_dom_event_ids(self):
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
        first_payload = discord_route.ChromeBridgeMessage(
            event_id="chat-messages-123-optimistic",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            channel_url="https://discord.com/channels/1/chrome-alerts",
            author_id="analyst-1",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
        )
        second_payload = discord_route.ChromeBridgeMessage(
            event_id="chat-messages-123-server",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            channel_url="https://discord.com/channels/1/chrome-alerts",
            author_id="analyst-1",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
        )

        first = asyncio.run(discord_route.ingest_chrome_bridge_message(first_payload, request))
        second = asyncio.run(discord_route.ingest_chrome_bridge_message(second_payload, request))

        self.assertEqual(first["status"], "accepted")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(second["skip_reason"], "duplicate bridge alert")
        self.assertEqual(len(fake_db.alerts), 1)

    def test_chrome_bridge_treats_entry_with_appended_commentary_as_an_update(self):
        from routes import discord as discord_route
        import risk

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {
                        "process_actionable_edits": True,
                    },
                },
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        first_payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-entry-original",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="$DELL $500 CALLS EXPIRATION 9/4/2026 $3.5-$4.5 Entry @everyone",
        )
        appended_payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-entry-appended-commentary",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content=(
                "$DELL $500 CALLS EXPIRATION 9/4/2026 $3.5-$4.5 Entry @everyone\n"
                "Crazy volatility behind setup. These went from $4 to $5.6 & dumped @everyone"
            ),
        )

        first = asyncio.run(discord_route.ingest_chrome_bridge_message(first_payload, request))
        for fingerprint in list(risk._seen_fingerprints):
            risk._seen_fingerprints[fingerprint] = datetime.now(timezone.utc) - timedelta(minutes=5)
        second = asyncio.run(discord_route.ingest_chrome_bridge_message(appended_payload, request))

        self.assertEqual(first["status"], "accepted")
        self.assertEqual(second["status"], "updated")
        self.assertFalse(second["trade_requested"])
        self.assertEqual(len(fake_db.alerts), 1)

    def test_chrome_bridge_dedupes_mirrored_entry_with_same_headline_and_new_commentary(self):
        from routes import discord as discord_route
        import risk

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "alerts": {"process_actionable_edits": True},
                    "mirror-analysis": {"process_actionable_edits": True},
                },
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        first_payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-nvda-entry-original",
            channel_id="alerts",
            channel_name="alerts",
            author_name="MikeInvesting",
            content=(
                "$NVDA $230 CALLS EXPIRATION 9/4/2026 $.3 Entry @everyone $230 range PT. EOW EXP\n"
                "I am still in $NVDA at $.3 avg. Holding these with no panic. @everyone"
            ),
        )
        mirrored_payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-nvda-entry-mirror",
            channel_id="mirror-analysis",
            channel_name="mirror-analysis",
            author_name="MikeInvesting",
            content=(
                "$NVDA $230 CALLS EXPIRATION 9/4/2026 $.3 Entry @everyone $230 range PT. EOW EXP\n"
                "Many doubted the alert. Those who didn't got paid. What can I say. @everyone"
            ),
        )

        first = asyncio.run(discord_route.ingest_chrome_bridge_message(first_payload, request))
        for fingerprint in list(risk._seen_fingerprints):
            risk._seen_fingerprints[fingerprint] = datetime.now(timezone.utc) - timedelta(minutes=30)
        second = asyncio.run(discord_route.ingest_chrome_bridge_message(mirrored_payload, request))

        self.assertEqual(first["status"], "accepted")
        self.assertEqual(second["status"], "updated")
        self.assertFalse(second["trade_requested"])
        self.assertEqual(len(fake_db.alerts), 1)

    def test_chrome_bridge_respects_shared_duplicate_alert_detector(self):
        from routes import discord as discord_route
        from risk import is_duplicate_alert
        from utils import normalize_parsed_alert, parse_alert

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {},
                },
            }
        )
        discord_route.set_db(fake_db)
        self.assertFalse(is_duplicate_alert(normalize_parsed_alert(parse_alert("BTO SPY 500C 6/21 @ 1.25"))))

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-cross-ingestion-duplicate",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["skip_reason"], "duplicate alert")
        self.assertEqual(fake_db.alerts, [])

    def test_chrome_bridge_canonicalizes_nested_discord_message_event_ids(self):
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
        nested = discord_route.ChromeBridgeMessage(
            event_id="chat-messages___chat-messages-111-222",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
        )
        canonical = discord_route.ChromeBridgeMessage(
            event_id="chat-messages-111-222",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
        )

        first = asyncio.run(discord_route.ingest_chrome_bridge_message(nested, request))
        second = asyncio.run(discord_route.ingest_chrome_bridge_message(canonical, request))

        self.assertEqual(first["event_id"], "chat-messages-111-222")
        self.assertEqual(fake_db.operator_events[-1]["details"]["event_id"], "chat-messages-111-222")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(len(fake_db.alerts), 1)

    def test_chrome_bridge_rejects_persisted_duplicate_event_after_restart(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {},
                },
            }
        )
        fake_db.operator_events.append(
            {
                "id": "prior-event",
                "action": "bridge_alert_decision",
                "details": {
                    "event_id": "chat-messages-111-333",
                },
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chat-messages___chat-messages-111-333",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            author_name="Analyst",
            content="BTO SPY 500C 6/21 @ 1.25",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["event_id"], "chat-messages-111-333")
        self.assertEqual(fake_db.alerts, [])

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

    def test_sentinel_link_saved_channel_auto_enrolls_before_ingestion(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "chrome_bridge_require_source_override": True,
                "source_overrides": {},
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="homebrew-card-1",
            channel_id="1545210915031490651",
            channel_name="#homebrew-alerts",
            channel_url="https://discord.com/channels/1521713840281354283/1545210915031490651",
            author_name="Money Glitch",
            content="SPY $771C 09-24 Filled 20x @ $0.27",
            source="sentinel-link",
            source_mode="listen-only",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(len(fake_db.alerts), 1)
        policy = fake_db.settings["source_overrides"]["1545210915031490651"]
        self.assertEqual(policy["managed_by"], "sentinel-link")
        self.assertEqual(policy["enrollment_mode"], "listen-only")
        self.assertTrue(policy["allow_fresh_entry_after_close"])
        self.assertEqual(
            policy["allowed_channel_urls"],
            ["https://discord.com/channels/1521713840281354283/1545210915031490651"],
        )
        self.assertTrue(fake_db.operator_events[-1]["details"]["source"]["override_matched"])

    def test_sentinel_link_auto_enrollment_does_not_make_conversation_actionable(self):
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
            event_id="homebrew-comment-1",
            channel_id="1545210915031490651",
            channel_name="#homebrew-alerts",
            channel_url="https://discord.com/channels/1521713840281354283/1545210915031490651",
            author_name="Austin",
            content="i want a pop out of this level",
            source="sentinel-link",
            source_mode="listen-only",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["skip_reason"], "unparsed")
        self.assertEqual(fake_db.alerts, [])
        self.assertIn("1545210915031490651", fake_db.settings["source_overrides"])

    def test_sentinel_link_auto_enrollment_rejects_mismatched_channel_url(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "chrome_bridge_require_source_override": True,
                "source_overrides": {},
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="mismatched-channel-proof",
            channel_id="1545210915031490651",
            channel_name="#homebrew-alerts",
            channel_url="https://discord.com/channels/1521713840281354283/999999999999999999",
            author_name="Money Glitch",
            content="BTO SPY 771C 9/24 @ .27",
            source="sentinel-link",
            source_mode="listen-only",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["skip_reason"], "source override required for chrome bridge")
        self.assertEqual(fake_db.settings["source_overrides"], {})

    def test_sentinel_link_auto_enrollment_preserves_existing_customer_policy(self):
        from routes import discord as discord_route

        existing_policy = {
            "name": "Customer Homebrew Policy",
            "max_contracts": 3,
            "min_parser_confidence": "high",
            "allowed_author_ids": ["name:Money Glitch"],
        }
        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "chrome_bridge_require_source_override": True,
                "source_overrides": {"1545210915031490651": dict(existing_policy)},
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="homebrew-existing-policy",
            channel_id="1545210915031490651",
            channel_name="#homebrew-alerts",
            channel_url="https://discord.com/channels/1521713840281354283/1545210915031490651",
            author_name="Money Glitch",
            content="SPY $771C 09-24 Filled 20x @ $0.27",
            source="sentinel-link",
            source_mode="listen-only",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(
            fake_db.settings["source_overrides"]["1545210915031490651"],
            existing_policy,
        )

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

    def test_chrome_bridge_audit_records_source_metadata_policy_proof_for_accepted_alert(self):
        from routes import discord as discord_route

        fake_db = FakeChromeBridgeDb(
            {
                "auto_trading_enabled": False,
                "source_overrides": {
                    "chrome-alerts": {
                        "allowed_channel_urls": ["https://discord.com/channels/1/approved"],
                        "allowed_author_ids": ["mike"],
                        "min_parser_confidence": "medium",
                    }
                },
            }
        )
        discord_route.set_db(fake_db)

        request = types.SimpleNamespace(client=types.SimpleNamespace(host="127.0.0.1"))
        payload = discord_route.ChromeBridgeMessage(
            event_id="chrome-source-metadata-proof",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            channel_url="https://discord.com/channels/1/approved",
            author_id="mike",
            author_name="MikeInvesting",
            content="BTO SPY 500C 6/21 @ 1.25",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))

        source = fake_db.operator_events[-1]["details"]["source"]
        self.assertEqual(result["status"], "accepted")
        self.assertTrue(source["channel_url_allowed"])
        self.assertTrue(source["author_id_allowed"])
        self.assertTrue(source["parser_confidence_allowed"])
        self.assertTrue(source["metadata_policy_passed"])

    def test_chrome_bridge_audit_uses_author_name_identity_when_dom_lacks_author_id(self):
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
            event_id="chrome-author-name-identity",
            channel_id="chrome-alerts",
            channel_name="chrome-alerts",
            channel_url="https://discord.com/channels/1/chrome-alerts",
            author_name="OpenClaw",
            content="BTO SPY 500C 6/21 @ 1.25",
        )

        result = asyncio.run(discord_route.ingest_chrome_bridge_message(payload, request))
        details = fake_db.operator_events[-1]["details"]
        bus_event = bot_event_bus.event_bus.recent(event_type="signal.observed")[0]

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(details["author"]["id"], "name:OpenClaw")
        self.assertEqual(bus_event["payload"]["author_id"], "name:OpenClaw")
        self.assertTrue(details["source"]["author_id_allowed"])


if __name__ == "__main__":
    unittest.main()
