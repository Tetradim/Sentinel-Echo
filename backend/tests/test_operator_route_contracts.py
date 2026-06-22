import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def collect_route_contracts(routes, prefix=""):
    contracts = set()
    for route in routes:
        include_context = getattr(route, "include_context", None)
        included_router = getattr(include_context, "included_router", None)
        if included_router is not None:
            nested_prefix = f"{prefix}{getattr(included_router, 'prefix', '')}"
            contracts.update(collect_route_contracts(included_router.routes, nested_prefix))
            continue

        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        method = next(iter(methods - {"HEAD", "OPTIONS"}), "")
        if method:
            contracts.add((method, f"{prefix}{path}"))
    return contracts


class FakeTradingDb:
    def __init__(self):
        self.trade = {
            "id": "trade-1",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "2026-06-26",
            "entry_price": 2.0,
            "current_price": 2.5,
            "quantity": 2,
            "status": "executed",
            "realized_pnl": 0.0,
            "unrealized_pnl": 100.0,
        }
        self.position = {
            "id": "pos-1",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "2026-06-26",
            "entry_price": 2.0,
            "current_price": 2.5,
            "original_quantity": 4,
            "remaining_quantity": 4,
            "realized_pnl": 0.0,
            "status": "open",
            "broker": "ibkr",
            "simulated": True,
            "trade_ids": [],
        }
        self.inserted_trades = []
        self.inserted_alerts = []
        self.inserted_positions = []
        self.inserted_events = []
        self.trade_updates = []
        self.position_updates = []

    async def get_trades(self, limit=50):
        return [dict(self.trade)]

    async def update_trade(self, trade_id, updates):
        self.trade_updates.append((trade_id, updates))
        self.trade.update(updates)

    async def get_position_by_id(self, position_id):
        return dict(self.position) if position_id == self.position["id"] else None

    async def get_positions(self, status=None):
        if status and self.position.get("status") != status:
            return []
        return [dict(self.position)]

    async def update_position(self, position_id, updates):
        self.position_updates.append((position_id, updates))
        if "$set" in updates:
            self.position.update(updates["$set"])
        if "$push" in updates:
            for key, value in updates["$push"].items():
                self.position.setdefault(key, []).append(value)

    async def insert_trade(self, trade):
        self.inserted_trades.append(trade)
        return trade["id"]

    async def insert_alert(self, alert):
        self.inserted_alerts.append(alert)
        return alert["id"]

    async def insert_position(self, position):
        self.inserted_positions.append(position)
        return position["id"]

    async def insert_operator_event(self, event):
        self.inserted_events.append(event)
        return event["id"]

    async def get_operator_events(self, limit=100):
        return list(reversed(self.inserted_events))[:limit]

    async def get_settings(self):
        return {
            "active_broker": "ibkr",
            "simulation_mode": True,
            "auto_shutdown_enabled": False,
        }


class FakeBrokerDb:
    async def get_settings(self):
        return {
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"api_key": "key", "api_secret": "secret"}},
        }


class OperatorRouteContractTests(unittest.TestCase):
    def test_app_exposes_routes_used_by_operator_screens(self):
        from server import app

        routes = collect_route_contracts(app.routes)

        self.assertIn(("POST", "/api/trades/{trade_id}/close"), routes)
        self.assertIn(("PUT", "/api/trades/{trade_id}/price"), routes)
        self.assertIn(("POST", "/api/positions/{position_id}/sell"), routes)
        self.assertIn(("POST", "/api/test-alert"), routes)
        self.assertIn(("POST", "/api/broker/switch/{broker_id}"), routes)
        self.assertIn(("POST", "/api/broker/check/{broker_id}"), routes)
        self.assertIn(("GET", "/api/operator/events"), routes)
        self.assertIn(("POST", "/api/operator/test-alert"), routes)
        self.assertIn(("POST", "/api/operator/simulate-exit"), routes)
        self.assertIn(("GET", "/api/operator/live-readiness"), routes)
        self.assertIn(("POST", "/api/operator/live-arm"), routes)
        self.assertIn(("POST", "/api/operator/live-disarm"), routes)
        self.assertIn(("POST", "/api/operator/panic-stop"), routes)
        self.assertIn(("GET", "/api/operator/reconciliation"), routes)

    def test_operator_test_alert_creates_records_and_event(self):
        from routes import operator as operator_route

        fake_db = FakeTradingDb()
        operator_route.set_db(fake_db)

        response = asyncio.run(operator_route.create_operator_test_alert())

        self.assertEqual(response["message"], "Operator test alert created")
        self.assertEqual(len(fake_db.inserted_alerts), 1)
        self.assertEqual(len(fake_db.inserted_trades), 1)
        self.assertEqual(len(fake_db.inserted_positions), 1)
        self.assertEqual(len(fake_db.inserted_events), 1)
        self.assertEqual(fake_db.inserted_events[0]["category"], "test_lab")
        self.assertEqual(fake_db.inserted_events[0]["action"], "test_alert_created")

    def test_operator_events_return_newest_first_with_limit(self):
        from routes import operator as operator_route

        fake_db = FakeTradingDb()
        operator_route.set_db(fake_db)
        asyncio.run(fake_db.insert_operator_event({"id": "event-1", "timestamp": "1"}))
        asyncio.run(fake_db.insert_operator_event({"id": "event-2", "timestamp": "2"}))

        response = asyncio.run(operator_route.get_operator_events(limit=1))

        self.assertEqual([event["id"] for event in response], ["event-2"])

    def test_operator_simulate_exit_sells_first_open_position_and_logs_event(self):
        from routes import operator as operator_route
        from routes import settings as settings_route
        from routes import trading as trading_route

        fake_db = FakeTradingDb()
        operator_route.set_db(fake_db)
        trading_route.set_db(fake_db)
        settings_route.set_db(fake_db)

        response = asyncio.run(
            operator_route.simulate_exit(
                operator_route.OperatorSimulateExitRequest(exit_price=3.0, sell_percentage=50)
            )
        )

        self.assertEqual(response["position_id"], "pos-1")
        self.assertEqual(response["sold_quantity"], 2)
        self.assertEqual(fake_db.position["remaining_quantity"], 2)
        self.assertEqual(fake_db.inserted_events[-1]["action"], "simulated_exit")

    def test_broker_check_closes_temporary_client(self):
        from routes import brokers as brokers_route

        class FakeBrokerClient:
            def __init__(self):
                self.closed = False

            async def check_connection(self):
                return False

            async def close(self):
                self.closed = True

        fake_client = FakeBrokerClient()
        brokers_route.set_db(FakeBrokerDb())

        with patch("order_execution.get_configured_broker_client", return_value=fake_client):
            response = asyncio.run(brokers_route.check_broker_alias("alpaca"))

        self.assertFalse(response["connected"])
        self.assertTrue(fake_client.closed)

    def test_trade_close_endpoint_updates_status_and_realized_pnl(self):
        from routes import settings as settings_route
        from routes import trading as trading_route

        fake_db = FakeTradingDb()
        trading_route.set_db(fake_db)
        settings_route.set_db(fake_db)

        response = asyncio.run(
            trading_route.close_trade("trade-1", trading_route.CloseTradeRequest(exit_price=3.0))
        )

        self.assertEqual(response["trade_id"], "trade-1")
        self.assertEqual(response["realized_pnl"], 200.0)
        self.assertEqual(fake_db.trade["status"], "closed")
        self.assertEqual(fake_db.trade["exit_price"], 3.0)
        self.assertIsNotNone(fake_db.trade["closed_at"])

    def test_trade_close_endpoint_closes_linked_open_position(self):
        from routes import settings as settings_route
        from routes import trading as trading_route

        fake_db = FakeTradingDb()
        fake_db.position["trade_ids"] = ["trade-1"]
        trading_route.set_db(fake_db)
        settings_route.set_db(fake_db)

        response = asyncio.run(
            trading_route.close_trade("trade-1", trading_route.CloseTradeRequest(exit_price=3.0))
        )

        self.assertEqual(response["position_id"], "pos-1")
        self.assertEqual(response["sold_quantity"], 4)
        self.assertEqual(fake_db.position["status"], "closed")
        self.assertEqual(fake_db.position["remaining_quantity"], 0)
        self.assertEqual(fake_db.position["current_price"], 3.0)
        self.assertEqual(fake_db.position["realized_pnl"], 400.0)
        self.assertEqual(fake_db.trade["status"], "closed")

    def test_trade_price_endpoint_updates_current_price_and_unrealized_pnl(self):
        from routes import trading as trading_route

        fake_db = FakeTradingDb()
        trading_route.set_db(fake_db)

        response = asyncio.run(
            trading_route.update_trade_price(
                "trade-1",
                trading_route.UpdateTradePriceRequest(current_price=3.25),
            )
        )

        self.assertEqual(response["trade_id"], "trade-1")
        self.assertEqual(response["unrealized_pnl"], 250.0)
        self.assertEqual(fake_db.trade["current_price"], 3.25)
        self.assertEqual(fake_db.trade["unrealized_pnl"], 250.0)

    def test_position_sell_endpoint_uses_submitted_exit_price_and_percentage(self):
        from routes import settings as settings_route
        from routes import trading as trading_route

        fake_db = FakeTradingDb()
        trading_route.set_db(fake_db)
        settings_route.set_db(fake_db)

        response = asyncio.run(
            trading_route.sell_position_from_operator(
                "pos-1",
                sell_percentage=50,
                exit_price=3.0,
            )
        )

        self.assertEqual(response["position_id"], "pos-1")
        self.assertEqual(response["sold_quantity"], 2)
        self.assertEqual(response["realized_pnl"], 200.0)
        self.assertEqual(fake_db.position["remaining_quantity"], 2)
        self.assertEqual(fake_db.position["current_price"], 3.0)
        self.assertEqual(fake_db.inserted_trades[0]["exit_price"], 3.0)

    def test_test_alert_endpoint_creates_simulated_records(self):
        from routes import trading as trading_route

        fake_db = FakeTradingDb()
        trading_route.set_db(fake_db)

        response = asyncio.run(trading_route.create_test_alert())

        self.assertEqual(response["message"], "Test alert created")
        self.assertEqual(len(fake_db.inserted_alerts), 1)
        self.assertEqual(len(fake_db.inserted_trades), 1)
        self.assertEqual(len(fake_db.inserted_positions), 1)
        self.assertTrue(fake_db.inserted_alerts[0]["trade_executed"])
        self.assertEqual(fake_db.inserted_trades[0]["status"], "simulated")
        self.assertEqual(fake_db.inserted_positions[0]["status"], "open")
        self.assertEqual(fake_db.inserted_positions[0]["trade_ids"], [fake_db.inserted_trades[0]["id"]])


if __name__ == "__main__":
    unittest.main()
