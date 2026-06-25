from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def _position(**overrides):
    position = {
        "id": "pos-1",
        "ticker": "AAPL",
        "strike": 200.0,
        "option_type": "CALL",
        "expiration": "2026-06-24",
        "entry_price": 2.4,
        "current_price": 2.1,
        "remaining_quantity": 4,
        "status": "open",
    }
    position.update(overrides)
    return position


def _directive(**overrides):
    directive = {
        "schema_version": "edge.sr.directive.v1",
        "directive_id": "edge-sr-1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "action": "close_position",
        "reason_code": "call_support_break",
        "position": {
            "position_id": "pos-1",
            "underlying": "AAPL",
            "option_side": "call",
            "quantity": 4,
            "expiry": "2026-06-24",
            "strike": 200.0,
            "entry_price": 2.4,
        },
        "level": {"id": "opening_range_low", "role": "support", "price": 198.0},
        "execution_hint": {"immediate": True, "order_preference": "marketable_limit"},
        "sizing_hint": {"mode": "close_existing_position", "fraction": 1.0},
    }
    directive.update(overrides)
    return directive


class EdgeSrExecutionTests(unittest.TestCase):
    def test_close_directive_builds_ready_sell_intent_when_auto_act_enabled(self):
        from edge_sr_execution import build_edge_sr_execution_plan

        plan = build_edge_sr_execution_plan(
            _directive(),
            positions=[_position()],
            source_config={"sr_watch_enabled": True, "sr_watch_auto_act": True},
            now=datetime(2026, 6, 24, 14, 35, 20, tzinfo=timezone.utc),
        )

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["action"], "close_position")
        self.assertEqual(plan["position_id"], "pos-1")
        self.assertEqual(plan["order_intent"]["side"], "SELL")
        self.assertEqual(plan["order_intent"]["quantity"], 4)
        self.assertEqual(plan["order_intent"]["limit_price"], 2.1)

    def test_auto_act_disabled_requires_operator_review(self):
        from edge_sr_execution import build_edge_sr_execution_plan

        plan = build_edge_sr_execution_plan(
            _directive(),
            positions=[_position()],
            source_config={"sr_watch_enabled": True, "sr_watch_auto_act": False},
        )

        self.assertEqual(plan["status"], "operator_review_required")
        self.assertEqual(plan["reason"], "sr_watch_auto_act_disabled")
        self.assertNotIn("order_intent", plan)

    def test_duplicate_directive_is_rejected(self):
        from edge_sr_directives import EdgeSrDirectiveIdempotency
        from edge_sr_execution import build_edge_sr_execution_plan

        seen = EdgeSrDirectiveIdempotency()
        first = build_edge_sr_execution_plan(
            _directive(),
            positions=[_position()],
            source_config={"sr_watch_enabled": True, "sr_watch_auto_act": True},
            idempotency=seen,
        )
        duplicate = build_edge_sr_execution_plan(
            _directive(),
            positions=[_position()],
            source_config={"sr_watch_enabled": True, "sr_watch_auto_act": True},
            idempotency=seen,
        )

        self.assertEqual(first["status"], "ready")
        self.assertEqual(duplicate["status"], "rejected")
        self.assertEqual(duplicate["reason"], "duplicate_directive")

    def test_scale_in_after_cutoff_is_blocked(self):
        from edge_sr_execution import build_edge_sr_execution_plan

        plan = build_edge_sr_execution_plan(
            _directive(
                action="request_scale_in",
                reason_code="call_resistance_break",
                sizing_hint={"mode": "buying_power_fraction", "fraction": 0.25, "minimum_contracts": 1},
            ),
            positions=[_position()],
            source_config={
                "sr_watch_enabled": True,
                "sr_watch_auto_act": True,
                "sr_watch_stop_trading_after_time_enabled": True,
                "sr_watch_stop_trading_after_time": "15:15",
            },
            now=datetime(2026, 6, 24, 20, 16, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["reason"], "scale_in_after_cutoff")

    def test_close_after_cutoff_is_still_allowed(self):
        from edge_sr_execution import build_edge_sr_execution_plan

        plan = build_edge_sr_execution_plan(
            _directive(),
            positions=[_position()],
            source_config={
                "sr_watch_enabled": True,
                "sr_watch_auto_act": True,
                "sr_watch_stop_trading_after_time_enabled": True,
                "sr_watch_stop_trading_after_time": "15:15",
            },
            now=datetime(2026, 6, 24, 20, 16, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["action"], "close_position")

    def test_unmatched_position_is_blocked(self):
        from edge_sr_execution import build_edge_sr_execution_plan

        plan = build_edge_sr_execution_plan(
            _directive(),
            positions=[_position(id="other-pos")],
            source_config={"sr_watch_enabled": True, "sr_watch_auto_act": True},
        )

        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["reason"], "position_not_found")


if __name__ == "__main__":
    unittest.main()
