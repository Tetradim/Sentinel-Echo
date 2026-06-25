from pathlib import Path
import sys
import unittest


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def _close_plan():
    return {
        "status": "ready",
        "action": "close_position",
        "directive_id": "edge-sr-close-1",
        "position_id": "pos-1",
        "reason_code": "call_support_break",
        "order_intent": {
            "side": "SELL",
            "ticker": "AAPL",
            "strike": 200.0,
            "option_type": "CALL",
            "expiration": "2026-06-24",
            "quantity": 4,
            "limit_price": 2.1,
            "order_preference": "marketable_limit",
        },
    }


def _scale_plan():
    return {
        "status": "ready",
        "action": "request_scale_in",
        "directive_id": "edge-sr-scale-1",
        "position_id": "pos-1",
        "reason_code": "call_resistance_break",
        "order_intent": {
            "side": "BUY",
            "ticker": "AAPL",
            "strike": 200.0,
            "option_type": "CALL",
            "expiration": "2026-06-24",
            "sizing": {
                "mode": "buying_power_fraction",
                "fraction": 0.25,
                "minimum_contracts": 1,
            },
        },
    }


class EdgeSrActionRequestTests(unittest.TestCase):
    def test_close_plan_builds_sell_alert_request(self):
        from edge_sr_action_request import build_edge_sr_action_request

        request = build_edge_sr_action_request(
            _close_plan(),
            source_config={"sr_watch_enabled": True, "sr_watch_auto_act": True},
        )

        alert = request["alert"]
        parsed = request["parsed"]
        self.assertEqual(alert.ticker, "AAPL")
        self.assertEqual(alert.alert_type, "sell")
        self.assertEqual(alert.sell_percentage, 100.0)
        self.assertEqual(alert.entry_price, 2.1)
        self.assertEqual(parsed["alert_type"], "sell")
        self.assertEqual(parsed["_edge_sr_directive_id"], "edge-sr-close-1")
        self.assertEqual(parsed["_edge_sr_reason_code"], "call_support_break")
        self.assertTrue(parsed["_source_config"]["sr_watch_enabled"])

    def test_scale_in_plan_builds_buy_alert_request_with_edge_metadata(self):
        from edge_sr_action_request import build_edge_sr_action_request

        request = build_edge_sr_action_request(
            _scale_plan(),
            source_config={"sr_watch_enabled": True, "sr_watch_auto_act": True},
        )

        alert = request["alert"]
        parsed = request["parsed"]
        self.assertEqual(alert.alert_type, "buy")
        self.assertEqual(alert.entry_price, 0.01)
        self.assertEqual(parsed["alert_type"], "buy")
        self.assertEqual(parsed["_edge_sr_directive_id"], "edge-sr-scale-1")
        self.assertEqual(parsed["_edge_sr_sizing"]["fraction"], 0.25)
        self.assertTrue(parsed["_source_config"]["sr_watch_auto_act"])

    def test_non_ready_plan_is_rejected(self):
        from edge_sr_action_request import build_edge_sr_action_request

        with self.assertRaisesRegex(ValueError, "ready"):
            build_edge_sr_action_request(
                {"status": "blocked", "reason": "position_not_found"},
                source_config={"sr_watch_enabled": True},
            )


if __name__ == "__main__":
    unittest.main()
