import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeSimulationEngineDb:
    def __init__(self):
        self.runtime_updates = []

    async def get_settings(self):
        return {
            "auto_trading_enabled": False,
            "simulation_mode": True,
            "source_overrides": {"alerts": {"paper_only": True}},
        }

    async def update_runtime_state(self, update):
        self.runtime_updates.append(update)
        return dict(update)


class SimulationEngineRouteTests(unittest.TestCase):
    def test_replay_preview_caches_acceptance_summary_for_readiness(self):
        from routes import simulation_engine as simulation_engine_route

        fake_db = FakeSimulationEngineDb()
        simulation_engine_route.set_db(fake_db)
        replay = {
            "contract_version": "simulation.consolidation.replay.v1",
            "expected_results": {
                "discord_alert:one": {
                    "parsed": {"ticker": "QQQ"},
                    "would_request_trade": True,
                }
            },
            "events": [
                {
                    "event_id": "discord_alert:one",
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

        async def fake_fetch(**kwargs):
            return replay

        with patch("routes.simulation_engine.fetch_engine_replay", side_effect=fake_fetch):
            response = asyncio.run(
                simulation_engine_route.preview_simulation_engine_replay({"replay_url": "http://127.0.0.1:9200"})
            )

        self.assertEqual(response["acceptance"]["status"], "failed")
        self.assertEqual(fake_db.runtime_updates[-1]["simulation_replay_acceptance_status"], "failed")
        self.assertEqual(fake_db.runtime_updates[-1]["simulation_replay_acceptance_failed_count"], 1)
        self.assertEqual(fake_db.runtime_updates[-1]["simulation_replay_acceptance_failed_event_count"], 1)
        self.assertEqual(
            fake_db.runtime_updates[-1]["simulation_replay_acceptance_failed_event_ids"],
            ["discord_alert:one"],
        )
        self.assertEqual(fake_db.runtime_updates[-1]["simulation_replay_acceptance_expected_count"], 1)
        self.assertIn("simulation_replay_acceptance_updated_at", fake_db.runtime_updates[-1])
        self.assertEqual(
            fake_db.runtime_updates[-1]["simulation_replay_acceptance_replay_url"],
            "http://127.0.0.1:9200/api/consolidation/replay/events",
        )

    def test_replay_preview_caches_missing_expected_event_ids_for_readiness(self):
        from routes import simulation_engine as simulation_engine_route

        fake_db = FakeSimulationEngineDb()
        simulation_engine_route.set_db(fake_db)
        replay = {
            "contract_version": "simulation.consolidation.replay.v1",
            "expected_results": {
                "discord_alert:missing": {
                    "parsed": {"ticker": "SPY"},
                    "would_request_trade": True,
                }
            },
            "events": [],
        }

        async def fake_fetch(**kwargs):
            return replay

        with patch("routes.simulation_engine.fetch_engine_replay", side_effect=fake_fetch):
            response = asyncio.run(
                simulation_engine_route.preview_simulation_engine_replay({"replay_url": "http://127.0.0.1:9200"})
            )

        self.assertEqual(response["acceptance"]["missing_event_count"], 1)
        self.assertEqual(response["acceptance"]["missing_event_ids"], ["discord_alert:missing"])
        self.assertEqual(response["acceptance"]["failed_event_ids"], ["discord_alert:missing"])
        self.assertEqual(
            fake_db.runtime_updates[-1]["simulation_replay_acceptance_missing_event_count"],
            1,
        )
        self.assertEqual(
            fake_db.runtime_updates[-1]["simulation_replay_acceptance_missing_event_ids"],
            ["discord_alert:missing"],
        )
        self.assertEqual(
            fake_db.runtime_updates[-1]["simulation_replay_acceptance_failed_event_ids"],
            ["discord_alert:missing"],
        )

    def test_replay_preview_accepts_request_body_expectations_for_readiness_proof(self):
        from routes import simulation_engine as simulation_engine_route

        fake_db = FakeSimulationEngineDb()
        simulation_engine_route.set_db(fake_db)
        replay = {
            "contract_version": "simulation.consolidation.replay.v1",
            "events": [
                {
                    "event_id": "discord_alert:one",
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

        async def fake_fetch(**kwargs):
            return replay

        body = {
            "replay_url": "http://127.0.0.1:9200",
            "expected_results": {
                "discord_alert:one": {
                    "parsed": {"ticker": "SPY", "alert_type": "buy"},
                    "would_insert_alert": True,
                    "would_request_trade": False,
                    "execution_reason": "auto trading disabled",
                }
            },
        }
        with patch("routes.simulation_engine.fetch_engine_replay", side_effect=fake_fetch):
            response = asyncio.run(simulation_engine_route.preview_simulation_engine_replay(body))

        self.assertEqual(response["acceptance"]["status"], "passed")
        self.assertEqual(response["acceptance"]["expected_count"], 1)
        self.assertEqual(fake_db.runtime_updates[-1]["simulation_replay_acceptance_status"], "passed")
        self.assertEqual(fake_db.runtime_updates[-1]["simulation_replay_acceptance_passed_count"], 1)


if __name__ == "__main__":
    unittest.main()
