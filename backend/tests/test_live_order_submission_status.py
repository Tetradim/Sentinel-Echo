import asyncio
import os
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
        self.positions = FakeCollection()


class FakeRuntimeDb:
    def __init__(self):
        self.positions_by_status = {"open": [], "partial": []}
        self.inserted_trades = []
        self.updated_positions = []
        self.runtime_state = {
            "live_trading_armed": True,
            "live_trading_armed_until": "2099-01-01T00:00:00+00:00",
            "shutdown_triggered": False,
        }

    async def get_positions(self, status):
        return self.positions_by_status[status]

    async def insert_trade(self, trade):
        self.inserted_trades.append(trade)
        return trade["id"]

    async def update_position(self, position_id, updates):
        self.updated_positions.append((position_id, updates))
        for positions in self.positions_by_status.values():
            for position in positions:
                if position.get("id") != position_id:
                    continue
                if "$set" in updates:
                    position.update(updates["$set"])
                if "$push" in updates:
                    for key, value in updates["$push"].items():
                        position.setdefault(key, []).append(value)
                return

    async def get_runtime_state(self):
        return dict(self.runtime_state)


class FailingPositionRuntimeDb(FakeRuntimeDb):
    async def get_positions(self, status):
        raise RuntimeError("position store unavailable")


class FakeBrokerClient:
    orders = []

    async def place_order(self, **kwargs):
        self.orders.append(kwargs)
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
    def patch_server(self, server, *, fake_sync_mongo=None, fake_db=None, live_role=True):
        import order_execution

        originals = {
            "USE_SQLITE": server.USE_SQLITE,
            "sync_mongo_db": server.sync_mongo_db,
            "get_db": server.get_db,
            "check_correlation": server.check_correlation,
            "monitor_fill": server.monitor_fill,
            "notify_correlation_block": server.notify_correlation_block,
            "get_configured_broker_client": order_execution.get_configured_broker_client,
            "SENTINEL_ECHO_BOT_ROLE": os.environ.get("SENTINEL_ECHO_BOT_ROLE"),
        }
        if live_role:
            os.environ["SENTINEL_ECHO_BOT_ROLE"] = "live_executioner"
        else:
            os.environ.pop("SENTINEL_ECHO_BOT_ROLE", None)
        server.USE_SQLITE = False
        if fake_sync_mongo is not None:
            server.sync_mongo_db = fake_sync_mongo
        if fake_db is not None:
            server.get_db = lambda: fake_db
        server.check_correlation = allow_correlation
        server.monitor_fill = fake_monitor_fill
        server.notify_correlation_block = fake_notify_correlation_block
        FakeBrokerClient.orders = []
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
        if originals["SENTINEL_ECHO_BOT_ROLE"] is None:
            os.environ.pop("SENTINEL_ECHO_BOT_ROLE", None)
        else:
            os.environ["SENTINEL_ECHO_BOT_ROLE"] = originals["SENTINEL_ECHO_BOT_ROLE"]

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
        self.assertEqual(FakeBrokerClient.orders[0]["price"], 1.25)
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-buy"},
                    {"$set": {"processed": True, "trade_executed": False}},
                )
            ],
        )

    def test_live_buy_is_blocked_when_runtime_is_not_armed(self):
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
        fake_db.runtime_state["live_trading_armed"] = False
        fake_db.runtime_state["live_trading_armed_until"] = ""
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-unarmed",
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

        self.assertEqual(FakeBrokerClient.orders, [])
        self.assertEqual(fake_mongo.trades.inserted, [])
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-unarmed"},
                    {
                        "$set": {
                            "processed": True,
                            "trade_executed": False,
                            "trade_result": "blocked: live trading not armed",
                        }
                    },
                )
            ],
        )

    def test_live_buy_is_blocked_when_sentinel_echo_role_is_not_executioner(self):
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
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db, live_role=False)
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-role-blocked",
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

        self.assertEqual(FakeBrokerClient.orders, [])
        self.assertEqual(fake_mongo.trades.inserted, [])
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-role-blocked"},
                    {
                        "$set": {
                            "processed": True,
                            "trade_executed": False,
                            "trade_result": "blocked: live executioner role disabled",
                        }
                    },
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

    def test_live_exit_is_blocked_when_sentinel_echo_role_is_not_executioner(self):
        from models import Alert, Settings
        import server

        fake_db = FakeRuntimeDb()
        fake_db.positions_by_status["open"] = [
            {
                "id": "pos-role-blocked",
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
        originals = self.patch_server(server, fake_db=fake_db, live_role=False)
        try:
            processed = asyncio.run(
                server.process_exit_alert(
                    Alert(
                        id="alert-sell-role-blocked",
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
        self.assertEqual(FakeBrokerClient.orders, [])
        self.assertEqual(fake_db.inserted_trades, [])

    def test_live_buy_premium_buffer_is_applied_as_cents(self):
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "simulation_mode": False,
            "default_quantity": 1,
            "max_position_size": 1000.0,
            "premium_buffer_enabled": True,
            "premium_buffer_amount": 10.0,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-buffer",
                        ticker="SPY",
                        strike=500.0,
                        option_type="CALL",
                        expiration="6/21",
                        entry_price=5.00,
                    ),
                    {"alert_type": "buy"},
                )
            )
        finally:
            self.restore_server(server, originals)

        self.assertEqual(FakeBrokerClient.orders[0]["price"], 4.90)

    def test_simulated_buy_position_includes_oco_exit_plan_when_guards_are_enabled(self):
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "simulation_mode": True,
            "default_quantity": 2,
            "max_position_size": 1000.0,
            "take_profit_enabled": True,
            "take_profit_percentage": 50.0,
            "stop_loss_enabled": True,
            "stop_loss_percentage": 25.0,
            "trailing_stop_enabled": True,
            "trailing_stop_type": "percent",
            "trailing_stop_percent": 10.0,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-sim-oco",
                        ticker="SPY",
                        strike=500.0,
                        option_type="CALL",
                        expiration="6/21",
                        entry_price=1.20,
                    ),
                    {"alert_type": "buy"},
                )
            )
        finally:
            self.restore_server(server, originals)

        position = fake_mongo.positions.inserted[0]
        plan = position["oco_exit_plan"]
        self.assertTrue(position["oco_exit_protected"])
        self.assertEqual(plan["status"], "armed")
        self.assertEqual(plan["quantity"], 2)
        self.assertEqual(plan["take_profit"]["trigger_price"], 1.80)
        self.assertEqual(plan["stop_loss"]["trigger_price"], 0.90)
        self.assertIn(position["id"], plan["take_profit"]["client_order_id"])
        self.assertIn(position["id"], plan["stop_loss"]["client_order_id"])

    def test_simulated_average_down_updates_matching_position_weighted_average(self):
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "simulation_mode": True,
            "default_quantity": 10,
            "max_position_size": 1000.0,
            "averaging_down_enabled": True,
            "averaging_down_threshold": 10.0,
            "averaging_down_percentage": 50.0,
            "averaging_down_max_buys": 2,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        fake_db.positions_by_status["open"] = [
            {
                "id": "pos-avg",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "CALL",
                "expiration": "6/21",
                "entry_price": 1.00,
                "current_price": 1.00,
                "original_quantity": 4,
                "remaining_quantity": 4,
                "total_cost": 400.0,
                "broker": "alpaca",
                "status": "open",
                "realized_pnl": 0.0,
                "simulated": True,
                "trade_ids": ["entry-trade"],
                "average_down_count": 0,
                "initial_entry_price": None,
                "highest_price": 1.00,
            }
        ]
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-avg-down",
                        ticker="SPY",
                        strike=500.0,
                        option_type="CALL",
                        expiration="6/21",
                        entry_price=0.80,
                        alert_type="average_down",
                    ),
                    {
                        "alert_type": "average_down",
                        "ticker": "SPY",
                        "strike": 500.0,
                        "option_type": "CALL",
                        "expiration": "6/21",
                        "entry_price": 0.80,
                    },
                )
            )
        finally:
            self.restore_server(server, originals)

        self.assertEqual(len(fake_db.inserted_trades), 1)
        trade = fake_db.inserted_trades[0]
        self.assertEqual(trade["side"], "BUY")
        self.assertEqual(trade["quantity"], 2)
        self.assertEqual(trade["status"], "simulated")

        self.assertEqual(fake_db.updated_positions[0][0], "pos-avg")
        update = fake_db.updated_positions[0][1]
        self.assertEqual(update["$set"]["remaining_quantity"], 6)
        self.assertEqual(update["$set"]["original_quantity"], 6)
        self.assertAlmostEqual(update["$set"]["entry_price"], 0.9333333333)
        self.assertEqual(update["$set"]["total_cost"], 560.0)
        self.assertEqual(update["$set"]["average_down_count"], 1)
        self.assertEqual(update["$set"]["initial_entry_price"], 1.00)
        self.assertEqual(update["$push"]["trade_ids"], trade["id"])
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-avg-down"},
                    {"$set": {"processed": True, "trade_executed": True}},
                )
            ],
        )

    def test_paper_shadow_buy_position_includes_oco_exit_plan_when_guards_are_enabled(self):
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "simulation_mode": False,
            "default_quantity": 1,
            "max_position_size": 1000.0,
            "take_profit_enabled": True,
            "take_profit_percentage": 50.0,
            "stop_loss_enabled": True,
            "stop_loss_percentage": 25.0,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-shadow-oco",
                        ticker="SPY",
                        strike=500.0,
                        option_type="CALL",
                        expiration="6/21",
                        entry_price=1.20,
                    ),
                    {"alert_type": "buy", "_source_config": {"paper_shadow": True}},
                )
            )
        finally:
            self.restore_server(server, originals)

        shadow_position = fake_mongo.positions.inserted[0]
        plan = shadow_position["oco_exit_plan"]
        self.assertTrue(shadow_position["simulated"])
        self.assertEqual(shadow_position["broker"], "alpaca:paper_shadow")
        self.assertTrue(shadow_position["oco_exit_protected"])
        self.assertEqual(plan["take_profit"]["trigger_price"], 1.80)
        self.assertEqual(plan["stop_loss"]["trigger_price"], 0.90)

    def test_unarmed_live_buy_does_not_record_paper_shadow_position(self):
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "simulation_mode": False,
            "default_quantity": 1,
            "max_position_size": 1000.0,
            "take_profit_enabled": True,
            "take_profit_percentage": 50.0,
            "stop_loss_enabled": True,
            "stop_loss_percentage": 25.0,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        fake_db.runtime_state["live_trading_armed"] = False
        fake_db.runtime_state["live_trading_armed_until"] = ""
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-shadow-unarmed",
                        ticker="SPY",
                        strike=500.0,
                        option_type="CALL",
                        expiration="6/21",
                        entry_price=1.20,
                    ),
                    {"alert_type": "buy", "_source_config": {"paper_shadow": True}},
                )
            )
        finally:
            self.restore_server(server, originals)

        self.assertEqual(FakeBrokerClient.orders, [])
        self.assertEqual(fake_mongo.trades.inserted, [])
        self.assertEqual(fake_mongo.positions.inserted, [])
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-shadow-unarmed"},
                    {
                        "$set": {
                            "processed": True,
                            "trade_executed": False,
                            "trade_result": "blocked: live trading not armed",
                        }
                    },
                )
            ],
        )

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
                    {
                        "$set": {
                            "processed": True,
                            "trade_executed": False,
                            "trade_result": "blocked: Risk controls unavailable",
                        }
                    },
                )
            ],
        )

    def test_live_buy_blocks_when_position_store_is_unavailable_for_risk_check(self):
        from models import Alert
        import risk
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
        fake_db = FailingPositionRuntimeDb()
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        server.check_correlation = risk.check_correlation
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-risk-db-unavailable",
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

        self.assertEqual(FakeBrokerClient.orders, [])
        self.assertEqual(fake_mongo.trades.inserted, [])
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-risk-db-unavailable"},
                    {
                        "$set": {
                            "processed": True,
                            "trade_executed": False,
                            "trade_result": "blocked: Risk controls unavailable",
                        }
                    },
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
