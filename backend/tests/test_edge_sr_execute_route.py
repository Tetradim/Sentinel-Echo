from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def _directive():
    return {
        "schema_version": "edge.sr.directive.v1",
        "directive_id": "edge-sr-execute-1",
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


def _body(source_config=None, positions=None):
    return {
        "payload": _directive(),
        "positions": [_position()] if positions is None else positions,
        "source_config": source_config or {"sr_watch_enabled": True, "sr_watch_auto_act": True},
    }


def _client(executor=None):
    from routes import edge_sr

    edge_sr.set_executor(executor)
    app = FastAPI()
    app.include_router(edge_sr.router)
    return TestClient(app)


class EdgeSrExecuteRouteTests(unittest.TestCase):
    def test_execute_route_requires_confirmation_header(self):
        calls = []

        async def executor(alert, parsed):
            calls.append((alert, parsed))

        response = _client(executor).post("/edge/sr/directives/execute", json=_body())

        self.assertEqual(response.status_code, 409)
        self.assertEqual(calls, [])

    def test_execute_route_submits_ready_plan_to_injected_executor(self):
        calls = []

        async def executor(alert, parsed):
            calls.append((alert, parsed))

        response = _client(executor).post(
            "/edge/sr/directives/execute",
            headers={"X-Edge-SR-Execution-Confirm": "EXECUTE EDGE SR DIRECTIVE"},
            json=_body(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "submitted")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0].alert_type, "sell")
        self.assertEqual(calls[0][1]["_edge_sr_directive_id"], "edge-sr-execute-1")

    def test_execute_route_does_not_submit_non_ready_plan(self):
        calls = []

        async def executor(alert, parsed):
            calls.append((alert, parsed))

        response = _client(executor).post(
            "/edge/sr/directives/execute",
            headers={"X-Edge-SR-Execution-Confirm": "EXECUTE EDGE SR DIRECTIVE"},
            json=_body(source_config={"sr_watch_enabled": True, "sr_watch_auto_act": False}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_submitted")
        self.assertEqual(response.json()["plan"]["status"], "operator_review_required")
        self.assertEqual(calls, [])

    def test_execute_route_requires_configured_executor(self):
        response = _client(None).post(
            "/edge/sr/directives/execute",
            headers={"X-Edge-SR-Execution-Confirm": "EXECUTE EDGE SR DIRECTIVE"},
            json=_body(),
        )

        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
