import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class SimulationReplayTests(unittest.TestCase):
    def test_preview_replay_events_without_requesting_real_execution(self):
        from simulation_replay import build_replay_preview

        replay = {
            "contract_version": "simulation.consolidation.replay.v1",
            "events": [
                {
                    "event_id": "discord_alert:m1",
                    "type": "discord_alert",
                    "timestamp": "2026-06-19T14:30:00+00:00",
                    "channel_id": "123",
                    "payload": {
                        "message": {"channel_id": "123", "channel_name": "alerts", "content": "BTO SPY 500C 6/21 @ 1.25"},
                        "alert": {"raw_text": "BTO SPY 500C 6/21 @ 1.25"},
                        "market_snapshot": {"selected_market_price": 1.05},
                        "price_drift": {"price_drift_alert": True, "price_drift_amount": -0.2},
                    },
                }
            ],
        }

        preview = build_replay_preview(
            replay,
            {
                "auto_trading_enabled": True,
                "simulation_mode": True,
                "source_overrides": {"alerts": {"paper_only": True}},
            },
        )

        self.assertEqual(preview["contract_version"], "consolidation.simulation_replay_preview.v1")
        self.assertEqual(preview["execution_mode"], "preview_only_no_trades")
        self.assertEqual(preview["event_count"], 1)
        self.assertEqual(preview["parsed_count"], 1)
        self.assertEqual(preview["would_request_trade_count"], 1)
        self.assertEqual(preview["drift_alert_count"], 1)
        self.assertEqual(preview["results"][0]["parsed"]["ticker"], "SPY")
        self.assertTrue(preview["results"][0]["would_insert_alert"])
        self.assertTrue(preview["results"][0]["market_context"]["price_drift"]["price_drift_alert"])

    def test_preview_blocks_trade_request_when_risk_sizing_returns_zero(self):
        from simulation_replay import build_replay_preview

        replay = {
            "contract_version": "simulation.consolidation.replay.v1",
            "events": [
                {
                    "event_id": "discord_alert:m-risk",
                    "type": "discord_alert",
                    "timestamp": "2026-06-11T14:30:00+00:00",
                    "channel_id": "123",
                    "payload": {
                        "message": {
                            "channel_id": "123",
                            "channel_name": "alerts",
                            "content": "$SPY\n$740 CALLS\nEXPIRATION 6/12/2026\n$1.1 Entry",
                        },
                        "alert": {
                            "raw_text": "$SPY\n$740 CALLS\nEXPIRATION 6/12/2026\n$1.1 Entry",
                        },
                    },
                }
            ],
        }

        preview = build_replay_preview(
            replay,
            {
                "auto_trading_enabled": True,
                "simulation_mode": True,
                "default_quantity": 1,
                "max_position_size": 100.0,
            },
        )

        self.assertEqual(preview["parsed_count"], 1)
        self.assertEqual(preview["would_request_trade_count"], 0)
        result = preview["results"][0]
        self.assertTrue(result["would_insert_alert"])
        self.assertFalse(result["would_request_trade"])
        self.assertEqual(
            result["execution_preview"]["reason"],
            "position size exceeds max_position_size",
        )
        self.assertEqual(result["execution_preview"]["quantity"], 0)
        self.assertFalse(result["execution_preview"]["would_request_trade"])

    def test_normalize_replay_url_accepts_engine_root_or_full_endpoint(self):
        from simulation_replay import normalize_replay_url

        self.assertEqual(
            normalize_replay_url("http://127.0.0.1:9200"),
            "http://127.0.0.1:9200/api/consolidation/replay/events",
        )
        self.assertEqual(
            normalize_replay_url("http://127.0.0.1:9200/api/consolidation/replay/events"),
            "http://127.0.0.1:9200/api/consolidation/replay/events",
        )


if __name__ == "__main__":
    unittest.main()
