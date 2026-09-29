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
    def test_default_settings_enable_auto_trading_while_runtime_stays_unarmed(self):
        from database.abstraction import _default_runtime_state, _default_settings
        from models import Settings

        settings = _default_settings()
        runtime = _default_runtime_state()

        self.assertTrue(Settings().auto_trading_enabled)
        self.assertTrue(settings["auto_trading_enabled"])
        self.assertTrue(runtime["auto_trading_enabled"])
        self.assertFalse(runtime["live_trading_armed"])

    def test_sqlite_connections_use_wal_and_busy_timeout(self):
        sqlite_source = (BACKEND_DIR / "database_sqlite.py").read_text()
        abstraction_source = (BACKEND_DIR / "database" / "abstraction.py").read_text()

        self.assertIn("timeout=30", sqlite_source)
        self.assertIn("PRAGMA busy_timeout=30000", sqlite_source)
        self.assertIn("PRAGMA journal_mode=WAL", sqlite_source)
        self.assertIn("timeout=30", abstraction_source)
        self.assertIn("PRAGMA journal_mode=WAL", abstraction_source)

    def test_legacy_sqlite_reader_backfills_new_exit_defaults(self):
        previous_database_path = os.environ.get("DATABASE_PATH")
        previous_module_database_path = None
        if "database_sqlite" in sys.modules:
            previous_module_database_path = getattr(sys.modules["database_sqlite"], "DATABASE_PATH", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "legacy-settings.sqlite3"
            try:
                os.environ["DATABASE_PATH"] = str(db_path)

                import database_sqlite

                database_sqlite.DATABASE_PATH = str(db_path)
                database_sqlite.init_database()
                with database_sqlite.get_connection() as conn:
                    conn.execute(
                        "UPDATE settings SET data = ? WHERE id = ?",
                        ('{"active_broker":"alpaca"}', "main_settings"),
                    )
                    conn.commit()
                settings = database_sqlite.get_settings()
            finally:
                if previous_database_path is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = previous_database_path
                if "database_sqlite" in sys.modules:
                    if previous_module_database_path is not None:
                        sys.modules["database_sqlite"].DATABASE_PATH = previous_module_database_path
                    else:
                        from database_paths import configured_database_path

                        sys.modules["database_sqlite"].DATABASE_PATH = configured_database_path()

        self.assertEqual(settings["active_broker"], "alpaca")
        self.assertTrue(settings["reversal_exit_enabled"])
        self.assertTrue(settings["adaptive_trailing_enabled"])
        self.assertTrue(settings["zero_dte_liquidation_enabled"])
        self.assertTrue(settings["coordinated_exit_enabled"])
        self.assertTrue(settings["post_exit_telemetry_enabled"])
        self.assertEqual(settings["post_exit_telemetry_minutes"], 60)
        self.assertTrue(settings["risk_budget_sizing_enabled"])
        self.assertEqual(settings["max_loss_per_trade"], 100.0)
        self.assertEqual(settings["coordinated_normal_stop_loss_percent"], 35.0)
        self.assertEqual(settings["coordinated_high_risk_stop_loss_percent"], 50.0)
        self.assertFalse(settings["take_profit_enabled"])
        self.assertFalse(settings["stop_loss_enabled"])
        self.assertFalse(settings["trailing_stop_enabled"])

    def test_insert_alert_accepts_pydantic_model_dump_with_datetime(self):
        previous_database_path = os.environ.get("DATABASE_PATH")
        previous_module_database_path = None
        if "database_sqlite" in sys.modules:
            previous_module_database_path = getattr(sys.modules["database_sqlite"], "DATABASE_PATH", None)
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = pathlib.Path(temp_dir) / "test.sqlite3"
            try:
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
            finally:
                if previous_database_path is None:
                    os.environ.pop("DATABASE_PATH", None)
                else:
                    os.environ["DATABASE_PATH"] = previous_database_path
                if "database_sqlite" in sys.modules:
                    if previous_module_database_path is not None:
                        sys.modules["database_sqlite"].DATABASE_PATH = previous_module_database_path
                    else:
                        from database_paths import configured_database_path

                        sys.modules["database_sqlite"].DATABASE_PATH = configured_database_path()

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
                        "simulation_replay_acceptance_replay_url": "http://127.0.0.1:9200/api/sentinel-echo/replay/events",
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
            "http://127.0.0.1:9200/api/sentinel-echo/replay/events",
        )

    def test_sqlite_positions_persist_contract_fields_as_queryable_columns(self):
        async def run_case():
            import aiosqlite
            from database.abstraction import SQLiteDatabase

            with tempfile.TemporaryDirectory() as temp_dir:
                db_path = pathlib.Path(temp_dir) / "positions.sqlite3"
                database = SQLiteDatabase(str(db_path))
                await database.insert_position(
                    {
                        "id": "position-alpaca-spy-260621-c-500",
                        "ticker": "SPY",
                        "strike": 500.0,
                        "option_type": "CALL",
                        "expiration": "6/21/2026",
                        "entry_price": 1.25,
                        "current_price": 1.30,
                        "original_quantity": 2,
                        "remaining_quantity": 2,
                        "broker": "alpaca",
                        "status": "open",
                        "opened_at": "2026-06-19T18:02:00+00:00",
                        "unrealized_pnl": 10.0,
                    }
                )
                async with aiosqlite.connect(db_path) as conn:
                    conn.row_factory = aiosqlite.Row
                    async with conn.execute(
                        """SELECT ticker, strike, option_type, expiration, remaining_quantity, broker
                           FROM positions
                           WHERE id = ?""",
                        ("position-alpaca-spy-260621-c-500",),
                    ) as cur:
                        row = await cur.fetchone()
                return dict(row)

        row = asyncio.run(run_case())

        self.assertEqual(row["ticker"], "SPY")
        self.assertEqual(row["strike"], 500.0)
        self.assertEqual(row["option_type"], "CALL")
        self.assertEqual(row["expiration"], "6/21/2026")
        self.assertEqual(row["remaining_quantity"], 2)
        self.assertEqual(row["broker"], "alpaca")

    def test_concurrent_position_pushes_do_not_lose_trade_links(self):
        async def run_case():
            from database.abstraction import SQLiteDatabase

            with tempfile.TemporaryDirectory() as temp_dir:
                db_path = pathlib.Path(temp_dir) / "position-updates.sqlite3"
                database = SQLiteDatabase(str(db_path))
                position_id = "position-alpaca-tsla-260928-p-355"
                await database.insert_position(
                    {
                        "id": position_id,
                        "ticker": "TSLA",
                        "strike": 355.0,
                        "option_type": "PUT",
                        "expiration": "9/28/2026",
                        "remaining_quantity": 2,
                        "status": "open",
                        "trade_ids": [],
                    }
                )

                trade_ids = [f"trade-{index}" for index in range(40)]
                await asyncio.gather(
                    *(
                        database.update_position(
                            position_id,
                            {"$push": {"trade_ids": trade_id}},
                        )
                        for trade_id in trade_ids
                    )
                )
                positions = await database.get_positions()
                return next(position for position in positions if position["id"] == position_id)

        position = asyncio.run(run_case())

        self.assertCountEqual(position["trade_ids"], [f"trade-{index}" for index in range(40)])


if __name__ == "__main__":
    unittest.main()
