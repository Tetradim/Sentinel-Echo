import asyncio
import pathlib
import sys
import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeExitDb:
    def __init__(self):
        self.positions = []
        self.trades = []
        self.position_updates = []
        self.inserted_positions = []
        self.operator_events = []

    async def get_positions(self, status=None):
        return [position for position in self.positions if status is None or position.get("status") == status]

    async def get_trades(self, limit=50):
        return list(self.trades)[:limit]

    async def insert_trade(self, trade):
        self.trades.append(trade)
        return trade["id"]

    async def insert_position(self, position):
        self.inserted_positions.append(position)
        self.positions.append(position)
        return position["id"]

    async def get_position_by_id(self, position_id):
        return next((position for position in self.positions if position.get("id") == position_id), None)

    async def update_trade(self, trade_id, updates):
        for trade in self.trades:
            if trade.get("id") == trade_id:
                trade.update(updates)
                return

    async def update_position(self, position_id, updates):
        self.position_updates.append((position_id, updates))
        for position in self.positions:
            if position["id"] == position_id:
                if "$set" in updates:
                    position.update(updates["$set"])
                elif "$set" not in updates:
                    position.update(updates)
                if "$push" in updates:
                    for key, value in updates["$push"].items():
                        position.setdefault(key, []).append(value)

    async def insert_operator_event(self, event):
        self.operator_events.append(event)
        return event["id"]


class FakeExitBroker:
    def __init__(self, positions=None):
        self.orders = []
        self.positions = positions or []
        self.list_position_calls = 0

    async def place_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"order_id": f"order-{len(self.orders)}", "status": "submitted"}

    async def list_positions(self):
        self.list_position_calls += 1
        return list(self.positions)


class FakeRejectingExitBroker(FakeExitBroker):
    async def place_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"error": "rejected for test"}


class FakeContextBroker(FakeExitBroker):
    def __init__(self, *, context, positions=None):
        super().__init__(positions=positions)
        self.context = context
        self.context_calls = []

    async def get_option_market_context(self, **kwargs):
        self.context_calls.append(kwargs)
        return dict(self.context)


class FakeLifecycleBroker(FakeContextBroker):
    def __init__(self, *, context, positions=None, open_orders=None):
        super().__init__(context=context, positions=positions)
        self.open_orders = list(open_orders or [])
        self.cancelled_order_ids = []

    async def list_open_orders(self):
        return list(self.open_orders)

    async def cancel_order(self, order_id):
        self.cancelled_order_ids.append(order_id)
        return True


class FakePendingFillBroker(FakeContextBroker):
    def __init__(self, *, context, positions, statuses):
        super().__init__(context=context, positions=positions)
        self.statuses = statuses

    async def get_order_status(self, order_id):
        return dict(self.statuses[order_id])


class FakeReplacePendingBroker(FakeContextBroker):
    def __init__(self, *, context, positions):
        super().__init__(context=context, positions=positions)
        self.cancelled_order_ids = []

    async def get_order_status(self, order_id):
        if order_id in self.cancelled_order_ids:
            return {"status": "cancelled", "filled_qty": 0, "avg_fill_price": 0.0}
        return {"status": "pending", "filled_qty": 0, "avg_fill_price": 0.0}

    async def cancel_order(self, order_id):
        self.cancelled_order_ids.append(order_id)
        return {"status": "cancel_requested", "cancel_requested": True}


class BotManagedExitTests(unittest.TestCase):
    def test_post_exit_telemetry_records_best_bid_without_submitting_orders(self):
        from bot_managed_exits import _refresh_recent_closed_position_telemetry

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "closed-position",
                "ticker": "SPY",
                "strike": 775.0,
                "option_type": "CALL",
                "expiration": "2026-09-28",
                "entry_price": 0.34,
                "current_price": 0.30,
                "remaining_quantity": 0,
                "broker": "alpaca",
                "status": "closed",
                "closed_at": "2026-09-28T15:00:00+00:00",
            }
        )
        broker = FakeContextBroker(
            context={
                "option_bid": 0.51,
                "option_ask": 0.53,
                "option_quote_observed_at": "2026-09-28T15:10:00+00:00",
            }
        )

        refreshed = asyncio.run(
            _refresh_recent_closed_position_telemetry(
                db,
                broker,
                {"post_exit_telemetry_enabled": True, "post_exit_telemetry_minutes": 60},
                now=datetime(2026, 9, 28, 15, 10, tzinfo=timezone.utc),
            )
        )

        self.assertEqual(refreshed, 1)
        self.assertEqual(db.positions[0]["post_exit_last_bid"], 0.51)
        self.assertEqual(db.positions[0]["post_exit_highest_bid"], 0.51)
        self.assertEqual(db.positions[0]["post_exit_highest_return_percent"], 50.0)
        self.assertEqual(broker.orders, [])

    def test_legacy_sell_trade_recovers_position_from_reserved_order_id_only(self):
        from bot_managed_exits import _position_id_for_trade

        trade = {"side": "SELL", "order_id": "legacy-exit-order"}
        positions = [
            {
                "id": "position-1",
                "exit_order_pending": True,
                "exit_order_id": "legacy-exit-order",
            },
            {
                "id": "position-2",
                "exit_order_pending": True,
                "exit_order_id": "other-order",
            },
        ]

        self.assertEqual(_position_id_for_trade(trade, positions), "position-1")
        self.assertIsNone(
            _position_id_for_trade(
                trade,
                positions + [{"id": "position-3", "exit_order_id": "legacy-exit-order"}],
            )
        )

    def test_exit_worker_cadence_honors_fastest_configured_reprice_interval(self):
        from bot_managed_exits import _exit_worker_interval_seconds

        self.assertEqual(
            _exit_worker_interval_seconds(
                {
                    "exit_reprice_interval_seconds": 2,
                    "profit_exit_reprice_interval_seconds": 3,
                },
                default_interval=5,
            ),
            2,
        )
        self.assertEqual(
            _exit_worker_interval_seconds(
                {
                    "exit_reprice_interval_seconds": 10,
                    "profit_exit_reprice_interval_seconds": 12,
                },
                default_interval=5,
            ),
            5,
        )

    def test_unfinished_exit_target_is_maintained_during_peak_update(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-target-retry",
                "ticker": "SPY",
                "strike": 761.0,
                "option_type": "CALL",
                "expiration": "2026-09-11",
                "entry_price": 1.00,
                "current_price": 1.10,
                "highest_price": 1.00,
                "highest_executable_bid": 1.00,
                "original_quantity": 8,
                "remaining_quantity": 4,
                "quantity": 4,
                "broker": "alpaca",
                "status": "partial",
                "trade_ids": ["entry", "partial-exit"],
                "profit_stage_1_completed": True,
                "profit_stage_2_completed": True,
                "exit_order_pending": False,
                "exit_target_remaining_quantity": 2,
                "exit_target_trigger": "profit_stage_2",
            }
        )
        broker = FakeContextBroker(
            context={
                "bars": [],
                "option_bid": 1.10,
                "option_ask": 1.12,
                "option_quote_observed_at": "2026-09-10T14:30:00+00:00",
            }
        )

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "coordinated_exit_enabled": True,
                    "zero_dte_liquidation_enabled": False,
                },
                broker,
                schedule_monitor=lambda **kwargs: None,
                now=datetime(2026, 9, 10, 10, 30, tzinfo=ZoneInfo("America/New_York")),
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(broker.orders[-1]["quantity"], 2)
        self.assertEqual(db.trades[-1]["exit_trigger"], "profit_stage_2")

    def test_trailing_target_replaces_older_partial_profit_order(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-alpaca-spy-260910-c-761",
                "alert_id": "entry-761c",
                "ticker": "SPY",
                "strike": 761.0,
                "option_type": "CALL",
                "expiration": "2026-09-10",
                "entry_price": 0.35,
                "current_price": 0.50,
                "highest_price": 0.81,
                "highest_executable_bid": 0.62,
                "original_quantity": 8,
                "remaining_quantity": 4,
                "quantity": 4,
                "broker_quantity": 4,
                "broker": "alpaca",
                "status": "partial",
                "trade_ids": ["entry", "stage-1"],
                "profit_stage_1_completed": True,
                "profit_floor_armed": True,
                "profit_floor_price": 0.36,
                "exit_order_pending": True,
                "exit_order_id": "stage-2-order",
                "exit_reservation_trigger": "profit_stage_2",
                "exit_target_remaining_quantity": 2,
                "exit_reservation_created_at": "2026-09-10T14:29:00+00:00",
            }
        )
        db.trades.append(
            {
                "id": "stage-2",
                "alert_id": "entry-761c",
                "alert_status_owned": False,
                "position_id": "position-alpaca-spy-260910-c-761",
                "ticker": "SPY",
                "strike": 761.0,
                "option_type": "CALL",
                "expiration": "2026-09-10",
                "entry_price": 0.35,
                "exit_price": 0.64,
                "quantity": 2,
                "side": "SELL",
                "broker": "alpaca",
                "status": "pending",
                "order_id": "stage-2-order",
                "exit_trigger": "profit_stage_2",
            }
        )
        broker_position = {
            "broker": "alpaca",
            "symbol": "SPY260910C00761000",
            "quantity": 4,
            "avg_entry_price": 0.35,
            "current_price": 0.50,
        }
        broker = FakeReplacePendingBroker(
            context={
                "bars": [],
                "option_bid": 0.50,
                "option_ask": 0.52,
                "option_quote_observed_at": "2026-09-10T14:30:00+00:00",
            },
            positions=[broker_position],
        )
        monitored = []

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "coordinated_exit_enabled": True,
                    "zero_dte_liquidation_enabled": False,
                },
                broker,
                schedule_monitor=lambda **kwargs: monitored.append(kwargs),
                now=datetime(2026, 9, 10, 10, 30, tzinfo=ZoneInfo("America/New_York")),
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(broker.cancelled_order_ids, ["stage-2-order"])
        self.assertEqual(broker.orders[-1]["quantity"], 4)
        self.assertEqual(db.positions[0]["exit_target_remaining_quantity"], 0)
        self.assertEqual(db.trades[-1]["exit_trigger"], "coordinated_trailing_stop")

    def test_filled_stage_two_is_reconciled_before_trailing_exit_evaluation(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-alpaca-spy-260910-c-761",
                "alert_id": "entry-761c",
                "ticker": "SPY",
                "strike": 761.0,
                "option_type": "CALL",
                "expiration": "2026-09-10",
                "entry_price": 0.35,
                "current_price": 0.50,
                "highest_price": 0.81,
                "highest_executable_bid": 0.62,
                "original_quantity": 8,
                "remaining_quantity": 4,
                "quantity": 4,
                "broker_quantity": 2,
                "broker": "alpaca",
                "status": "partial",
                "trade_ids": ["entry", "stage-1"],
                "profit_stage_1_completed": True,
                "profit_floor_armed": True,
                "profit_floor_price": 0.36,
                "exit_order_pending": True,
                "exit_order_id": "stage-2-order",
                "exit_reservation_trigger": "profit_stage_2",
            }
        )
        db.trades.append(
            {
                "id": "stage-2",
                "alert_id": "entry-761c",
                "alert_status_owned": False,
                "position_id": "position-alpaca-spy-260910-c-761",
                "ticker": "SPY",
                "strike": 761.0,
                "option_type": "CALL",
                "expiration": "2026-09-10",
                "entry_price": 0.35,
                "exit_price": 0.64,
                "quantity": 2,
                "side": "SELL",
                "broker": "alpaca",
                "status": "pending_broker",
                "order_id": "stage-2-order",
                "exit_trigger": "profit_stage_2",
            }
        )
        broker_position = {
            "broker": "alpaca",
            "symbol": "SPY260910C00761000",
            "quantity": 2,
            "avg_entry_price": 0.35,
            "current_price": 0.50,
        }
        broker = FakePendingFillBroker(
            context={
                "bars": [],
                "option_bid": 0.50,
                "option_ask": 0.52,
                "option_quote_observed_at": "2026-09-10T14:30:00+00:00",
            },
            positions=[broker_position],
            statuses={
                "stage-2-order": {
                    "status": "filled",
                    "filled_qty": 2,
                    "avg_fill_price": 0.64,
                }
            },
        )
        monitored = []

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "coordinated_exit_enabled": True,
                    "coordinated_progressive_trailing_enabled": True,
                    "zero_dte_liquidation_enabled": False,
                },
                broker,
                schedule_monitor=lambda **kwargs: monitored.append(kwargs),
                now=datetime(2026, 9, 10, 10, 30, tzinfo=ZoneInfo("America/New_York")),
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(db.trades[0]["status"], "executed")
        self.assertIn("stage-2", db.positions[0]["trade_ids"])
        self.assertEqual(db.positions[0]["remaining_quantity"], 2)
        self.assertEqual(db.trades[-1]["exit_trigger"], "coordinated_trailing_stop")
        self.assertEqual(broker.orders[-1]["quantity"], 2)
        self.assertEqual(len(monitored), 1)

    def test_coordinated_exit_uses_explicit_original_quantity_stage(self):
        from bot_managed_exits import _exit_quantity_for_decision

        quantity = _exit_quantity_for_decision(
            {"original_quantity": 8, "remaining_quantity": 4},
            {},
            {"exit_trigger": "profit_stage_2", "quantity": 2},
        )

        self.assertEqual(quantity, 2)

    def test_coordinated_worker_persists_exit_reservation_before_monitor(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-stage-1",
                "alert_id": "alert-stage-1",
                "ticker": "SPY",
                "strike": 765.0,
                "option_type": "CALL",
                "expiration": "2026-09-04",
                "entry_price": 1.00,
                "current_price": 1.25,
                "highest_price": 1.20,
                "original_quantity": 8,
                "remaining_quantity": 8,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
            }
        )
        broker = FakeContextBroker(
            context={"bars": [], "option_bid": 1.25, "option_ask": 1.27, "source": "alpaca"}
        )
        monitored = []

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "coordinated_exit_enabled": True,
                    "zero_dte_liquidation_enabled": False,
                },
                broker,
                schedule_monitor=lambda **kwargs: monitored.append(kwargs),
                now=datetime(2026, 9, 3, 11, 0, tzinfo=ZoneInfo("America/New_York")),
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(broker.orders[0]["quantity"], 4)
        self.assertEqual(broker.orders[0]["price"], 1.24)
        self.assertEqual(db.trades[0]["exit_trigger"], "profit_stage_1")
        self.assertTrue(db.positions[0]["exit_order_pending"])
        self.assertEqual(db.positions[0]["exit_order_id"], "order-1")
        self.assertEqual(len(monitored), 1)

    def test_profit_stage_marketable_offset_can_be_disabled(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-stage-no-offset",
                "ticker": "SPY",
                "strike": 765.0,
                "option_type": "CALL",
                "expiration": "2026-09-04",
                "entry_price": 1.00,
                "current_price": 1.25,
                "highest_price": 1.25,
                "original_quantity": 8,
                "remaining_quantity": 8,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
            }
        )
        broker = FakeContextBroker(
            context={"bars": [], "option_bid": 1.25, "option_ask": 1.27, "source": "alpaca"}
        )

        asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "coordinated_exit_enabled": True,
                    "zero_dte_liquidation_enabled": False,
                    "profit_exit_marketable_offset_cents": 0,
                },
                broker,
                schedule_monitor=lambda **kwargs: None,
                now=datetime(2026, 9, 3, 11, 0, tzinfo=ZoneInfo("America/New_York")),
            )
        )

        self.assertEqual(broker.orders[0]["price"], 1.25)

    def test_existing_exit_reservation_suppresses_duplicate_submission(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-reserved",
                "ticker": "SPY",
                "strike": 765.0,
                "option_type": "CALL",
                "expiration": "2026-09-04",
                "entry_price": 1.00,
                "current_price": 1.25,
                "highest_price": 1.25,
                "original_quantity": 8,
                "remaining_quantity": 8,
                "broker": "alpaca",
                "status": "open",
                "exit_order_pending": True,
                "exit_order_id": "existing-order",
            }
        )
        broker = FakeContextBroker(
            context={"bars": [], "option_bid": 1.25, "option_ask": 1.27}
        )

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "coordinated_exit_enabled": True,
                    "zero_dte_liquidation_enabled": False,
                },
                broker,
                now=datetime(2026, 9, 3, 11, 0, tzinfo=ZoneInfo("America/New_York")),
            )
        )

        self.assertEqual(count, 0)
        self.assertEqual(broker.orders, [])

    def test_failed_exit_submission_releases_reservation(self):
        from bot_managed_exits import _submit_exit_order

        db = FakeExitDb()
        position = {
            "id": "position-failed",
            "ticker": "SPY",
            "strike": 765.0,
            "option_type": "CALL",
            "expiration": "2026-09-04",
            "entry_price": 1.00,
            "current_price": 0.64,
            "option_bid": 0.64,
            "remaining_quantity": 2,
        }
        db.positions.append(position)
        broker = FakeRejectingExitBroker()

        result = asyncio.run(
            _submit_exit_order(
                db,
                position,
                {
                    "triggered": True,
                    "exit_trigger": "coordinated_hard_stop",
                    "quantity": 2,
                    "exit_price": 0.64,
                },
                {"active_broker": "alpaca"},
                broker,
                schedule_monitor=None,
            )
        )

        self.assertIsNone(result)
        self.assertFalse(db.positions[0]["exit_order_pending"])

    def test_zero_dte_cutoff_forces_full_exit_before_partial_rules(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-zero-dte",
                "alert_id": "alert-zero-dte",
                "ticker": "SPY",
                "strike": 765.0,
                "option_type": "CALL",
                "expiration": "2026-09-01",
                "entry_price": 1.00,
                "current_price": 1.20,
                "highest_price": 1.50,
                "remaining_quantity": 8,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
                "reversal_conflict_count": 1,
            }
        )
        broker = FakeLifecycleBroker(
            context={
                "bars": [
                    {"o": price + 0.03, "c": price, "v": 100}
                    for price in [100.5, 100.4, 100.3, 100.2, 100.1, 100.0]
                ],
                "option_bid": 1.19,
                "option_ask": 1.21,
            }
        )

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "zero_dte_liquidation_enabled": True,
                    "zero_dte_liquidation_time": "15:40",
                    "reversal_exit_enabled": True,
                    "reversal_warning_sell_percent": 25.0,
                    "take_profit_sell_percentage": 50.0,
                },
                broker,
                now=datetime(2026, 9, 1, 15, 41, tzinfo=ZoneInfo("America/New_York")),
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(broker.orders[0]["quantity"], 8)
        self.assertEqual(broker.orders[0]["price"], 1.19)
        self.assertEqual(db.trades[0]["exit_trigger"], "mandatory_0dte_liquidation")
        self.assertEqual(db.operator_events[-1]["action"], "zero_dte_liquidation_started")
        self.assertTrue(db.positions[0]["zero_dte_liquidation_started_at"])

    def test_zero_dte_cutoff_cancels_only_expiring_buy_orders(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        broker = FakeLifecycleBroker(
            context={},
            open_orders=[
                {"order_id": "expire-buy", "symbol": "SPY260901C00765000", "side": "buy"},
                {"order_id": "future-buy", "symbol": "SPY260902C00765000", "side": "buy"},
                {"order_id": "expire-sell", "symbol": "SPY260901C00765000", "side": "sell"},
            ],
        )

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "zero_dte_liquidation_enabled": True,
                    "zero_dte_liquidation_time": "15:40",
                },
                broker,
                now=datetime(2026, 9, 1, 15, 41, tzinfo=ZoneInfo("America/New_York")),
            )
        )

        self.assertEqual(count, 0)
        self.assertEqual(broker.cancelled_order_ids, ["expire-buy"])

    def test_completed_partial_take_profit_does_not_submit_again(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-tp-complete",
                "ticker": "SPY",
                "strike": 765.0,
                "option_type": "CALL",
                "expiration": "12/18/2026",
                "entry_price": 1.00,
                "current_price": 1.40,
                "highest_price": 1.40,
                "remaining_quantity": 5,
                "broker": "alpaca",
                "status": "partial",
                "trade_ids": ["trade-entry", "trade-tp1"],
                "take_profit_stage_completed": True,
            }
        )
        broker = FakeExitBroker()

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "take_profit_enabled": True,
                    "take_profit_percentage": 35.0,
                    "take_profit_sell_percentage": 50.0,
                },
                broker,
            )
        )

        self.assertEqual(count, 0)
        self.assertEqual(broker.orders, [])

    def test_reversal_warning_persists_state_and_sells_partial_at_live_bid(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-reversal",
                "alert_id": "alert-reversal",
                "ticker": "SPY",
                "strike": 765.0,
                "option_type": "CALL",
                "expiration": "12/18/2026",
                "entry_price": 1.00,
                "current_price": 1.20,
                "highest_price": 1.50,
                "remaining_quantity": 8,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
                "reversal_conflict_count": 1,
            }
        )
        broker = FakeContextBroker(
            context={
                "bars": [
                    {"o": price + 0.03, "c": price, "v": 100}
                    for price in [100.5, 100.4, 100.3, 100.2, 100.1, 100.0]
                ],
                "option_bid": 1.19,
                "option_ask": 1.21,
                "source": "alpaca",
            }
        )

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "reversal_exit_enabled": True,
                    "reversal_warning_confirmations": 2,
                    "reversal_confirmed_confirmations": 4,
                    "reversal_warning_sell_percent": 25.0,
                    "reversal_premium_drawdown_percent": 12.0,
                },
                broker,
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(len(broker.context_calls), 1)
        self.assertEqual(db.positions[0]["reversal_conflict_count"], 2)
        self.assertEqual(db.positions[0]["reversal_state"], "reversal_reduce")
        self.assertEqual(broker.orders[0]["quantity"], 2)
        self.assertEqual(broker.orders[0]["price"], 1.19)
        self.assertEqual(db.trades[0]["exit_trigger"], "reversal_reduce")
        self.assertIn("reversal_state_changed", [event["action"] for event in db.operator_events])
        self.assertEqual(db.operator_events[-1]["action"], "coordinated_exit_submitted")
        reversal_event = next(
            event for event in db.operator_events if event["action"] == "reversal_state_changed"
        )
        self.assertEqual(reversal_event["details"]["to_state"], "reversal_reduce")

    def test_unavailable_context_clears_stale_quote_before_fixed_exit_order(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-stale-context",
                "ticker": "SPY",
                "strike": 765.0,
                "option_type": "CALL",
                "expiration": "12/18/2026",
                "entry_price": 1.00,
                "current_price": 1.40,
                "highest_price": 1.50,
                "option_bid": 2.00,
                "option_ask": 2.10,
                "adaptive_trailing_percent": 30.0,
                "market_intelligence_context_available": True,
                "remaining_quantity": 2,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
            }
        )
        broker = FakeContextBroker(
            context={},
            positions=[
                {
                    "broker": "alpaca",
                    "symbol": "SPY261218C00765000",
                    "quantity": 2,
                    "avg_entry_price": 1.00,
                    "current_price": 1.40,
                }
            ],
        )

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "take_profit_enabled": True,
                    "take_profit_percentage": 35.0,
                    "reversal_exit_enabled": False,
                    "zero_dte_liquidation_enabled": False,
                },
                broker,
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(broker.orders[0]["price"], 1.40)
        self.assertIsNone(db.positions[0]["option_bid"])
        self.assertIsNone(db.positions[0]["adaptive_trailing_percent"])
        self.assertFalse(db.positions[0]["market_intelligence_context_available"])

    def test_adaptive_trailing_uses_effective_width_before_fixed_exit_evaluation(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-adaptive",
                "ticker": "SPY",
                "strike": 765.0,
                "option_type": "CALL",
                "expiration": "12/18/2026",
                "entry_price": 1.00,
                "current_price": 1.30,
                "highest_price": 1.50,
                "remaining_quantity": 2,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
                "premium_mark_history": [1.50, 1.35, 1.42],
            }
        )
        broker = FakeContextBroker(
            context={
                "bars": [
                    {"o": price - 0.03, "c": price, "v": 100}
                    for price in [100.0, 100.1, 100.2, 100.3, 100.4, 100.5]
                ],
                "option_bid": 1.29,
                "option_ask": 1.31,
                "source": "alpaca",
            }
        )

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "trailing_stop_enabled": True,
                    "trailing_stop_type": "percent",
                    "trailing_stop_percent": 10.0,
                    "adaptive_trailing_enabled": True,
                    "adaptive_trailing_min_percent": 8.0,
                    "adaptive_trailing_max_percent": 35.0,
                },
                broker,
            )
        )

        self.assertEqual(count, 0)
        self.assertEqual(broker.orders, [])
        self.assertGreater(db.positions[0]["adaptive_trailing_percent"], 10.0)
        self.assertEqual(db.positions[0]["current_price"], 1.30)

    def test_exit_cycle_places_sell_when_take_profit_hits(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-1",
                "alert_id": "alert-1",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "CALL",
                "expiration": "12/18/2026",
                "entry_price": 1.00,
                "current_price": 1.40,
                "remaining_quantity": 2,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
            }
        )
        broker = FakeExitBroker()
        scheduled = []

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "take_profit_enabled": True,
                    "take_profit_percentage": 35.0,
                },
                broker,
                schedule_monitor=lambda **kwargs: scheduled.append(kwargs),
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(broker.orders[0]["side"], "SELL")
        self.assertEqual(broker.orders[0]["quantity"], 2)
        self.assertEqual(broker.orders[0]["price"], 1.40)
        self.assertEqual(db.trades[0]["side"], "SELL")
        self.assertEqual(db.trades[0]["status"], "pending")
        self.assertEqual(db.trades[0]["position_id"], "position-1")
        self.assertEqual(db.trades[0]["exit_trigger"], "take_profit")
        self.assertEqual(scheduled[0]["order_context"].position_id, "position-1")

    def test_exit_cycle_uses_broker_mark_before_evaluating_take_profit(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-1",
                "alert_id": "alert-1",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "CALL",
                "expiration": "12/18/2026",
                "entry_price": 0.45,
                "current_price": 0.45,
                "highest_price": 0.45,
                "remaining_quantity": 10,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
                "broker_mark_refreshed_at": "2026-08-31T13:57:43+00:00",
            }
        )
        broker = FakeExitBroker(
            positions=[
                {
                    "broker": "alpaca",
                    "symbol": "SPY261218C00500000",
                    "quantity": 10,
                    "avg_entry_price": 0.45,
                    "current_price": 0.61,
                }
            ]
        )

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "take_profit_enabled": True,
                    "take_profit_percentage": 35.0,
                },
                broker,
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(broker.orders[0]["quantity"], 10)
        self.assertEqual(broker.orders[0]["price"], 0.61)
        self.assertEqual(db.positions[0]["current_price"], 0.61)
        self.assertEqual(db.positions[0]["highest_price"], 0.61)
        self.assertEqual(broker.list_position_calls, 1)

    def test_exit_cycle_uses_one_broker_position_snapshot_for_import_stale_and_mark_refresh(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-1",
                "alert_id": "alert-1",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "CALL",
                "expiration": "12/18/2026",
                "entry_price": 0.45,
                "current_price": 0.45,
                "highest_price": 0.45,
                "remaining_quantity": 10,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
                "broker_mark_refreshed_at": "2026-08-31T13:57:43+00:00",
            }
        )
        broker = FakeExitBroker(
            positions=[
                {
                    "broker": "alpaca",
                    "symbol": "SPY261218C00500000",
                    "quantity": 10,
                    "avg_entry_price": 0.45,
                    "current_price": 0.61,
                }
            ]
        )

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "take_profit_enabled": True,
                    "take_profit_percentage": 35.0,
                },
                broker,
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(broker.list_position_calls, 1)
        self.assertEqual(db.positions[0]["current_price"], 0.61)

    def test_take_profit_can_sell_configured_partial_quantity(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-1",
                "alert_id": "alert-1",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "CALL",
                "expiration": "12/18/2026",
                "entry_price": 1.00,
                "current_price": 1.40,
                "remaining_quantity": 10,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
            }
        )
        broker = FakeExitBroker()

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "take_profit_enabled": True,
                    "take_profit_percentage": 35.0,
                    "take_profit_sell_percentage": 50.0,
                },
                broker,
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(broker.orders[0]["quantity"], 5)
        self.assertEqual(db.trades[0]["quantity"], 5)
        self.assertEqual(db.trades[0]["exit_trigger"], "take_profit")

    def test_break_even_triggers_after_configured_profit_activation(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-1",
                "alert_id": "alert-1",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "CALL",
                "expiration": "12/18/2026",
                "entry_price": 0.50,
                "current_price": 0.50,
                "highest_price": 0.60,
                "remaining_quantity": 3,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
            }
        )
        broker = FakeExitBroker()

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "bot_managed_exit_worker_enabled": True,
                    "break_even_enabled": True,
                    "break_even_activation_percentage": 10.0,
                },
                broker,
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(broker.orders[0]["quantity"], 3)
        self.assertEqual(broker.orders[0]["price"], 0.50)
        self.assertEqual(db.trades[0]["exit_trigger"], "break_even")

    def test_break_even_can_activate_after_configured_cents_gain(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-1",
                "alert_id": "alert-1",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "CALL",
                "expiration": "12/18/2026",
                "entry_price": 0.50,
                "current_price": 0.50,
                "highest_price": 0.65,
                "remaining_quantity": 3,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
            }
        )
        broker = FakeExitBroker()

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "bot_managed_exit_worker_enabled": True,
                    "break_even_enabled": True,
                    "break_even_activation_type": "cents",
                    "break_even_activation_cents": 15.0,
                    "break_even_activation_percentage": 40.0,
                },
                broker,
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(broker.orders[0]["quantity"], 3)
        self.assertEqual(broker.orders[0]["price"], 0.50)
        self.assertEqual(db.trades[0]["exit_trigger"], "break_even")

    def test_exit_cycle_updates_trailing_peak_without_selling(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-1",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "CALL",
                "expiration": "12/18/2026",
                "entry_price": 1.00,
                "current_price": 1.20,
                "highest_price": 1.10,
                "remaining_quantity": 1,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
            }
        )
        broker = FakeExitBroker()

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "trailing_stop_enabled": True,
                    "trailing_stop_type": "percent",
                    "trailing_stop_percent": 10.0,
                },
                broker,
            )
        )

        self.assertEqual(count, 0)
        self.assertEqual(broker.orders, [])
        self.assertEqual(db.positions[0]["highest_price"], 1.20)

    def test_startup_reconciliation_inserts_missing_broker_option_position(self):
        from bot_managed_exits import reconcile_broker_positions

        db = FakeExitDb()
        broker = FakeExitBroker(
            positions=[
                {
                    "broker": "alpaca",
                    "symbol": "SPY261218C00500000",
                    "ticker": "SPY",
                    "strike": 500.0,
                    "option_type": "CALL",
                    "expiration": "12/18/2026",
                    "quantity": 3,
                    "avg_entry_price": 1.20,
                    "current_price": 1.30,
                }
            ]
        )

        count = asyncio.run(reconcile_broker_positions(db, broker, {"active_broker": "alpaca"}))

        self.assertEqual(count, 1)
        position = db.inserted_positions[0]
        self.assertEqual(position["id"], "position-alpaca-spy-261218-c-500")
        self.assertEqual(position["remaining_quantity"], 3)
        self.assertEqual(position["entry_price"], 1.20)
        self.assertEqual(position["current_price"], 1.30)
        self.assertTrue(position["reconciled_from_broker_only"])

    def test_reconciliation_reactivates_closed_contract_instead_of_inserting_duplicate_id(self):
        from bot_managed_exits import reconcile_broker_positions

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-alpaca-spy-260901-p-758",
                "ticker": "SPY",
                "strike": 758.0,
                "option_type": "PUT",
                "expiration": "2026-09-01",
                "remaining_quantity": 0,
                "broker": "alpaca",
                "status": "closed",
                "trade_ids": ["old-buy", "old-sell"],
                "coordinated_loss_ladder_completed_steps": [0, 1, 2, 3],
                "coordinated_stop_confirmation_count": 2,
                "coordinated_break_even_confirmation_count": 2,
                "counterfactual_stop_hits": {"25": "old"},
                "premium_mark_history": [0.40, 0.10],
                "coordinated_trailing_floor": 0.40,
                "exit_target_remaining_quantity": 0,
            }
        )
        broker = FakeExitBroker(
            positions=[
                {
                    "broker": "alpaca",
                    "symbol": "SPY260901P00758000",
                    "quantity": 10,
                    "avg_entry_price": 0.25,
                    "current_price": 0.24,
                }
            ]
        )

        count = asyncio.run(reconcile_broker_positions(db, broker, {"active_broker": "alpaca"}))

        self.assertEqual(count, 1)
        self.assertEqual(db.inserted_positions, [])
        self.assertEqual(len(db.positions), 1)
        self.assertEqual(db.positions[0]["status"], "open")
        self.assertEqual(db.positions[0]["remaining_quantity"], 10)
        self.assertTrue(db.positions[0]["reconciled_from_broker_only"])
        self.assertEqual(db.positions[0]["trade_ids"], [])
        self.assertEqual(db.positions[0]["coordinated_loss_ladder_completed_steps"], [])
        self.assertEqual(db.positions[0]["coordinated_stop_confirmation_count"], 0)
        self.assertEqual(db.positions[0]["coordinated_break_even_confirmation_count"], 0)
        self.assertEqual(db.positions[0]["counterfactual_stop_hits"], {})
        self.assertEqual(db.positions[0]["premium_mark_history"], [])
        self.assertIsNone(db.positions[0]["coordinated_trailing_floor"])
        self.assertIsNone(db.positions[0]["exit_target_remaining_quantity"])

    def test_reconciliation_does_not_resurrect_just_closed_contract_from_stale_broker_snapshot(self):
        from bot_managed_exits import reconcile_broker_positions

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-alpaca-spy-260901-c-766",
                "ticker": "SPY",
                "strike": 766.0,
                "option_type": "CALL",
                "expiration": "2026-09-01",
                "remaining_quantity": 0,
                "broker": "alpaca",
                "status": "closed",
                "closed_at": datetime.now(timezone.utc).isoformat(),
                "realized_pnl": 10.0,
                "unrealized_pnl": 0.0,
                "trade_ids": ["buy-current", "sell-current"],
            }
        )
        broker = FakeExitBroker(
            positions=[
                {
                    "broker": "alpaca",
                    "symbol": "SPY260901C00766000",
                    "quantity": 10,
                    "avg_entry_price": 0.16,
                    "current_price": 0.17,
                }
            ]
        )

        count = asyncio.run(reconcile_broker_positions(db, broker, {"active_broker": "alpaca"}))

        self.assertEqual(count, 0)
        self.assertEqual(db.positions[0]["status"], "closed")
        self.assertEqual(db.positions[0]["realized_pnl"], 10.0)
        self.assertEqual(db.positions[0]["trade_ids"], ["buy-current", "sell-current"])

    def test_exit_cycle_imports_broker_only_position_before_evaluating_exits(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        broker = FakeExitBroker(
            positions=[
                {
                    "broker": "alpaca",
                    "symbol": "SPY261218C00500000",
                    "quantity": 10,
                    "avg_entry_price": 0.40,
                    "current_price": 0.56,
                }
            ]
        )

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "take_profit_enabled": True,
                    "take_profit_percentage": 35.0,
                },
                broker,
            )
        )

        self.assertEqual(count, 1)
        self.assertEqual(len(db.inserted_positions), 1)
        self.assertTrue(db.inserted_positions[0]["reconciled_from_broker_only"])
        self.assertEqual(broker.orders[0]["side"], "SELL")
        self.assertEqual(broker.orders[0]["quantity"], 10)
        self.assertEqual(broker.orders[0]["price"], 0.56)

    def test_exit_cycle_closes_stale_local_position_absent_at_broker(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-1",
                "alert_id": "alert-1",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "PUT",
                "expiration": "12/18/2026",
                "entry_price": 1.00,
                "current_price": 0.80,
                "highest_price": 1.00,
                "unrealized_pnl": -40.0,
                "remaining_quantity": 2,
                "quantity": 2,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
                "broker_mark_refreshed_at": "2026-08-31T13:57:43+00:00",
            }
        )
        broker = FakeExitBroker(positions=[])

        count = asyncio.run(
            run_bot_managed_exit_cycle(
                db,
                {
                    "active_broker": "alpaca",
                    "stop_loss_enabled": True,
                    "stop_loss_percentage": 18.0,
                },
                broker,
            )
        )

        self.assertEqual(count, 0)
        self.assertEqual(broker.orders, [])
        self.assertEqual(db.positions[0]["status"], "closed")
        self.assertEqual(db.positions[0]["remaining_quantity"], 0)
        self.assertEqual(db.positions[0]["unrealized_pnl"], 0.0)
        self.assertEqual(db.positions[0]["broker_reconciliation"], "closed_absent_at_broker")

    def test_broker_refresh_does_not_race_pending_exit_quantity_accounting(self):
        from bot_managed_exits import _refresh_positions_from_broker

        db = FakeExitDb()
        position = {
            "id": "position-pending-exit",
            "ticker": "SPY",
            "strike": 773.0,
            "option_type": "CALL",
            "expiration": "2026-09-03",
            "entry_price": 0.17,
            "current_price": 0.24,
            "remaining_quantity": 3,
            "quantity": 3,
            "broker": "alpaca",
            "status": "partial",
            "exit_order_pending": True,
        }
        db.positions.append(position)
        broker_position = {
            "broker": "alpaca",
            "symbol": "SPY260903C00773000",
            "quantity": 1,
            "avg_entry_price": 0.17,
            "current_price": 0.26,
        }

        asyncio.run(
            _refresh_positions_from_broker(
                db,
                [position],
                FakeExitBroker(positions=[broker_position]),
                {"active_broker": "alpaca"},
                broker_positions=[broker_position],
            )
        )

        self.assertEqual(position["remaining_quantity"], 3)
        self.assertEqual(position["quantity"], 3)
        self.assertEqual(position["current_price"], 0.26)

    def test_broker_refresh_caps_runner_quantities_to_broker_position(self):
        from bot_managed_exits import _refresh_positions_from_broker

        db = FakeExitDb()
        position = {
            "id": "position-runner-reconcile",
            "ticker": "SPY",
            "strike": 773.0,
            "option_type": "CALL",
            "expiration": "2026-09-03",
            "entry_price": 0.17,
            "current_price": 0.24,
            "remaining_quantity": 4,
            "quantity": 4,
            "broker": "alpaca",
            "status": "partial",
            "exit_order_pending": False,
            "core_runner_candidate_quantity": 3,
            "core_runner_dedicated_quantity": 3,
            "core_runner_core_quantity": 1,
            "core_runner_activated": True,
        }
        db.positions.append(position)
        broker_position = {
            "broker": "alpaca",
            "symbol": "SPY260903C00773000",
            "quantity": 1,
            "avg_entry_price": 0.17,
            "current_price": 0.26,
        }

        asyncio.run(
            _refresh_positions_from_broker(
                db,
                [position],
                FakeExitBroker(positions=[broker_position]),
                {"active_broker": "alpaca"},
                broker_positions=[broker_position],
            )
        )

        self.assertEqual(position["remaining_quantity"], 1)
        self.assertEqual(position["core_runner_candidate_quantity"], 1)
        self.assertEqual(position["core_runner_dedicated_quantity"], 1)
        self.assertEqual(position["core_runner_core_quantity"], 0)

    def test_stale_reconciliation_waits_for_pending_exit_fill_monitor(self):
        from bot_managed_exits import reconcile_local_positions_against_broker

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-pending-full-exit",
                "ticker": "SPY",
                "strike": 775.0,
                "option_type": "CALL",
                "expiration": "2026-09-03",
                "remaining_quantity": 3,
                "quantity": 3,
                "broker": "alpaca",
                "status": "partial",
                "exit_order_pending": True,
                "trade_ids": ["entry-trade"],
            }
        )

        result = asyncio.run(
            reconcile_local_positions_against_broker(
                db,
                FakeExitBroker(positions=[]),
                {"active_broker": "alpaca"},
                broker_positions=[],
            )
        )

        self.assertEqual(result, {"checked": 0, "closed": 0})
        self.assertEqual(db.positions[0]["status"], "partial")
        self.assertEqual(db.positions[0]["remaining_quantity"], 3)

    def test_bot_managed_exit_retry_uses_fresh_client_order_id(self):
        from bot_managed_exits import run_bot_managed_exit_cycle

        db = FakeExitDb()
        db.positions.append(
            {
                "id": "position-1",
                "alert_id": "alert-1",
                "ticker": "SPY",
                "strike": 500.0,
                "option_type": "CALL",
                "expiration": "12/18/2026",
                "entry_price": 1.00,
                "current_price": 0.80,
                "remaining_quantity": 2,
                "broker": "alpaca",
                "status": "open",
                "trade_ids": ["trade-entry"],
            }
        )
        broker = FakeExitBroker()
        settings = {
            "active_broker": "alpaca",
            "stop_loss_enabled": True,
            "stop_loss_percentage": 18.0,
        }

        asyncio.run(run_bot_managed_exit_cycle(db, settings, broker))
        db.trades[0]["status"] = "failed"
        asyncio.run(run_bot_managed_exit_cycle(db, settings, broker))

        self.assertEqual(len(broker.orders), 2)
        first_id = broker.orders[0]["client_order_id"]
        second_id = broker.orders[1]["client_order_id"]
        self.assertNotEqual(first_id, second_id)

    def test_risk_exit_replacement_uses_short_exit_interval_not_entry_timeout(self):
        from bot_managed_exits import _pending_exit_requires_replacement

        now = datetime(2026, 9, 11, 15, 0, 10, tzinfo=timezone.utc)
        replace = _pending_exit_requires_replacement(
            {"remaining_quantity": 3, "exit_reservation_created_at": "2026-09-11T15:00:04+00:00"},
            {"quantity": 3, "exit_trigger": "coordinated_hard_stop"},
            {"triggered": True, "quantity": 3, "exit_trigger": "coordinated_hard_stop"},
            {
                "fill_confirmation_timeout_seconds": 180,
                "exit_reprice_interval_seconds": 5,
                "profit_exit_reprice_interval_seconds": 12,
            },
            now=now,
        )

        self.assertTrue(replace)

    def test_profit_stage_uses_its_own_more_patient_reprice_interval(self):
        from bot_managed_exits import _pending_exit_requires_replacement

        settings = {
            "fill_confirmation_timeout_seconds": 180,
            "exit_reprice_interval_seconds": 5,
            "profit_exit_reprice_interval_seconds": 12,
        }
        position = {
            "remaining_quantity": 3,
            "exit_reservation_created_at": "2026-09-11T15:00:00+00:00",
        }
        pending = {"quantity": 1, "exit_trigger": "profit_stage_1"}
        decision = {"triggered": True, "quantity": 1, "exit_trigger": "profit_stage_1"}

        self.assertFalse(
            _pending_exit_requires_replacement(
                position,
                pending,
                decision,
                settings,
                now=datetime(2026, 9, 11, 15, 0, 11, tzinfo=timezone.utc),
            )
        )
        self.assertTrue(
            _pending_exit_requires_replacement(
                position,
                pending,
                decision,
                settings,
                now=datetime(2026, 9, 11, 15, 0, 12, tzinfo=timezone.utc),
            )
        )

    def test_decision_target_honors_explicit_runner_target(self):
        from bot_managed_exits import _decision_target

        target = _decision_target(
            {"remaining_quantity": 4},
            {
                "triggered": True,
                "quantity": 3,
                "target_remaining_quantity": 2,
                "exit_trigger": "coordinated_trailing_stop",
            },
        )

        self.assertEqual(target, 2)

    def test_pending_exit_is_replaced_when_it_would_cross_new_runner_target(self):
        from bot_managed_exits import _pending_exit_requires_replacement

        replace = _pending_exit_requires_replacement(
            {
                "remaining_quantity": 4,
                "exit_target_remaining_quantity": 0,
                "exit_reservation_created_at": "2026-09-11T15:00:09+00:00",
            },
            {"quantity": 4, "exit_trigger": "coordinated_trailing_stop"},
            {
                "triggered": True,
                "quantity": 2,
                "target_remaining_quantity": 2,
                "exit_trigger": "coordinated_trailing_stop",
            },
            {"exit_reprice_interval_seconds": 30},
            now=datetime(2026, 9, 11, 15, 0, 10, tzinfo=timezone.utc),
        )

        self.assertTrue(replace)

    def test_runner_exit_priorities_match_risk_ownership(self):
        from bot_managed_exits import _exit_trigger_priority

        self.assertEqual(_exit_trigger_priority("runner_catastrophic_stop"), 100)
        self.assertEqual(_exit_trigger_priority("runner_trailing_stop"), 80)

    def test_runner_exit_submission_persists_allocation_audit_fields(self):
        from bot_managed_exits import _submit_exit_order

        db = FakeExitDb()
        position = {
            "id": "position-runner-audit",
            "ticker": "SPY",
            "strike": 775.0,
            "option_type": "CALL",
            "expiration": "2026-09-25",
            "entry_price": 0.34,
            "current_price": 1.20,
            "option_bid": 1.20,
            "remaining_quantity": 2,
        }
        db.positions.append(position)
        broker = FakeExitBroker()

        trade = asyncio.run(
            _submit_exit_order(
                db,
                position,
                {
                    "triggered": True,
                    "exit_trigger": "runner_trailing_stop",
                    "quantity": 1,
                    "target_remaining_quantity": 1,
                    "exit_allocation_target": "runners_only",
                    "exit_price": 1.20,
                },
                {"active_broker": "alpaca"},
                broker,
                schedule_monitor=None,
            )
        )

        self.assertEqual(trade["target_remaining_quantity"], 1)
        self.assertEqual(trade["exit_allocation_target"], "runners_only")
        self.assertEqual(db.positions[0]["exit_target_remaining_quantity"], 1)


if __name__ == "__main__":
    unittest.main()
