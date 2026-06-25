from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def _directive():
    return {
        "schema_version": "edge.sr.directive.v1",
        "directive_id": "edge-sr-route-1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "action": "close_position",
        "reason_code": "call_support_break",
        "position": {
            "position_id": "pos-1",
            "underlying": "AAPL",
            "option_side": "call",
            "quantity": 2,
            "expiry": "2026-06-24",
            "strike": 200.0,
            "entry_price": 2.4,
        },
        "execution_hint": {"immediate": True, "order_preference": "marketable_limit"},
        "sizing_hint": {"mode": "close_existing_position", "fraction": 1.0},
    }


def _position():
    return {
        "id": "pos-1",
        "ticker": "AAPL",
        "strike": 200.0,
        "option_type": "CALL",
        "expiration": "2026-06-24",
        "entry_price": 2.4,
        "current_price": 2.1,
        "remaining_quantity": 2,
        "status": "open",
    }


def _client():
    from routes.edge_sr import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class EdgeSrRouteTests(unittest.TestCase):
    def test_preview_directive_returns_execution_plan_without_order(self):
        response = _client().post(
            "/edge/sr/directives/preview",
            json={
                "payload": _directive(),
                "positions": [_position()],
                "source_config": {"sr_watch_enabled": True, "sr_watch_auto_act": True},
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["plan"]["status"], "ready")
        self.assertEqual(body["plan"]["order_intent"]["side"], "SELL")
        self.assertNotIn("order_id", body["plan"]["order_intent"])

    def test_get_events_returns_targeted_edge_sr_events(self):
        previous_event_dir = os.environ.get("BOT_EVENT_BUS_DIR")
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["BOT_EVENT_BUS_DIR"] = temp_dir
            Path(temp_dir, "2026-06-24.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "event_id": "evt-sr",
                                "event_type": "edge.sr.directive.v1",
                                "target_bots": ["consolidation"],
                                "payload": _directive(),
                            }
                        ),
                        json.dumps(
                            {
                                "event_id": "evt-other",
                                "event_type": "edge.sr.directive.v1",
                                "target_bots": ["sentinel-pulse"],
                                "payload": _directive(),
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            response = _client().get("/edge/sr/events")

        if previous_event_dir is None:
            os.environ.pop("BOT_EVENT_BUS_DIR", None)
        else:
            os.environ["BOT_EVENT_BUS_DIR"] = previous_event_dir

        self.assertEqual(response.status_code, 200)
        self.assertEqual([event["event_id"] for event in response.json()["events"]], ["evt-sr"])


if __name__ == "__main__":
    unittest.main()
