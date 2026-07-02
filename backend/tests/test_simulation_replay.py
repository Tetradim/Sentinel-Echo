import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class SimulationReplayTests(unittest.TestCase):
    def test_preview_replay_events_without_requesting_real_execution(self):
        from simulation_replay import build_replay_preview

        replay = {
            "contract_version": "simulation.sentinel-echo.replay.v1",
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

        self.assertEqual(preview["contract_version"], "sentinel-echo.simulation_replay_preview.v1")
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
            "contract_version": "simulation.sentinel-echo.replay.v1",
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

    def test_preview_treats_malformed_settings_as_operational_defaults(self):
        from simulation_replay import build_replay_preview

        replay = {
            "contract_version": "simulation.sentinel-echo.replay.v1",
            "events": [
                {
                    "event_id": "discord_alert:m-malformed-settings",
                    "type": "discord_alert",
                    "timestamp": "2026-06-19T14:30:00+00:00",
                    "channel_id": "123",
                    "payload": {
                        "message": {
                            "channel_id": "123",
                            "channel_name": "alerts",
                            "content": "BTO SPY 500C 6/21 @ 1.25",
                        }
                    },
                }
            ],
        }

        preview = build_replay_preview(replay, "settings")

        self.assertEqual(preview["parsed_count"], 1)
        self.assertEqual(preview["would_request_trade_count"], 1)
        result = preview["results"][0]
        self.assertTrue(result["would_insert_alert"])
        self.assertTrue(result["would_request_trade"])
        self.assertIsNone(result["execution_preview"]["reason"])
        self.assertTrue(result["execution_preview"]["auto_trading_enabled"])
        self.assertTrue(result["execution_preview"]["simulation_mode"])

    def test_preview_parses_string_trading_flags_without_truthy_fallback(self):
        from simulation_replay import build_replay_preview

        replay = {
            "contract_version": "simulation.sentinel-echo.replay.v1",
            "events": [
                {
                    "event_id": "discord_alert:m-string-flags",
                    "type": "discord_alert",
                    "timestamp": "2026-06-19T14:30:00+00:00",
                    "channel_id": "123",
                    "payload": {
                        "message": {
                            "channel_id": "123",
                            "channel_name": "alerts",
                            "content": "BTO SPY 500C 6/21 @ 1.25",
                        }
                    },
                }
            ],
        }

        preview = build_replay_preview(
            replay,
            {
                "auto_trading_enabled": "false",
                "simulation_mode": "false",
                "default_quantity": 1,
                "max_position_size": 1000.0,
            },
        )

        result = preview["results"][0]
        self.assertFalse(result["execution_preview"]["would_request_trade"])
        self.assertEqual(result["execution_preview"]["reason"], "auto trading disabled")
        self.assertFalse(result["execution_preview"]["auto_trading_enabled"])
        self.assertFalse(result["execution_preview"]["simulation_mode"])

    def test_replay_preview_reports_acceptance_passes_for_expected_outcomes(self):
        from simulation_replay import build_replay_preview

        replay = {
            "contract_version": "simulation.sentinel-echo.replay.v1",
            "events": [
                {
                    "event_id": "discord_alert:m-expected-pass",
                    "type": "discord_alert",
                    "timestamp": "2026-06-19T14:30:00+00:00",
                    "channel_id": "alerts",
                    "payload": {
                        "message": {
                            "channel_id": "alerts",
                            "channel_name": "alerts",
                            "content": "BTO SPY 500C 6/21 @ 1.25",
                        },
                        "expected": {
                            "parsed": {
                                "ticker": "SPY",
                                "strike": 500.0,
                                "option_type": "CALL",
                                "alert_type": "buy",
                            },
                            "would_insert_alert": True,
                            "would_request_trade": True,
                            "skip_reason": None,
                            "execution_reason": None,
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
                "source_overrides": {"alerts": {"paper_only": True}},
            },
        )

        self.assertEqual(preview["acceptance"]["status"], "passed")
        self.assertEqual(preview["acceptance"]["expected_count"], 1)
        self.assertEqual(preview["acceptance"]["failed_count"], 0)
        self.assertTrue(preview["results"][0]["acceptance"]["passed"])
        self.assertEqual(preview["results"][0]["acceptance"]["mismatches"], [])

    def test_replay_preview_reports_acceptance_failures_with_field_mismatches(self):
        from simulation_replay import build_replay_preview

        replay = {
            "contract_version": "simulation.sentinel-echo.replay.v1",
            "expected_results": {
                "discord_alert:m-expected-fail": {
                    "parsed": {
                        "ticker": "QQQ",
                    },
                    "would_request_trade": True,
                    "execution_reason": None,
                }
            },
            "events": [
                {
                    "event_id": "discord_alert:m-expected-fail",
                    "type": "discord_alert",
                    "timestamp": "2026-06-19T14:30:00+00:00",
                    "channel_id": "alerts",
                    "payload": {
                        "message": {
                            "channel_id": "alerts",
                            "channel_name": "alerts",
                            "content": "BTO SPY 500C 6/21 @ 1.25",
                        },
                    },
                }
            ],
        }

        preview = build_replay_preview(
            replay,
            {
                "auto_trading_enabled": False,
                "simulation_mode": True,
                "source_overrides": {"alerts": {"paper_only": True}},
            },
        )

        self.assertEqual(preview["acceptance"]["status"], "failed")
        self.assertEqual(preview["acceptance"]["expected_count"], 1)
        self.assertEqual(preview["acceptance"]["failed_count"], 1)
        self.assertEqual(preview["acceptance"]["failed_event_count"], 1)
        self.assertEqual(preview["acceptance"]["failed_event_ids"], ["discord_alert:m-expected-fail"])
        mismatches = preview["results"][0]["acceptance"]["mismatches"]
        self.assertIn(
            {
                "field": "parsed.ticker",
                "expected": "QQQ",
                "actual": "SPY",
            },
            mismatches,
        )
        self.assertIn(
            {
                "field": "would_request_trade",
                "expected": True,
                "actual": False,
            },
            mismatches,
        )
        self.assertIn(
            {
                "field": "execution_reason",
                "expected": None,
                "actual": "auto trading disabled",
            },
            mismatches,
        )

    def test_replay_preview_fails_acceptance_when_expected_event_is_missing(self):
        from simulation_replay import build_replay_preview

        replay = {
            "contract_version": "simulation.sentinel-echo.replay.v1",
            "expected_results": {
                "discord_alert:missing": {
                    "parsed": {"ticker": "SPY"},
                    "would_request_trade": True,
                }
            },
            "events": [],
        }

        preview = build_replay_preview(
            replay,
            {
                "auto_trading_enabled": True,
                "simulation_mode": True,
                "source_overrides": {"alerts": {"paper_only": True}},
            },
        )

        self.assertEqual(preview["acceptance"]["status"], "failed")
        self.assertEqual(preview["acceptance"]["expected_count"], 1)
        self.assertEqual(preview["acceptance"]["passed_count"], 0)
        self.assertEqual(preview["acceptance"]["failed_count"], 1)
        self.assertEqual(preview["acceptance"]["failed_event_count"], 1)
        self.assertEqual(preview["acceptance"]["failed_event_ids"], ["discord_alert:missing"])
        self.assertEqual(preview["acceptance"]["missing_event_count"], 1)
        self.assertEqual(preview["acceptance"]["missing_event_ids"], ["discord_alert:missing"])

    def test_normalize_replay_url_accepts_engine_root_or_full_endpoint(self):
        from simulation_replay import normalize_replay_url

        self.assertEqual(
            normalize_replay_url("http://127.0.0.1:9200"),
            "http://127.0.0.1:9200/api/sentinel-echo/replay/events",
        )
        self.assertEqual(
            normalize_replay_url("http://127.0.0.1:9200/api/sentinel-echo/replay/events"),
            "http://127.0.0.1:9200/api/sentinel-echo/replay/events",
        )


if __name__ == "__main__":
    unittest.main()
