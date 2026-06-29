import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeAlertDb:
    def __init__(self):
        self.updated = []

    async def update_alert(self, alert_id, updates):
        self.updated.append((alert_id, updates))


class FakeCollection:
    def __init__(self):
        self.updated = []

    def update_one(self, query, update):
        self.updated.append((query, update))


class FakeMongo:
    def __init__(self):
        self.alerts = FakeCollection()


class ServerAlertUpdateTests(unittest.TestCase):
    def test_alert_status_updates_use_database_abstraction(self):
        import server

        db = FakeAlertDb()
        asyncio.run(
            server.update_alert_status(
                "alert-1",
                {"processed": True, "trade_executed": False},
                db=db,
            )
        )

        self.assertEqual(
            db.updated,
            [("alert-1", {"processed": True, "trade_executed": False})],
        )

    def test_alert_status_updates_fallback_to_sync_mongo_for_legacy_callers(self):
        import server

        fake_mongo = FakeMongo()
        originals = {
            "USE_SQLITE": server.USE_SQLITE,
            "sync_mongo_db": server.sync_mongo_db,
            "get_db": server.get_db,
        }
        try:
            server.USE_SQLITE = False
            server.sync_mongo_db = fake_mongo
            server.get_db = lambda: object()

            asyncio.run(
                server.update_alert_status(
                    "alert-2",
                    {"processed": True, "trade_executed": True},
                )
            )
        finally:
            server.USE_SQLITE = originals["USE_SQLITE"]
            server.sync_mongo_db = originals["sync_mongo_db"]
            server.get_db = originals["get_db"]

        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-2"},
                    {"$set": {"processed": True, "trade_executed": True}},
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
