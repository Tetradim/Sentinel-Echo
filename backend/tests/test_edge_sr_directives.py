from datetime import datetime, timezone
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def _directive(**overrides):
    payload = {
        "schema_version": "edge.sr.directive.v1",
        "directive_id": "edge-sr-1",
        "created_at": "2026-06-24T14:35:00+00:00",
        "action": "close_position",
        "reason_code": "call_support_break",
        "underlying": "AAPL",
        "position": {
            "position_id": "AAPL-20260624-200-C",
            "underlying": "AAPL",
            "option_side": "call",
            "quantity": 2,
            "expiry": "2026-06-24",
            "strike": 200.0,
            "entry_price": 2.4,
        },
        "level": {"id": "opening_range_low", "role": "support", "price": 198.0},
        "execution_hint": {"immediate": True, "order_preference": "marketable_limit"},
    }
    payload.update(overrides)
    return payload


class EdgeSrDirectiveTests(unittest.TestCase):
    def test_close_directive_requires_full_contract_identity(self):
        from edge_sr_directives import validate_edge_sr_directive

        result = validate_edge_sr_directive(
            _directive(),
            now=datetime(2026, 6, 24, 14, 35, 20, tzinfo=timezone.utc),
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["intent"]["action"], "close_position")
        self.assertEqual(result["intent"]["contract"]["underlying"], "AAPL")
        self.assertEqual(result["intent"]["contract"]["option_side"], "call")
        self.assertEqual(result["intent"]["contract"]["quantity"], 2)

    def test_missing_contract_identity_is_invalid(self):
        from edge_sr_directives import validate_edge_sr_directive

        payload = _directive(position={"underlying": "AAPL", "option_side": "call", "quantity": 2})
        result = validate_edge_sr_directive(payload)

        self.assertFalse(result["valid"])
        self.assertIn("position.expiry is required", result["errors"])
        self.assertIn("position.strike is required", result["errors"])

    def test_scale_in_directive_validates_sizing_without_creating_order(self):
        from edge_sr_directives import validate_edge_sr_directive

        result = validate_edge_sr_directive(
            _directive(
                action="request_scale_in",
                reason_code="call_resistance_break",
                sizing_hint={
                    "mode": "buying_power_fraction",
                    "fraction": 0.25,
                    "minimum_contracts": 1,
                },
            )
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["intent"]["action"], "request_scale_in")
        self.assertEqual(result["intent"]["sizing"]["mode"], "buying_power_fraction")
        self.assertEqual(result["intent"]["sizing"]["fraction"], 0.25)
        self.assertNotIn("order_id", result["intent"])

    def test_duplicate_and_stale_directives_are_rejected_by_helper(self):
        from edge_sr_directives import EdgeSrDirectiveIdempotency, validate_edge_sr_directive

        seen = EdgeSrDirectiveIdempotency()
        first = seen.accept("edge-sr-1")
        duplicate = seen.accept("edge-sr-1")
        stale = validate_edge_sr_directive(
            _directive(created_at="2026-06-24T14:00:00+00:00"),
            now=datetime(2026, 6, 24, 14, 35, 20, tzinfo=timezone.utc),
            max_age_seconds=60,
        )

        self.assertTrue(first["accepted"])
        self.assertFalse(duplicate["accepted"])
        self.assertEqual(duplicate["reason"], "duplicate_directive")
        self.assertFalse(stale["valid"])
        self.assertIn("directive is stale", stale["errors"])


if __name__ == "__main__":
    unittest.main()
