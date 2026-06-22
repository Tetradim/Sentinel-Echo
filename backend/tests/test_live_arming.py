import asyncio
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeArmDb:
    def __init__(self):
        self.runtime = {
            "live_trading_armed": False,
            "live_trading_armed_until": "",
            "live_trading_armed_by": "",
            "live_trading_arm_reason": "",
            "shutdown_triggered": False,
        }
        self.events = []

    async def get_runtime_state(self):
        return dict(self.runtime)

    async def update_runtime_state(self, updates):
        self.runtime.update(updates)
        return dict(self.runtime)

    async def insert_operator_event(self, event):
        self.events.append(event)
        return event["id"]


class FakeMalformedRuntimeUpdateDb(FakeArmDb):
    async def update_runtime_state(self, updates):
        self.runtime.update(updates)
        return "runtime"


class LiveArmingTests(unittest.TestCase):
    def test_default_runtime_state_is_unarmed(self):
        from database.abstraction import _default_runtime_state

        state = _default_runtime_state()

        self.assertFalse(state["live_trading_armed"])
        self.assertEqual(state["live_trading_armed_until"], "")

    def test_arm_live_trading_requires_confirmation(self):
        from live_arming import arm_live_trading

        db = FakeArmDb()

        with self.assertRaises(ValueError):
            asyncio.run(
                arm_live_trading(
                    db,
                    duration_minutes=15,
                    confirmation="wrong",
                    readiness={"ready_for_live": True, "blocking_issues": []},
                )
            )

        self.assertFalse(db.runtime["live_trading_armed"])

    def test_arm_live_trading_rejects_malformed_duration(self):
        from live_arming import arm_live_trading

        db = FakeArmDb()

        with self.assertRaises(ValueError):
            asyncio.run(
                arm_live_trading(
                    db,
                    duration_minutes="15",
                    confirmation="ARM LIVE TRADING",
                    readiness={"ready_for_live": True, "blocking_issues": []},
                )
            )

        self.assertFalse(db.runtime["live_trading_armed"])
        self.assertEqual(db.events, [])

    def test_arm_and_disarm_live_trading_updates_runtime_and_audit(self):
        from live_arming import arm_live_trading, disarm_live_trading, is_live_trading_armed

        db = FakeArmDb()
        armed = asyncio.run(
            arm_live_trading(
                db,
                duration_minutes=15,
                confirmation="ARM LIVE TRADING",
                readiness={"ready_for_live": True, "blocking_issues": []},
                operator="tester",
                reason="integration test",
            )
        )

        self.assertTrue(armed["live_trading_armed"])
        self.assertTrue(is_live_trading_armed(armed))
        self.assertEqual(db.events[-1]["action"], "live_trading_armed")

        disarmed = asyncio.run(disarm_live_trading(db, operator="tester"))

        self.assertFalse(disarmed["live_trading_armed"])
        self.assertEqual(db.events[-1]["action"], "live_trading_disarmed")

    def test_malformed_runtime_state_is_not_armed(self):
        from live_arming import is_live_trading_armed

        self.assertFalse(is_live_trading_armed("runtime"))

    def test_non_boolean_runtime_armed_flag_is_not_armed(self):
        from live_arming import is_live_trading_armed

        runtime = {
            "live_trading_armed": "true",
            "live_trading_armed_until": "2099-01-01T00:00:00+00:00",
        }

        self.assertFalse(is_live_trading_armed(runtime))

    def test_arm_live_trading_returns_requested_armed_state_when_update_response_is_malformed(self):
        from live_arming import arm_live_trading, is_live_trading_armed

        db = FakeMalformedRuntimeUpdateDb()

        armed = asyncio.run(
            arm_live_trading(
                db,
                duration_minutes=15,
                confirmation="ARM LIVE TRADING",
                readiness={"ready_for_live": True, "blocking_issues": []},
                operator="tester",
                reason="malformed response test",
            )
        )

        self.assertTrue(armed["live_trading_armed"])
        self.assertTrue(is_live_trading_armed(armed))
        self.assertEqual(armed["live_trading_armed_by"], "tester")
        self.assertEqual(db.events[-1]["action"], "live_trading_armed")

    def test_arm_live_trading_treats_malformed_readiness_as_blocked(self):
        from live_arming import arm_live_trading

        db = FakeArmDb()

        with self.assertRaises(RuntimeError):
            asyncio.run(
                arm_live_trading(
                    db,
                    duration_minutes=15,
                    confirmation="ARM LIVE TRADING",
                    readiness="ready",
                    operator="tester",
                )
            )

        self.assertFalse(db.runtime["live_trading_armed"])
        self.assertEqual(db.events[-1]["action"], "live_trading_arm_blocked")

    def test_disarm_live_trading_returns_requested_unarmed_state_when_update_response_is_malformed(self):
        from live_arming import disarm_live_trading

        db = FakeMalformedRuntimeUpdateDb()
        db.runtime["live_trading_armed"] = True

        disarmed = asyncio.run(disarm_live_trading(db, operator="tester"))

        self.assertFalse(disarmed["live_trading_armed"])
        self.assertEqual(disarmed["live_trading_armed_until"], "")
        self.assertEqual(disarmed["live_trading_armed_by"], "tester")
        self.assertEqual(db.events[-1]["action"], "live_trading_disarmed")


if __name__ == "__main__":
    unittest.main()
