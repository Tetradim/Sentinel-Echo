import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakePanicDb:
    def __init__(self):
        self.settings = {
            "active_broker": "alpaca",
            "auto_trading_enabled": True,
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
        }
        self.runtime = {
            "live_trading_armed": True,
            "live_trading_armed_until": "2099-01-01T00:00:00+00:00",
            "shutdown_triggered": False,
            "shutdown_reason": "",
        }
        self.events = []
        self.trades = []

    async def get_settings(self):
        return dict(self.settings)

    async def update_settings(self, updates):
        self.settings.update(updates)
        return dict(self.settings)

    async def get_runtime_state(self):
        return dict(self.runtime)

    async def update_runtime_state(self, updates):
        self.runtime.update(updates)
        return dict(self.runtime)

    async def insert_operator_event(self, event):
        self.events.append(event)
        return event["id"]

    async def get_trades(self, limit=50):
        return list(self.trades[:limit])


class FakeCancelClient:
    def __init__(self, open_orders=None):
        self.cancelled_order_ids = []
        self.open_orders = list(open_orders or [])
        self.closed = False

    async def list_open_orders(self):
        return list(self.open_orders)

    async def cancel_order(self, order_id):
        self.cancelled_order_ids.append(order_id)
        return {"order_id": order_id, "status": "cancel_requested", "cancel_requested": True}

    async def close(self):
        self.closed = True


class FakeMalformedSettingsPanicDb(FakePanicDb):
    async def get_settings(self):
        return "settings"


class FakeMalformedUpdatePanicDb(FakePanicDb):
    async def update_settings(self, updates):
        self.settings.update(updates)
        return "settings"

    async def update_runtime_state(self, updates):
        self.runtime.update(updates)
        return "runtime"


class PanicStopTests(unittest.TestCase):
    def test_panic_stop_disables_automation_and_records_event(self):
        from routes import operator as operator_route

        db = FakePanicDb()
        operator_route.set_db(db)

        result = asyncio.run(operator_route.panic_stop())

        self.assertFalse(result["auto_trading_enabled"])
        self.assertFalse(result["live_trading_armed"])
        self.assertTrue(result["shutdown_triggered"])
        self.assertEqual(db.events[-1]["severity"], "critical")
        self.assertEqual(db.events[-1]["action"], "panic_stop")

    def test_panic_stop_normalizes_enum_backed_active_broker_in_audit(self):
        from models import BrokerType
        from routes import operator as operator_route

        db = FakePanicDb()
        db.settings["active_broker"] = BrokerType.ALPACA
        operator_route.set_db(db)

        asyncio.run(operator_route.panic_stop())

        self.assertEqual(db.events[-1]["details"]["active_broker"], "alpaca")
        self.assertNotIn("BrokerType", " ".join(db.events[-1]["details"]["warnings"]))

    def test_panic_stop_treats_malformed_settings_as_default_broker(self):
        from routes import operator as operator_route

        db = FakeMalformedSettingsPanicDb()
        operator_route.set_db(db)

        result = asyncio.run(operator_route.panic_stop())

        self.assertFalse(result["auto_trading_enabled"])
        self.assertTrue(result["shutdown_triggered"])
        self.assertEqual(db.events[-1]["details"]["active_broker"], "ibkr")

    def test_panic_stop_uses_requested_safety_state_when_update_responses_are_malformed(self):
        from routes import operator as operator_route

        db = FakeMalformedUpdatePanicDb()
        operator_route.set_db(db)

        result = asyncio.run(operator_route.panic_stop())

        self.assertFalse(result["auto_trading_enabled"])
        self.assertFalse(result["live_trading_armed"])
        self.assertTrue(result["shutdown_triggered"])
        self.assertEqual(result["shutdown_reason"], "panic stop triggered by operator")
        self.assertEqual(db.events[-1]["action"], "panic_stop")

    def test_panic_stop_cancels_pending_live_broker_orders(self):
        from routes import operator as operator_route

        db = FakePanicDb()
        db.trades = [
            {
                "id": "trade-1",
                "status": "pending",
                "order_id": "broker-order-1",
                "broker": "alpaca",
                "simulated": False,
            }
        ]
        fake_client = FakeCancelClient()
        operator_route.set_db(db)

        with patch("order_execution.get_configured_broker_client", return_value=fake_client):
            result = asyncio.run(operator_route.panic_stop())

        self.assertEqual(fake_client.cancelled_order_ids, ["broker-order-1"])
        self.assertTrue(fake_client.closed)
        self.assertEqual(
            result["cancellation_attempts"],
            [
                {
                    "trade_id": "trade-1",
                    "order_id": "broker-order-1",
                    "source": "local_registry",
                    "status": "cancel_requested",
                    "cancel_requested": True,
                }
            ],
        )
        self.assertEqual(db.events[-1]["details"]["cancellation_attempts"], result["cancellation_attempts"])

    def test_panic_stop_cancels_broker_discovered_open_orders_without_local_trade_match(self):
        from routes import operator as operator_route

        db = FakePanicDb()
        fake_client = FakeCancelClient(
            open_orders=[
                {"order_id": "broker-only-order-1", "status": "open", "symbol": "SPY"},
            ]
        )
        operator_route.set_db(db)

        with patch("order_execution.get_configured_broker_client", return_value=fake_client):
            result = asyncio.run(operator_route.panic_stop())

        self.assertEqual(fake_client.cancelled_order_ids, ["broker-only-order-1"])
        self.assertEqual(
            result["cancellation_attempts"],
            [
                {
                    "trade_id": "",
                    "order_id": "broker-only-order-1",
                    "source": "broker_open_orders",
                    "broker_status": "open",
                    "status": "cancel_requested",
                    "cancel_requested": True,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
