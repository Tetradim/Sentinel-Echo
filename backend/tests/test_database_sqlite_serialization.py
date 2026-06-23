import os
import asyncio
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timezone


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class SQLiteSerializationTests(unittest.TestCase):
    def test_sqlite_connections_use_wal_and_busy_timeout(self):
        sqlite_source = (BACKEND_DIR / "database_sqlite.py").read_text()
        abstraction_source = (BACKEND_DIR / "database" / "abstraction.py").read_text()

        self.assertIn("timeout=30", sqlite_source)
        self.assertIn("PRAGMA busy_timeout=30000", sqlite_source)
        self.assertIn("PRAGMA journal_mode=WAL", sqlite_source)
        self.assertIn("timeout=30", abstraction_source)
        self.assertIn("PRAGMA journal_mode=WAL", abstraction_source)

    def test_insert_alert_accepts_pydantic_model_dump_with_datetime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "test.sqlite3"
            os.environ["DATABASE_PATH"] = str(db_path)

            import database_sqlite
            from models import Alert

            database_sqlite.DATABASE_PATH = str(db_path)
            database_sqlite.init_database()

            alert = Alert(
                ticker="SPY",
                strike=738,
                option_type="PUT",
                expiration="6/18/2026",
                entry_price=0.6,
                alert_type="buy",
                raw_message="$SPY\n$738 PUTS\nEXPIRATION 6/18/2026\n$.6 Entry",
                timestamp=datetime(2026, 6, 19, 18, 2, tzinfo=timezone.utc),
            )

            alert_id = database_sqlite.insert_alert(alert.model_dump())
            alerts = database_sqlite.get_alerts()

        self.assertEqual(alert_id, alert.id)
        self.assertEqual(alerts[0]["ticker"], "SPY")
        self.assertEqual(alerts[0]["timestamp"], "2026-06-19T18:02:00+00:00")

    def test_sqlite_runtime_state_persists_simulation_replay_acceptance(self):
        async def run_case():
            from database.abstraction import SQLiteDatabase

            with tempfile.TemporaryDirectory() as temp_dir:
                db_path = pathlib.Path(temp_dir) / "runtime.sqlite3"
                database = SQLiteDatabase(str(db_path))
                await database.update_runtime_state(
                    {
                        "simulation_replay_acceptance_status": "failed",
                        "simulation_replay_acceptance_expected_count": 3,
                        "simulation_replay_acceptance_passed_count": 1,
                        "simulation_replay_acceptance_failed_count": 2,
                        "simulation_replay_acceptance_failed_event_count": 2,
                        "simulation_replay_acceptance_failed_event_ids": [
                            "discord_alert:bad-one",
                            "discord_alert:missing",
                        ],
                        "simulation_replay_acceptance_missing_event_count": 1,
                        "simulation_replay_acceptance_missing_event_ids": [
                            "discord_alert:missing"
                        ],
                        "simulation_replay_acceptance_updated_at": "2026-06-23T01:11:00Z",
                        "simulation_replay_acceptance_replay_url": "http://127.0.0.1:9200/api/consolidation/replay/events",
                    }
                )
                return await database.get_runtime_state()

        runtime = asyncio.run(run_case())

        self.assertEqual(runtime["simulation_replay_acceptance_status"], "failed")
        self.assertEqual(runtime["simulation_replay_acceptance_expected_count"], 3)
        self.assertEqual(runtime["simulation_replay_acceptance_passed_count"], 1)
        self.assertEqual(runtime["simulation_replay_acceptance_failed_count"], 2)
        self.assertEqual(runtime["simulation_replay_acceptance_failed_event_count"], 2)
        self.assertEqual(
            runtime["simulation_replay_acceptance_failed_event_ids"],
            ["discord_alert:bad-one", "discord_alert:missing"],
        )
        self.assertEqual(runtime["simulation_replay_acceptance_missing_event_count"], 1)
        self.assertEqual(
            runtime["simulation_replay_acceptance_missing_event_ids"],
            ["discord_alert:missing"],
        )
        self.assertEqual(
            runtime["simulation_replay_acceptance_replay_url"],
            "http://127.0.0.1:9200/api/consolidation/replay/events",
        )


if __name__ == "__main__":
    unittest.main()
