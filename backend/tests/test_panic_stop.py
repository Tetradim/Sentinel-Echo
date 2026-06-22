import asyncio
import sys
import unittest
from pathlib import Path


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


class FakeMalformedSettingsPanicDb(FakePanicDb):
    async def get_settings(self):
        return "settings"


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


if __name__ == "__main__":
    unittest.main()
