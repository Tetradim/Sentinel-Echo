import asyncio
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


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
        self.trade_updates = []
        self.position_updates = []

    async def get_trades(self, limit=50):
        return [dict(self.trade)]

    async def update_trade(self, trade_id, updates):
        self.trade_updates.append((trade_id, updates))
        self.trade.update(updates)

    async def get_position_by_id(self, position_id):
        return dict(self.position) if position_id == self.position["id"] else None

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

    async def get_settings(self):
        return {
            "active_broker": "ibkr",
            "simulation_mode": True,
            "auto_shutdown_enabled": False,
        }


class OperatorRouteContractTests(unittest.TestCase):
    def test_app_exposes_routes_used_by_operator_screens(self):
        from server import app

        routes = {
            (next(iter(route.methods - {"HEAD", "OPTIONS"}), ""), route.path)
            for route in app.routes
            if hasattr(route, "methods")
        }

        self.assertIn(("POST", "/api/trades/{trade_id}/close"), routes)
        self.assertIn(("PUT", "/api/trades/{trade_id}/price"), routes)
        self.assertIn(("POST", "/api/positions/{position_id}/sell"), routes)
        self.assertIn(("POST", "/api/broker/switch/{broker_id}"), routes)
        self.assertIn(("POST", "/api/broker/check/{broker_id}"), routes)

    def test_trade_close_endpoint_updates_status_and_realized_pnl(self):
        from routes import trading as trading_route

        fake_db = FakeTradingDb()
        trading_route.set_db(fake_db)

        response = asyncio.run(
            trading_route.close_trade("trade-1", trading_route.CloseTradeRequest(exit_price=3.0))
        )

        self.assertEqual(response["trade_id"], "trade-1")
        self.assertEqual(response["realized_pnl"], 200.0)
        self.assertEqual(fake_db.trade["status"], "closed")
        self.assertEqual(fake_db.trade["exit_price"], 3.0)
        self.assertIsNotNone(fake_db.trade["closed_at"])

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


if __name__ == "__main__":
    unittest.main()
