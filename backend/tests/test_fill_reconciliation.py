import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeLifecycleDb:
    def __init__(self):
        self.trade_updates = []
        self.alert_updates = []
        self.position_updates = []
        self.positions = {}
        self.inserted_positions = []

    async def update_trade(self, trade_id, updates):
        self.trade_updates.append((trade_id, updates))

    async def update_alert(self, alert_id, updates):
        self.alert_updates.append((alert_id, updates))

    async def insert_position(self, position):
        self.positions[position["id"]] = position
        self.inserted_positions.append(position)
        return position["id"]

    async def get_position_by_id(self, position_id):
        return self.positions.get(position_id)

    async def update_position(self, position_id, updates):
        self.position_updates.append((position_id, updates))
        position = dict(self.positions[position_id])
        if "$set" in updates:
            position.update(updates["$set"])
        if "$push" in updates:
            for key, value in updates["$push"].items():
                position.setdefault(key, []).append(value)
        if "$set" not in updates and "$push" not in updates:
            position.update(updates)
        self.positions[position_id] = position


class FillReconciliationTests(unittest.TestCase):
    def test_replayed_sell_fill_clears_stale_reservation_without_double_counting(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-replayed"] = {
            "id": "position-replayed",
            "entry_price": 0.35,
            "remaining_quantity": 2,
            "realized_pnl": 58.0,
            "trade_ids": ["entry", "stage-1", "stage-2"],
            "status": "partial",
            "exit_order_pending": True,
            "exit_order_id": "stage-2-order",
        }
        context = OrderContext(
            trade_id="stage-2",
            order_id="stage-2-order",
            side="SELL",
            ticker="SPY",
            strike=761.0,
            option_type="CALL",
            expiration="2026-09-10",
            requested_quantity=2,
            position_id="position-replayed",
            alert_price=0.64,
            exit_trigger="profit_stage_2",
            update_alert_status=False,
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=0.64),
            )
        )

        position = db.positions["position-replayed"]
        self.assertEqual(position["remaining_quantity"], 2)
        self.assertEqual(position["realized_pnl"], 58.0)
        self.assertFalse(position["exit_order_pending"])
        self.assertIsNone(position["exit_order_id"])

    def test_cancel_race_accounts_for_partial_fill_before_releasing_exit(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-race"] = {
            "id": "position-race",
            "entry_price": 0.28,
            "remaining_quantity": 5,
            "realized_pnl": 0.0,
            "trade_ids": ["entry-trade"],
            "status": "open",
            "exit_order_pending": True,
            "exit_order_id": "old-order",
        }
        context = OrderContext(
            trade_id="old-exit",
            order_id="old-order",
            side="SELL",
            ticker="SPY",
            strike=767.0,
            option_type="PUT",
            expiration="2026-09-04",
            requested_quantity=2,
            position_id="position-race",
            alert_price=0.38,
            update_alert_status=False,
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(
                    status="cancelled",
                    filled_qty=1,
                    avg_fill_price=0.38,
                    reason="cancel raced partial fill",
                ),
            )
        )

        position = db.positions["position-race"]
        self.assertEqual(position["remaining_quantity"], 4)
        self.assertFalse(position["exit_order_pending"])
        self.assertIsNone(position["exit_order_id"])

    def test_bot_managed_exit_does_not_overwrite_entry_alert(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-1"] = {
            "id": "position-1",
            "entry_price": 0.28,
            "remaining_quantity": 5,
            "realized_pnl": 40.0,
            "trade_ids": ["entry-trade", "stage-1-trade"],
            "status": "partial",
            "exit_order_pending": True,
        }
        context = OrderContext(
            trade_id="stage-2-trade",
            order_id="stage-2-order",
            side="SELL",
            ticker="SPY",
            strike=767.0,
            option_type="PUT",
            expiration="2026-09-04",
            requested_quantity=2,
            position_id="position-1",
            alert_id="entry-alert",
            alert_price=0.38,
            exit_trigger="profit_stage_2",
            update_alert_status=False,
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=0.38),
            )
        )

        self.assertEqual(db.alert_updates, [])
        self.assertEqual(db.positions["position-1"]["remaining_quantity"], 3)

    def test_filled_entry_persists_coordinated_risk_profile(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        context = OrderContext(
            trade_id="trade-risk-entry",
            order_id="order-risk-entry",
            side="BUY",
            ticker="DELL",
            strike=500.0,
            option_type="CALL",
            expiration="2026-09-04",
            requested_quantity=3,
            broker="alpaca",
            alert_id="alert-risk-entry",
            entry_risk_profile="high_risk",
            max_loss_budget=500.0,
            estimated_stop_loss_percent=50.0,
        )

        result = asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=3, avg_fill_price=4.50),
            )
        )

        position = db.positions[result.position_id]
        self.assertEqual(position["entry_risk_profile"], "high_risk")
        self.assertEqual(position["max_loss_budget"], 500.0)
        self.assertEqual(position["estimated_stop_loss_percent"], 50.0)
        self.assertFalse(position["profit_stage_1_completed"])
        self.assertFalse(position["profit_floor_armed"])

    def test_first_profit_stage_fill_arms_permanent_profit_floor(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-stage"] = {
            "id": "position-stage",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "2026-09-04",
            "entry_price": 1.00,
            "remaining_quantity": 8,
            "realized_pnl": 0.0,
            "trade_ids": ["trade-entry"],
            "status": "open",
            "exit_order_pending": True,
        }
        context = OrderContext(
            trade_id="trade-stage-1",
            order_id="order-stage-1",
            side="SELL",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="2026-09-04",
            requested_quantity=4,
            position_id="position-stage",
            exit_trigger="profit_stage_1",
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=4, avg_fill_price=1.25),
            )
        )

        position = db.positions["position-stage"]
        self.assertTrue(position["profit_stage_1_completed"])
        self.assertTrue(position["profit_floor_armed"])
        self.assertEqual(position["profit_floor_price"], 1.01)
        self.assertFalse(position["exit_order_pending"])

    def test_second_profit_stage_fill_marks_second_stage(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-stage"] = {
            "id": "position-stage",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "2026-09-04",
            "entry_price": 1.00,
            "remaining_quantity": 4,
            "realized_pnl": 100.0,
            "trade_ids": ["trade-entry", "trade-stage-1"],
            "status": "partial",
            "profit_stage_1_completed": True,
            "profit_floor_armed": True,
            "exit_order_pending": True,
        }
        context = OrderContext(
            trade_id="trade-stage-2",
            order_id="order-stage-2",
            side="SELL",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="2026-09-04",
            requested_quantity=2,
            position_id="position-stage",
            exit_trigger="profit_stage_2",
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.35),
            )
        )

        position = db.positions["position-stage"]
        self.assertTrue(position["profit_stage_2_completed"])
        self.assertFalse(position["exit_order_pending"])

    def test_rejected_exit_clears_exit_reservation(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-rejected"] = {
            "id": "position-rejected",
            "remaining_quantity": 2,
            "trade_ids": ["entry"],
            "exit_order_pending": True,
        }
        context = OrderContext(
            trade_id="trade-rejected",
            order_id="order-rejected",
            side="SELL",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="2026-09-04",
            requested_quantity=2,
            position_id="position-rejected",
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="rejected", reason="broker rejected"),
            )
        )

        self.assertFalse(db.positions["position-rejected"]["exit_order_pending"])

    def test_rejected_entry_order_does_not_leave_open_position(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        context = OrderContext(
            trade_id="trade-entry",
            order_id="order-entry",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
            alert_id="alert-entry",
        )

        result = asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="rejected", reason="insufficient buying power"),
            )
        )

        self.assertEqual(result.trade_status, "failed")
        self.assertEqual(db.trade_updates[0][1]["status"], "failed")
        self.assertEqual(db.trade_updates[0][1]["error_message"], "insufficient buying power")
        self.assertEqual(
            db.alert_updates,
            [
                (
                    "alert-entry",
                    {
                        "processed": True,
                        "trade_executed": False,
                        "trade_result": "failed: insufficient buying power",
                    },
                )
            ],
        )
        self.assertEqual(db.inserted_positions, [])

    def test_filled_entry_order_creates_open_position_from_fill_price(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        context = OrderContext(
            trade_id="trade-entry",
            order_id="order-entry",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=3,
            broker="alpaca",
            alert_id="alert-entry",
        )

        result = asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.35),
            )
        )

        self.assertEqual(result.trade_status, "executed")
        self.assertEqual(result.position_status, "open")
        self.assertEqual(db.trade_updates[0][1]["quantity"], 2)
        self.assertEqual(db.trade_updates[0][1]["entry_price"], 1.35)
        self.assertEqual(
            db.alert_updates,
            [
                (
                    "alert-entry",
                    {
                        "processed": True,
                        "trade_executed": True,
                        "trade_result": "filled",
                    },
                )
            ],
        )
        position = db.inserted_positions[0]
        self.assertEqual(position["ticker"], "SPY")
        self.assertEqual(position["original_quantity"], 2)
        self.assertEqual(position["remaining_quantity"], 2)
        self.assertEqual(position["entry_price"], 1.35)
        self.assertEqual(position["total_cost"], 270.0)

    def test_filled_entry_order_adds_metadata_oco_plan_from_actual_fill_price(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        context = OrderContext(
            trade_id="trade-entry",
            order_id="order-entry",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
            alert_id="alert-entry",
            alert_price=2.00,
        )
        settings = {
            "take_profit_enabled": True,
            "take_profit_percentage": 50.0,
            "stop_loss_enabled": True,
            "stop_loss_percentage": 20.0,
            "stop_loss_order_type": "market",
            "trailing_stop_enabled": True,
            "trailing_stop_type": "percent",
            "trailing_stop_percent": 10.0,
        }

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.35),
                settings=settings,
            )
        )

        position = db.inserted_positions[0]
        plan = position["oco_exit_plan"]
        self.assertEqual(plan["entry_price"], 1.35)
        self.assertEqual(plan["quantity"], 2)
        self.assertEqual(plan["take_profit"]["trigger_price"], 2.03)
        self.assertEqual(plan["stop_loss"]["trigger_price"], 1.08)
        self.assertEqual(position["oco_exit_status"], "metadata_only")
        self.assertFalse(position["oco_exit_protected"])

    def test_repeated_filled_entry_order_does_not_insert_duplicate_position(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        context = OrderContext(
            trade_id="trade-entry",
            order_id="order-entry",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            broker="alpaca",
            alert_id="alert-entry",
        )
        update = BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.35)

        first = asyncio.run(reconcile_order_update(db, context, update))
        second = asyncio.run(reconcile_order_update(db, context, update))

        self.assertEqual(first.position_id, second.position_id)
        self.assertEqual(len(db.inserted_positions), 1)
        self.assertEqual(db.inserted_positions[0]["remaining_quantity"], 2)

    def test_multiple_filled_entries_for_same_contract_share_one_position(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        first_context = OrderContext(
            trade_id="trade-entry-1",
            order_id="order-entry-1",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21/2026",
            requested_quantity=2,
            broker="alpaca",
            alert_id="alert-entry-1",
        )
        second_context = OrderContext(
            trade_id="trade-entry-2",
            order_id="order-entry-2",
            side="BUY",
            ticker="spy",
            strike=500.0,
            option_type="call",
            expiration="2026-06-21",
            requested_quantity=1,
            broker="alpaca",
            alert_id="alert-entry-2",
        )

        first = asyncio.run(
            reconcile_order_update(
                db,
                first_context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.00),
            )
        )
        second = asyncio.run(
            reconcile_order_update(
                db,
                second_context,
                BrokerOrderUpdate(status="filled", filled_qty=1, avg_fill_price=0.80),
            )
        )

        self.assertEqual(first.position_id, second.position_id)
        self.assertEqual(len(db.inserted_positions), 1)
        position = db.positions[first.position_id]
        self.assertEqual(position["remaining_quantity"], 3)
        self.assertEqual(position["original_quantity"], 3)
        self.assertAlmostEqual(position["entry_price"], 0.9333333333)
        self.assertEqual(position["total_cost"], 280.0)
        self.assertEqual(position["trade_ids"], ["trade-entry-1", "trade-entry-2"])

    def test_filled_entry_reopens_closed_contract_with_fresh_cost_basis(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        position_id = "position-alpaca-dell-260904-c-500"
        db.positions[position_id] = {
            "id": position_id,
            "ticker": "DELL",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "2026-09-04",
            "entry_price": 4.50,
            "current_price": 2.21,
            "highest_price": 5.375,
            "original_quantity": 10,
            "remaining_quantity": 0,
            "total_cost": 4500.0,
            "average_down_count": 1,
            "trade_ids": ["old-buy", "old-sell"],
            "status": "closed",
            "closed_at": "2026-09-02T13:35:44+00:00",
            "realized_pnl": -2290.0,
            "reversal_state": "confirmed",
            "reversal_conflict_count": 4,
            "reversal_warning_completed": True,
            "broker": "alpaca",
        }
        context = OrderContext(
            trade_id="new-buy",
            order_id="new-order",
            side="BUY",
            ticker="DELL",
            strike=500.0,
            option_type="CALL",
            expiration="09/04/26",
            requested_quantity=5,
            broker="alpaca",
            alert_id="new-alert",
        )

        result = asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=5, avg_fill_price=2.00),
                settings={
                    "take_profit_enabled": True,
                    "take_profit_percentage": 35,
                    "stop_loss_enabled": True,
                    "stop_loss_percentage": 50,
                },
            )
        )

        position = db.positions[position_id]
        self.assertEqual(result.position_id, position_id)
        self.assertEqual(position["status"], "open")
        self.assertEqual(position["entry_price"], 2.00)
        self.assertEqual(position["initial_entry_price"], 2.00)
        self.assertEqual(position["highest_price"], 2.00)
        self.assertEqual(position["original_quantity"], 5)
        self.assertEqual(position["remaining_quantity"], 5)
        self.assertEqual(position["total_cost"], 1000.0)
        self.assertEqual(position["average_down_count"], 0)
        self.assertEqual(position["realized_pnl"], 0.0)
        self.assertEqual(position["trade_ids"], ["new-buy"])
        self.assertIsNone(position["closed_at"])
        self.assertEqual(position["reversal_state"], "")
        self.assertEqual(position["reversal_conflict_count"], 0)
        self.assertFalse(position["reversal_warning_completed"])
        self.assertEqual(position["oco_exit_plan"]["entry_price"], 2.00)
        self.assertEqual(position["oco_exit_plan"]["quantity"], 5)

    def test_entry_fill_attaches_to_unlinked_broker_reconciled_position_without_doubling_quantity(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-alpaca-spy-260831-p-763"] = {
            "id": "position-alpaca-spy-260831-p-763",
            "ticker": "SPY",
            "strike": 763.0,
            "option_type": "PUT",
            "expiration": "2026-08-31",
            "entry_price": 0.42,
            "current_price": 0.42,
            "highest_price": 0.42,
            "original_quantity": 10,
            "remaining_quantity": 10,
            "total_cost": 420.0,
            "average_down_count": 0,
            "trade_ids": [],
            "status": "open",
            "broker": "alpaca",
            "reconciled_from_broker_only": True,
            "coordinated_loss_ladder_completed_steps": [0, 1, 2, 3],
            "coordinated_stop_confirmation_count": 2,
            "coordinated_break_even_confirmation_count": 2,
            "counterfactual_stop_hits": {"25": "old"},
            "counterfactual_trailing_hits": {"10": "old"},
            "premium_mark_history": [0.75, 0.42],
            "coordinated_trailing_floor": 0.70,
            "exit_target_remaining_quantity": 0,
        }
        context = OrderContext(
            trade_id="trade-entry",
            order_id="order-entry",
            side="BUY",
            ticker="SPY",
            strike=763.0,
            option_type="PUT",
            expiration="08/31/26",
            requested_quantity=10,
            broker="alpaca",
            alert_id="alert-entry",
        )

        result = asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=10, avg_fill_price=0.42),
            )
        )

        self.assertEqual(result.trade_status, "executed")
        self.assertEqual(result.position_status, "open")
        self.assertEqual(len(db.inserted_positions), 0)
        position = db.positions["position-alpaca-spy-260831-p-763"]
        self.assertEqual(position["remaining_quantity"], 10)
        self.assertEqual(position["original_quantity"], 10)
        self.assertEqual(position["total_cost"], 420.0)
        self.assertEqual(position["average_down_count"], 0)
        self.assertEqual(position["trade_ids"], ["trade-entry"])
        self.assertFalse(position["reconciled_from_broker_only"])
        self.assertTrue(position["broker_reconciled_entry_attached"])
        self.assertEqual(position["coordinated_loss_ladder_completed_steps"], [])
        self.assertEqual(position["coordinated_stop_confirmation_count"], 0)
        self.assertEqual(position["coordinated_break_even_confirmation_count"], 0)
        self.assertEqual(position["counterfactual_stop_hits"], {})
        self.assertEqual(position["counterfactual_trailing_hits"], {})
        self.assertEqual(position["premium_mark_history"], [])
        self.assertIsNone(position["coordinated_trailing_floor"])
        self.assertIsNone(position["exit_target_remaining_quantity"])

    def test_entry_fill_attaches_to_broker_reconciled_position_using_broker_quantity_as_authority(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-alpaca-spy-260831-p-763"] = {
            "id": "position-alpaca-spy-260831-p-763",
            "ticker": "SPY",
            "strike": 763.0,
            "option_type": "PUT",
            "expiration": "2026-08-31",
            "entry_price": 0.42,
            "current_price": 0.42,
            "highest_price": 0.42,
            "original_quantity": 4,
            "remaining_quantity": 4,
            "total_cost": 168.0,
            "average_down_count": 0,
            "trade_ids": [],
            "status": "open",
            "broker": "alpaca",
            "reconciled_from_broker_only": True,
        }
        context = OrderContext(
            trade_id="trade-entry",
            order_id="order-entry",
            side="BUY",
            ticker="SPY",
            strike=763.0,
            option_type="PUT",
            expiration="08/31/26",
            requested_quantity=10,
            broker="alpaca",
            alert_id="alert-entry",
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=10, avg_fill_price=0.42),
            )
        )

        position = db.positions["position-alpaca-spy-260831-p-763"]
        self.assertEqual(position["remaining_quantity"], 4)
        self.assertEqual(position["original_quantity"], 4)
        self.assertEqual(position["total_cost"], 168.0)

    def test_filled_average_down_buy_updates_existing_position(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-1"] = {
            "id": "position-1",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "entry_price": 1.00,
            "original_quantity": 4,
            "remaining_quantity": 4,
            "total_cost": 400.0,
            "average_down_count": 0,
            "initial_entry_price": None,
            "trade_ids": ["trade-entry"],
            "status": "open",
            "broker": "alpaca",
            "simulated": False,
        }
        context = OrderContext(
            trade_id="trade-average-down",
            order_id="order-average-down",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            position_id="position-1",
            broker="alpaca",
            alert_id="alert-average-down",
        )

        result = asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=0.80),
            )
        )

        self.assertEqual(result.trade_status, "executed")
        self.assertEqual(result.position_status, "open")
        self.assertEqual(len(db.inserted_positions), 0)
        trade_update = db.trade_updates[0][1]
        self.assertEqual(trade_update["side"], "BUY")
        self.assertEqual(trade_update["quantity"], 2)
        self.assertEqual(trade_update["entry_price"], 0.80)
        position = db.positions["position-1"]
        self.assertEqual(position["remaining_quantity"], 6)
        self.assertEqual(position["original_quantity"], 6)
        self.assertAlmostEqual(position["entry_price"], 0.9333333333)
        self.assertEqual(position["total_cost"], 560.0)
        self.assertEqual(position["average_down_count"], 1)
        self.assertEqual(position["initial_entry_price"], 1.00)
        self.assertIn("trade-average-down", position["trade_ids"])
        self.assertEqual(
            db.alert_updates,
            [
                (
                    "alert-average-down",
                    {
                        "processed": True,
                        "trade_executed": True,
                        "trade_result": "filled",
                    },
                )
            ],
        )

    def test_filled_exit_order_reduces_remaining_quantity_and_closes_when_zero(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-1"] = {
            "id": "position-1",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "entry_price": 1.00,
            "remaining_quantity": 2,
            "realized_pnl": 25.0,
            "unrealized_pnl": -20.0,
            "trade_ids": ["trade-entry"],
            "status": "partial",
            "broker": "alpaca",
            "simulated": False,
        }
        context = OrderContext(
            trade_id="trade-exit",
            order_id="order-exit",
            side="SELL",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            position_id="position-1",
            broker="alpaca",
        )

        result = asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.50),
            )
        )

        self.assertEqual(result.trade_status, "executed")
        self.assertEqual(result.position_status, "closed")
        trade_update = db.trade_updates[0][1]
        self.assertEqual(trade_update["side"], "SELL")
        self.assertEqual(trade_update["exit_price"], 1.50)
        self.assertEqual(trade_update["realized_pnl"], 100.0)
        position = db.positions["position-1"]
        self.assertEqual(position["remaining_quantity"], 0)
        self.assertEqual(position["status"], "closed")
        self.assertEqual(position["realized_pnl"], 125.0)
        self.assertEqual(position["unrealized_pnl"], 0.0)
        self.assertIn("trade-exit", position["trade_ids"])
        self.assertIn("closed_at", position)

    def test_core_only_fill_preserves_dedicated_runner(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-runner"] = {
            "id": "position-runner",
            "entry_price": 1.00,
            "remaining_quantity": 4,
            "realized_pnl": 0.0,
            "trade_ids": ["trade-entry"],
            "status": "open",
            "core_runner_candidate_quantity": 1,
            "core_runner_dedicated_quantity": 1,
            "core_runner_core_quantity": 3,
            "core_runner_activated": True,
        }
        context = OrderContext(
            trade_id="trade-core-exit",
            order_id="order-core-exit",
            side="SELL",
            ticker="SPY",
            strike=775.0,
            option_type="CALL",
            expiration="2026-09-25",
            requested_quantity=2,
            position_id="position-runner",
            exit_trigger="profit_stage_2",
            exit_allocation_target="core_only",
            target_remaining_quantity=2,
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.50),
            )
        )

        position = db.positions["position-runner"]
        self.assertEqual(position["remaining_quantity"], 2)
        self.assertEqual(position["core_runner_dedicated_quantity"], 1)
        self.assertEqual(position["core_runner_candidate_quantity"], 1)
        self.assertEqual(position["core_runner_core_quantity"], 1)

    def test_runner_only_fill_reduces_dedicated_runner(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-runner"] = {
            "id": "position-runner",
            "entry_price": 1.00,
            "remaining_quantity": 2,
            "realized_pnl": 0.0,
            "trade_ids": ["trade-entry"],
            "status": "partial",
            "core_runner_candidate_quantity": 1,
            "core_runner_dedicated_quantity": 1,
            "core_runner_core_quantity": 1,
            "core_runner_activated": True,
        }
        context = OrderContext(
            trade_id="trade-runner-exit",
            order_id="order-runner-exit",
            side="SELL",
            ticker="SPY",
            strike=775.0,
            option_type="CALL",
            expiration="2026-09-25",
            requested_quantity=1,
            position_id="position-runner",
            exit_trigger="runner_trailing_stop",
            exit_allocation_target="runners_only",
            target_remaining_quantity=1,
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=1, avg_fill_price=1.20),
            )
        )

        position = db.positions["position-runner"]
        self.assertEqual(position["remaining_quantity"], 1)
        self.assertEqual(position["core_runner_dedicated_quantity"], 0)
        self.assertEqual(position["core_runner_candidate_quantity"], 0)
        self.assertEqual(position["core_runner_core_quantity"], 1)

    def test_partial_core_fill_recomputes_core_from_broker_remainder(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-runner"] = {
            "id": "position-runner",
            "entry_price": 1.00,
            "remaining_quantity": 5,
            "realized_pnl": 0.0,
            "trade_ids": ["trade-entry"],
            "status": "open",
            "core_runner_candidate_quantity": 2,
            "core_runner_dedicated_quantity": 2,
            "core_runner_core_quantity": 3,
            "core_runner_activated": True,
        }
        context = OrderContext(
            trade_id="trade-partial-core-exit",
            order_id="order-partial-core-exit",
            side="SELL",
            ticker="SPY",
            strike=775.0,
            option_type="CALL",
            expiration="2026-09-25",
            requested_quantity=3,
            position_id="position-runner",
            exit_trigger="coordinated_hard_stop",
            exit_allocation_target="core_only",
            target_remaining_quantity=2,
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="partial", filled_qty=1, avg_fill_price=0.80),
            )
        )

        position = db.positions["position-runner"]
        self.assertEqual(position["remaining_quantity"], 4)
        self.assertEqual(position["core_runner_dedicated_quantity"], 2)
        self.assertEqual(position["core_runner_core_quantity"], 2)

    def test_repeated_filled_exit_order_does_not_reduce_position_twice(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-1"] = {
            "id": "position-1",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "entry_price": 1.00,
            "remaining_quantity": 2,
            "realized_pnl": 0.0,
            "trade_ids": ["trade-entry"],
            "status": "open",
            "broker": "alpaca",
            "simulated": False,
        }
        context = OrderContext(
            trade_id="trade-exit",
            order_id="order-exit",
            side="SELL",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=1,
            position_id="position-1",
            broker="alpaca",
        )
        update = BrokerOrderUpdate(status="filled", filled_qty=1, avg_fill_price=1.50)

        asyncio.run(reconcile_order_update(db, context, update))
        asyncio.run(reconcile_order_update(db, context, update))

        position = db.positions["position-1"]
        self.assertEqual(position["remaining_quantity"], 1)
        self.assertEqual(position["realized_pnl"], 50.0)
        self.assertEqual(position["trade_ids"].count("trade-exit"), 1)
        self.assertEqual(len(db.position_updates), 1)

    def test_partial_take_profit_fill_marks_stage_completed(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-1"] = {
            "id": "position-1",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "entry_price": 1.00,
            "remaining_quantity": 10,
            "realized_pnl": 0.0,
            "trade_ids": ["trade-entry"],
            "status": "open",
            "broker": "alpaca",
        }
        context = OrderContext(
            trade_id="trade-tp1",
            order_id="order-tp1",
            side="SELL",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=5,
            position_id="position-1",
            broker="alpaca",
            exit_trigger="take_profit",
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=5, avg_fill_price=1.40),
            )
        )

        position = db.positions["position-1"]
        self.assertEqual(position["remaining_quantity"], 5)
        self.assertTrue(position["take_profit_stage_completed"])
        self.assertIn("take_profit_stage_completed_at", position)

    def test_reversal_warning_fill_marks_warning_completed(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-1"] = {
            "id": "position-1",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "entry_price": 1.00,
            "remaining_quantity": 8,
            "realized_pnl": 0.0,
            "trade_ids": ["trade-entry"],
            "status": "open",
            "broker": "alpaca",
        }
        context = OrderContext(
            trade_id="trade-reversal-warning",
            order_id="order-reversal-warning",
            side="SELL",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="6/21",
            requested_quantity=2,
            position_id="position-1",
            broker="alpaca",
            exit_trigger="reversal_warning",
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=1.20),
            )
        )

        self.assertTrue(db.positions["position-1"]["reversal_warning_completed"])
        self.assertIn("reversal_warning_completed_at", db.positions["position-1"])

    def test_loss_ladder_fill_marks_only_that_step_completed(self):
        from fill_reconciliation import BrokerOrderUpdate, OrderContext, reconcile_order_update

        db = FakeLifecycleDb()
        db.positions["position-1"] = {
            "id": "position-1",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "PUT",
            "expiration": "6/21",
            "entry_price": 1.00,
            "remaining_quantity": 9,
            "realized_pnl": 0.0,
            "trade_ids": ["trade-entry"],
            "status": "open",
            "broker": "alpaca",
            "coordinated_loss_ladder_completed_steps": [0],
            "coordinated_loss_ladder_pending_step": 1,
        }
        context = OrderContext(
            trade_id="trade-loss-ladder",
            order_id="order-loss-ladder",
            side="SELL",
            ticker="SPY",
            strike=500.0,
            option_type="PUT",
            expiration="6/21",
            requested_quantity=2,
            position_id="position-1",
            broker="alpaca",
            exit_trigger="loss_ladder_2",
        )

        asyncio.run(
            reconcile_order_update(
                db,
                context,
                BrokerOrderUpdate(status="filled", filled_qty=2, avg_fill_price=0.80),
            )
        )

        position = db.positions["position-1"]
        self.assertEqual(position["coordinated_loss_ladder_completed_steps"], [0, 1])
        self.assertIsNone(position["coordinated_loss_ladder_pending_step"])


if __name__ == "__main__":
    unittest.main()
