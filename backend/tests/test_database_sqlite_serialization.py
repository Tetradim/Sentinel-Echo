import os
import pathlib
import sys
import tempfile
import unittest
from datetime import datetime, timezone


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class SQLiteSerializationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
