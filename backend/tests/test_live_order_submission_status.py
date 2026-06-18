import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeCollection:
    def __init__(self, document=None):
        self.document = document
        self.inserted = []
        self.updated = []

    def find_one(self, query):
        return self.document

    def insert_one(self, document):
        self.inserted.append(document)

    def update_one(self, query, update):
        self.updated.append((query, update))


class FakeSyncMongo:
    def __init__(self, settings):
        self.settings = FakeCollection(settings)
        self.trades = FakeCollection()
        self.alerts = FakeCollection()


class FakeRuntimeDb:
    def __init__(self):
        self.positions_by_status = {"open": [], "partial": []}
        self.inserted_trades = []

    async def get_positions(self, status):
        return self.positions_by_status[status]

    async def insert_trade(self, trade):
        self.inserted_trades.append(trade)
        return trade["id"]


class FakeBrokerClient:
    async def place_order(self, **kwargs):
        return {"order_id": "live-order-1"}

    async def get_order_status(self, order_id):
        return {"status": "pending"}


async def allow_correlation(**kwargs):
    return True, ""


async def fail_correlation(**kwargs):
    raise RuntimeError("risk database unavailable")


async def fake_monitor_fill(**kwargs):
    return None


async def fake_notify_correlation_block(**kwargs):
    return None


class LiveOrderSubmissionStatusTests(unittest.TestCase):
    def patch_server(self, server, *, fake_sync_mongo=None, fake_db=None):
        import order_execution

        originals = {
            "USE_SQLITE": server.USE_SQLITE,
            "sync_mongo_db": server.sync_mongo_db,
            "get_db": server.get_db,
            "check_correlation": server.check_correlation,
            "monitor_fill": server.monitor_fill,
            "notify_correlation_block": server.notify_correlation_block,
            "get_configured_broker_client": order_execution.get_configured_broker_client,
        }
        server.USE_SQLITE = False
        if fake_sync_mongo is not None:
            server.sync_mongo_db = fake_sync_mongo
        if fake_db is not None:
            server.get_db = lambda: fake_db
        server.check_correlation = allow_correlation
        server.monitor_fill = fake_monitor_fill
        server.notify_correlation_block = fake_notify_correlation_block
        order_execution.get_configured_broker_client = lambda *args, **kwargs: FakeBrokerClient()
        return originals

    def restore_server(self, server, originals):
        import order_execution

        server.USE_SQLITE = originals["USE_SQLITE"]
        server.sync_mongo_db = originals["sync_mongo_db"]
        server.get_db = originals["get_db"]
        server.check_correlation = originals["check_correlation"]
        server.monitor_fill = originals["monitor_fill"]
        server.notify_correlation_block = originals["notify_correlation_block"]
        order_execution.get_configured_broker_client = originals["get_configured_broker_client"]

    def test_live_buy_order_submission_does_not_mark_alert_executed_before_fill(self):
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "simulation_mode": False,
            "default_quantity": 1,
            "max_position_size": 1000.0,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-buy",
                        ticker="SPY",
                        strike=500.0,
                        option_type="CALL",
                        expiration="6/21",
                        entry_price=1.25,
                    ),
                    {"alert_type": "buy"},
                )
            )
        finally:
            self.restore_server(server, originals)

        self.assertEqual(fake_mongo.trades.inserted[0]["status"], "pending")
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-buy"},
                    {"$set": {"processed": True, "trade_executed": False}},
                )
            ],
        )

    def test_live_exit_order_submission_returns_not_executed_before_fill(self):
        from models import Alert, Settings
        import server

        fake_db = FakeRuntimeDb()
        fake_db.positions_by_status["open"] = [
            {
                "id": "pos-live",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "CALL",
                "expiration": "6/21",
                "entry_price": 1.00,
                "current_price": 1.00,
                "original_quantity": 2,
                "remaining_quantity": 2,
                "total_cost": 200.0,
                "broker": "alpaca",
                "status": "open",
                "realized_pnl": 0.0,
                "simulated": False,
                "trade_ids": ["entry-trade"],
            }
        ]
        originals = self.patch_server(server, fake_db=fake_db)
        try:
            processed = asyncio.run(
                server.process_exit_alert(
                    Alert(
                        id="alert-sell",
                        ticker="SPY",
                        strike=500.0,
                        option_type="CALL",
                        expiration="6/21",
                        entry_price=1.50,
                        alert_type="sell",
                        sell_percentage=50.0,
                    ),
                    {
                        "alert_type": "sell",
                        "ticker": "SPY",
                        "strike": 500.0,
                        "option_type": "CALL",
                        "expiration": "6/21",
                        "entry_price": 1.50,
                        "sell_percentage": 50.0,
                    },
                    Settings(
                        simulation_mode=False,
                        active_broker="alpaca",
                        broker_configs={"alpaca": {"broker_type": "alpaca"}},
                    ),
                    {
                        "simulation_mode": False,
                        "active_broker": "alpaca",
                        "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
                    },
                    source_config={},
                )
            )
        finally:
            self.restore_server(server, originals)

        self.assertFalse(processed)
        self.assertEqual(fake_db.inserted_trades[0]["status"], "pending")
        self.assertEqual(fake_db.inserted_trades[0]["order_id"], "live-order-1")

    def test_live_buy_blocks_when_correlation_check_fails(self):
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "simulation_mode": False,
            "default_quantity": 1,
            "max_position_size": 1000.0,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        server.check_correlation = fail_correlation
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-risk-fail",
                        ticker="SPY",
                        strike=500.0,
                        option_type="CALL",
                        expiration="6/21",
                        entry_price=1.25,
                    ),
                    {"alert_type": "buy"},
                )
            )
        finally:
            self.restore_server(server, originals)

        self.assertEqual(fake_mongo.trades.inserted, [])
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-risk-fail"},
                    {"$set": {"processed": True, "trade_executed": False}},
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
