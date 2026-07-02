import os
import pathlib
import sys
import tempfile
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class BotEventBusTests(unittest.TestCase):
    def test_store_publishes_and_reads_recent_events(self):
        from bot_event_bus import BotEvent, EventBusStore

        with tempfile.TemporaryDirectory() as temp_dir:
            store = EventBusStore(pathlib.Path(temp_dir))
            event = store.publish(
                BotEvent(
                    event_type="edge.action",
                    source_bot="sentinel-edge",
                    target_bots=["sentinel-pulse"],
                    payload={"action": "stop_buying"},
                )
            )

            recent = store.recent()

        self.assertEqual(recent[0]["event_id"], event.event_id)
        self.assertEqual(recent[0]["payload"]["action"], "stop_buying")

    def test_bridge_health_failure_requests_openclaw_attention(self):
        old_event_dir = os.environ.get("BOT_EVENT_BUS_DIR")
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["BOT_EVENT_BUS_DIR"] = temp_dir
            import bridge_health

            bridge_health._last_heartbeat = None
            bridge_health._last_attention_key = None

            status = bridge_health.evaluate_bridge_health()
            from bot_event_bus import event_bus

            events = event_bus.recent(event_type="openclaw.attention.requested")

        if old_event_dir is None:
            os.environ.pop("BOT_EVENT_BUS_DIR", None)
        else:
            os.environ["BOT_EVENT_BUS_DIR"] = old_event_dir

        self.assertEqual(status["status"], "unhealthy")
        self.assertEqual(events[0]["source_bot"], "sentinel-echo")


if __name__ == "__main__":
    unittest.main()
