import asyncio
import pathlib
import sys
import unittest
from unittest.mock import patch


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeDb:
    def __init__(self):
        self.trade_updates = []
        self.positions = {}
        self.inserted_positions = []

    async def update_trade(self, trade_id, updates):
        self.trade_updates.append((trade_id, updates))

    async def insert_position(self, position):
        self.positions[position["id"]] = position
        self.inserted_positions.append(position)
        return position["id"]

    async def get_position_by_id(self, position_id):
        return self.positions.get(position_id)

    async def update_position(self, position_id, updates):
        position = dict(self.positions[position_id])
        if "$set" in updates:
            position.update(updates["$set"])
        if "$push" in updates:
            for key, value in updates["$push"].items():
                position.setdefault(key, []).append(value)
        self.positions[position_id] = position


class BrokerWithoutStatus:
    pass


class BrokerWithFilledStatus:
    async def get_order_status(self, order_id):
        return {"status": "filled", "filled_qty": 2, "avg_fill_price": 1.25}


class BrokerWithTransientErrorThenFilledStatus:
    def __init__(self):
        self.status_calls = 0

    async def get_order_status(self, order_id):
        self.status_calls += 1
        if self.status_calls == 1:
            return {
                "status": "error",
                "filled_qty": 0,
                "avg_fill_price": 0.0,
                "reason": "temporary broker status timeout",
            }
        return {"status": "filled", "filled_qty": 2, "avg_fill_price": 1.25}


class BrokerThatCancelsTimedOutOrder:
    def __init__(self):
        self.cancelled = []
        self.status_calls = 0

    async def get_order_status(self, order_id):
        self.status_calls += 1
        if self.cancelled:
            return {"status": "cancelled", "filled_qty": 0, "avg_fill_price": 0.0, "reason": "cancelled"}
        return {"status": "new", "filled_qty": 0, "avg_fill_price": 0.0}

    async def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        return {"status": "cancel_requested", "cancel_requested": True}


class BrokerThatFillsDuringCancelFollowup:
    def __init__(self):
        self.cancelled = []

    async def get_order_status(self, order_id):
        if self.cancelled:
            return {"status": "filled", "filled_qty": 2, "avg_fill_price": 1.2}
        return {"status": "new", "filled_qty": 0, "avg_fill_price": 0.0}

    async def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        return {"status": "cancel_failed", "cancel_requested": False, "reason": "order already filled"}


class BrokerThatNeverConfirmsSell:
    def __init__(self):
        self.cancelled = []
        self.status_calls = 0

    async def get_order_status(self, order_id):
        self.status_calls += 1
        return {"status": "new", "filled_qty": 0, "avg_fill_price": 0.0}

    async def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        return {"status": "cancel_requested", "cancel_requested": True}


class BrokerThatFillsAfterConfirmationWindow:
    def __init__(self):
        self.status_calls = 0

    async def get_order_status(self, order_id):
        self.status_calls += 1
        if self.status_calls == 1:
            return {"status": "new", "filled_qty": 0, "avg_fill_price": 0.0}
        return {"status": "filled", "filled_qty": 2, "avg_fill_price": 1.30}


class BrokerWithPartialFillThenCancel:
    def __init__(self):
        self.cancelled = []

    async def get_order_status(self, order_id):
        return {
            "status": "cancelled" if self.cancelled else "partial",
            "filled_qty": 1,
            "avg_fill_price": 1.10,
            "reason": "cancelled remainder" if self.cancelled else "",
        }

    async def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        return {"status": "cancel_requested", "cancel_requested": True}


class FillMonitorTests(unittest.TestCase):
    def test_partial_entry_timeout_cancels_remainder_and_keeps_confirmed_fill(self):
        from fill_reconciliation import OrderContext
        from fill_monitor import monitor_fill

        db = FakeDb()
        broker = BrokerWithPartialFillThenCancel()
        context = OrderContext(
            trade_id="trade-partial",
            order_id="order-partial",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
        )

        with patch("fill_monitor.PARTIAL_FILL_SECS", 0):
            asyncio.run(
                monitor_fill(
                    order_context=context,
                    broker_client=broker,
                    db=db,
                    settings={},
                    poll_interval_secs=0,
                    max_polls=2,
                )
            )

        self.assertEqual(broker.cancelled, ["order-partial"])
        self.assertEqual(db.trade_updates[-1][1]["status"], "partial")
        self.assertEqual(db.trade_updates[-1][1]["quantity"], 1)
        self.assertEqual(db.inserted_positions[0]["remaining_quantity"], 1)

    def test_missing_order_status_marks_trade_unconfirmed_not_executed(self):
        from fill_reconciliation import OrderContext
        from fill_monitor import monitor_fill

        db = FakeDb()
        context = OrderContext(
            trade_id="trade-1",
            order_id="order-1",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
        )

        asyncio.run(
            monitor_fill(
                order_context=context,
                broker_client=BrokerWithoutStatus(),
                db=db,
                settings={},
                poll_interval_secs=0,
                max_polls=1,
            )
        )

        self.assertEqual(len(db.trade_updates), 1)
        _, update = db.trade_updates[0]
        self.assertEqual(update["status"], "unconfirmed")
        self.assertEqual(update["quantity"], 2)
        self.assertNotIn("executed_at", update)

    def test_filled_order_status_reconciles_position_from_broker_fill(self):
        from fill_reconciliation import OrderContext
        from fill_monitor import monitor_fill

        db = FakeDb()
        context = OrderContext(
            trade_id="trade-2",
            order_id="order-2",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
        )

        asyncio.run(
            monitor_fill(
                order_context=context,
                broker_client=BrokerWithFilledStatus(),
                db=db,
                settings={},
                poll_interval_secs=0,
                max_polls=1,
            )
        )

        self.assertEqual(db.trade_updates[0][1]["status"], "executed")
        self.assertEqual(db.trade_updates[0][1]["entry_price"], 1.25)
        self.assertEqual(len(db.inserted_positions), 1)
        self.assertEqual(db.inserted_positions[0]["remaining_quantity"], 2)

    def test_transient_status_error_keeps_polling_until_fill(self):
        from fill_reconciliation import OrderContext
        from fill_monitor import monitor_fill

        db = FakeDb()
        broker = BrokerWithTransientErrorThenFilledStatus()
        context = OrderContext(
            trade_id="trade-2b",
            order_id="order-2b",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
        )

        asyncio.run(
            monitor_fill(
                order_context=context,
                broker_client=broker,
                db=db,
                settings={},
                poll_interval_secs=0,
                max_polls=2,
            )
        )

        self.assertEqual(broker.status_calls, 2)
        self.assertEqual(db.trade_updates[0][1]["status"], "executed")
        self.assertEqual(db.trade_updates[0][1]["entry_price"], 1.25)
        self.assertEqual(len(db.inserted_positions), 1)

    def test_timeout_attempts_cancel_and_reconciles_cancelled_order(self):
        from fill_reconciliation import OrderContext
        from fill_monitor import monitor_fill

        db = FakeDb()
        broker = BrokerThatCancelsTimedOutOrder()
        context = OrderContext(
            trade_id="trade-3",
            order_id="order-3",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
        )

        asyncio.run(
            monitor_fill(
                order_context=context,
                broker_client=broker,
                db=db,
                settings={},
                poll_interval_secs=0,
                max_polls=1,
            )
        )

        self.assertEqual(broker.cancelled, ["order-3"])
        self.assertEqual(db.trade_updates[-1][1]["status"], "failed")
        self.assertEqual(db.trade_updates[-1][1]["error_message"], "cancelled")
        self.assertEqual(len(db.inserted_positions), 0)

    def test_timeout_reconciles_late_fill_seen_after_cancel_attempt(self):
        from fill_reconciliation import OrderContext
        from fill_monitor import monitor_fill

        db = FakeDb()
        broker = BrokerThatFillsDuringCancelFollowup()
        context = OrderContext(
            trade_id="trade-4",
            order_id="order-4",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
        )

        asyncio.run(
            monitor_fill(
                order_context=context,
                broker_client=broker,
                db=db,
                settings={},
                poll_interval_secs=0,
                max_polls=1,
            )
        )

        self.assertEqual(broker.cancelled, ["order-4"])
        self.assertEqual(db.trade_updates[-1][1]["status"], "executed")
        self.assertEqual(db.trade_updates[-1][1]["entry_price"], 1.2)
        self.assertEqual(len(db.inserted_positions), 1)

    def test_sell_timeout_keeps_reconciling_until_delayed_fill(self):
        from fill_reconciliation import OrderContext
        from fill_monitor import monitor_fill

        db = FakeDb()
        broker = BrokerThatFillsAfterConfirmationWindow()
        db.positions["position-1"] = {
            "id": "position-1",
            "entry_price": 1.00,
            "remaining_quantity": 2,
            "realized_pnl": 0.0,
            "trade_ids": ["entry-trade"],
            "status": "open",
            "exit_order_pending": True,
        }
        context = OrderContext(
            trade_id="trade-sell-timeout",
            order_id="order-sell-timeout",
            side="SELL",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
            position_id="position-1",
        )

        asyncio.run(
            monitor_fill(
                order_context=context,
                broker_client=broker,
                db=db,
                settings={},
                poll_interval_secs=0,
                max_polls=1,
                background_poll_interval_secs=0,
                max_background_polls=2,
            )
        )

        self.assertEqual(db.trade_updates[0][1]["status"], "pending_broker")
        self.assertEqual(db.trade_updates[-1][1]["status"], "executed")
        self.assertEqual(db.positions["position-1"]["remaining_quantity"], 0)


if __name__ == "__main__":
    unittest.main()
