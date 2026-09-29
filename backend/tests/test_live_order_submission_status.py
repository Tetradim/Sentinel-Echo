import asyncio
import os
import pathlib
import sys
import unittest
from datetime import datetime, timezone


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
        self.positions_by_status = {"open": [], "partial": [], "closed": []}
        self.inserted_trades = []
        self.updated_positions = []
        self.operator_events = []
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

    async def get_trades(self, limit=500):
        return list(reversed(self.inserted_trades))[:limit]

    async def update_trade(self, trade_id, updates):
        for trade in self.inserted_trades:
            if trade.get("id") == trade_id:
                trade.update(updates)
                return

    async def get_position_by_id(self, position_id):
        for positions in self.positions_by_status.values():
            for position in positions:
                if position.get("id") == position_id:
                    return position
        return None

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

    async def insert_operator_event(self, event):
        self.operator_events.append(event)
        return event["id"]


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


class CancelledExitBrokerClient(FakeBrokerClient):
    def __init__(self):
        self.cancelled = []

    async def cancel_order(self, order_id):
        self.cancelled.append(order_id)
        return {"status": "cancel_requested", "cancel_requested": True}

    async def get_order_status(self, order_id):
        return {"status": "cancelled", "filled_qty": 0, "avg_fill_price": 0.0}


class FreshQuoteBrokerClient(FakeBrokerClient):
    async def get_option_market_context(self, **kwargs):
        return {
            "option_bid": 0.91,
            "option_ask": 0.94,
            "option_quote_observed_at": "2026-09-03T13:51:10Z",
        }


class FailingPositionLookupBrokerClient(FakeBrokerClient):
    async def list_positions(self):
        raise TimeoutError("Alpaca positions timed out")


class ClosableNoPositionsBrokerClient(FakeBrokerClient):
    def __init__(self):
        self.closed = False

    async def list_positions(self):
        return []

    async def close(self):
        self.closed = True


async def allow_correlation(**kwargs):
    return True, ""


async def fail_correlation(**kwargs):
    raise RuntimeError("risk database unavailable")


async def fake_monitor_fill(**kwargs):
    return None


async def fake_notify_correlation_block(**kwargs):
    return None


class LiveOrderSubmissionStatusTests(unittest.TestCase):
    def test_contextual_analyst_exit_preserves_dedicated_runner(self):
        import server

        plan = server._cap_analyst_exit_plan(
            {
                "position": {
                    "id": "position-767p",
                    "entry_price": 0.28,
                    "current_price": 0.36,
                    "remaining_quantity": 3,
                    "original_quantity": 10,
                    "core_runner_candidate_quantity": 1,
                    "core_runner_dedicated_quantity": 1,
                    "core_runner_activated": True,
                },
                "quantity": 3,
                "percentage": 100.0,
            },
            {
                "alert_type": "sell",
                "ticker": "SPY",
                "strike": 767.0,
                "option_type": "PUT",
                "expiration": "2026-09-04",
                "sell_percentage": 100.0,
                "inferred_from_position_id": "position-767p",
            },
            {
                "core_runner_enabled": True,
                "core_runner_fixed_contracts": 1,
                "core_runner_allocation_mode": "fixed",
                "core_runner_protect_contextual_trims": True,
                "core_runner_contextual_full_exit_overrides": False,
            },
        )

        self.assertEqual(plan["quantity"], 2)
        self.assertEqual(plan["target_remaining_quantity"], 1)
        self.assertEqual(plan["runner_audit"]["protected_quantity"], 1)

    def test_explicit_analyst_exit_at_override_threshold_can_close_runner(self):
        import server

        plan = server._cap_analyst_exit_plan(
            {
                "position": {
                    "id": "position-767p",
                    "entry_price": 0.28,
                    "current_price": 0.36,
                    "remaining_quantity": 3,
                    "original_quantity": 10,
                    "core_runner_candidate_quantity": 1,
                    "core_runner_dedicated_quantity": 1,
                    "core_runner_activated": True,
                },
                "quantity": 3,
                "percentage": 90.0,
            },
            {
                "alert_type": "sell",
                "ticker": "SPY",
                "strike": 767.0,
                "option_type": "PUT",
                "expiration": "2026-09-04",
                "sell_percentage": 90.0,
            },
            {
                "core_runner_enabled": True,
                "core_runner_fixed_contracts": 1,
                "core_runner_allocation_mode": "fixed",
                "core_runner_analyst_override_percent": 80.0,
                "core_runner_explicit_full_exit_overrides": True,
            },
        )

        self.assertEqual(plan["quantity"], 3)
        self.assertEqual(plan["target_remaining_quantity"], 0)
        self.assertEqual(plan["exit_allocation_target"], "entire_position")
        self.assertTrue(plan["runner_audit"]["explicit_override"])

    def test_explicit_eighty_percent_contract_exit_without_expiration_overrides_trailing(self):
        import server

        position = {
            "id": "position-761c",
            "ticker": "SPY",
            "strike": 761.0,
            "option_type": "CALL",
            "expiration": "2026-09-10",
            "entry_price": 0.35,
            "highest_executable_bid": 0.62,
            "coordinated_trailing_armed": True,
        }
        parsed = {
            "alert_type": "sell",
            "ticker": "SPY",
            "strike": 761.0,
            "option_type": "CALL",
            "expiration": None,
            "sell_percentage": 90.0,
        }

        self.assertFalse(
            server._contextual_exit_is_trailing_protected(
                position,
                parsed,
                {"coordinated_exit_enabled": True},
                {
                    "protect_trailing_armed_from_contextual_exits": True,
                    "trailing_context_exit_override_percent": 80.0,
                },
            )
        )

    def test_contextual_full_exit_does_not_override_trailing_protected_contract(self):
        import server

        position = {
            "id": "position-767p",
            "ticker": "SPY",
            "strike": 767.0,
            "option_type": "PUT",
            "expiration": "2026-09-04",
            "entry_price": 0.28,
            "highest_executable_bid": 0.38,
            "coordinated_trailing_armed": True,
        }
        parsed = {
            "alert_type": "sell",
            "ticker": "SPY",
            "strike": 767.0,
            "option_type": "PUT",
            "expiration": "2026-09-04",
            "sell_percentage": 100.0,
            "inferred_from_position_id": "position-767p",
        }

        self.assertTrue(
            server._contextual_exit_is_trailing_protected(
                position,
                parsed,
                {"coordinated_exit_enabled": True},
                {"protect_trailing_armed_from_contextual_exits": True},
            )
        )
        explicit = dict(parsed)
        explicit.pop("inferred_from_position_id")
        self.assertFalse(
            server._contextual_exit_is_trailing_protected(
                position,
                explicit,
                {"coordinated_exit_enabled": True},
                {"protect_trailing_armed_from_contextual_exits": True},
            )
        )

    def test_process_exit_skips_order_for_trailing_protected_contextual_alert(self):
        from models import Alert, Settings
        import server

        db = FakeRuntimeDb()
        db.positions_by_status["partial"] = [
            {
                "id": "position-767p",
                "alert_id": "entry-767p",
                "ticker": "SPY",
                "strike": 767.0,
                "option_type": "PUT",
                "expiration": "2026-09-04",
                "entry_price": 0.28,
                "current_price": 0.36,
                "highest_executable_bid": 0.38,
                "original_quantity": 10,
                "remaining_quantity": 3,
                "total_cost": 280.0,
                "broker": "alpaca",
                "status": "partial",
                "realized_pnl": 60.0,
                "simulated": False,
                "trade_ids": ["entry", "stage-1", "stage-2"],
                "coordinated_trailing_armed": True,
            }
        ]
        originals = self.patch_server(server, fake_db=db)
        parsed = {
            "alert_type": "sell",
            "ticker": "SPY",
            "strike": 767.0,
            "option_type": "PUT",
            "expiration": "2026-09-04",
            "sell_percentage": 100.0,
            "inferred_from_position_id": "position-767p",
        }
        settings_raw = {
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "coordinated_exit_enabled": True,
        }
        try:
            processed = asyncio.run(
                server.process_exit_alert(
                    Alert(
                        id="contextual-out",
                        ticker="SPY",
                        strike=767.0,
                        option_type="PUT",
                        expiration="2026-09-04",
                        entry_price=0.36,
                        alert_type="sell",
                        sell_percentage=100.0,
                    ),
                    parsed,
                    Settings(**settings_raw),
                    settings_raw,
                    source_config={"protect_trailing_armed_from_contextual_exits": True},
                )
            )
        finally:
            self.restore_server(server, originals)

        self.assertFalse(processed)
        self.assertEqual(FakeBrokerClient.orders, [])
        self.assertIn("trailing-protected", parsed["_exit_skip_reason"])

    def test_newer_full_exit_cancels_smaller_resting_exit_before_replacement(self):
        import order_execution
        import server

        db = FakeRuntimeDb()
        position = {
            "id": "position-767p",
            "alert_id": "entry-alert-767p",
            "ticker": "SPY",
            "strike": 767.0,
            "option_type": "PUT",
            "expiration": "2026-09-04",
            "entry_price": 0.28,
            "remaining_quantity": 5,
            "realized_pnl": 40.0,
            "trade_ids": ["entry-trade", "stage-1-trade"],
            "status": "partial",
            "broker": "alpaca",
            "exit_order_pending": True,
            "exit_order_id": "stage-2-order",
            "exit_reservation_token": "reservation",
        }
        db.positions_by_status["partial"].append(position)
        db.inserted_trades.append(
            {
                "id": "stage-2-trade",
                "alert_id": "entry-alert-767p",
                "alert_status_owned": False,
                "position_id": "position-767p",
                "ticker": "SPY",
                "strike": 767.0,
                "option_type": "PUT",
                "expiration": "2026-09-04",
                "exit_price": 0.38,
                "quantity": 2,
                "side": "SELL",
                "broker": "alpaca",
                "status": "pending_broker",
                "order_id": "stage-2-order",
                "exit_trigger": "profit_stage_2",
            }
        )
        broker = CancelledExitBrokerClient()
        original = order_execution.get_configured_broker_client
        order_execution.get_configured_broker_client = lambda *args, **kwargs: broker
        try:
            superseded = asyncio.run(
                server._supersede_pending_exit_order(
                    db,
                    position,
                    requested_quantity=5,
                    requested_percentage=100.0,
                    settings_raw={"active_broker": "alpaca"},
                )
            )
        finally:
            order_execution.get_configured_broker_client = original

        self.assertTrue(superseded)
        self.assertEqual(broker.cancelled, ["stage-2-order"])
        self.assertFalse(position["exit_order_pending"])
        self.assertIsNone(position["exit_order_id"])
        self.assertEqual(db.inserted_trades[0]["status"], "failed")

    def test_process_exit_replaces_smaller_resting_order_with_remaining_quantity(self):
        from models import Alert, Settings
        import order_execution
        import server

        db = FakeRuntimeDb()
        position = {
            "id": "position-767p",
            "alert_id": "entry-alert-767p",
            "ticker": "SPY",
            "strike": 767.0,
            "option_type": "PUT",
            "expiration": "2026-09-04",
            "entry_price": 0.28,
            "current_price": 0.38,
            "original_quantity": 10,
            "remaining_quantity": 5,
            "total_cost": 280.0,
            "realized_pnl": 40.0,
            "trade_ids": ["entry-trade", "stage-1-trade"],
            "status": "partial",
            "broker": "alpaca",
            "simulated": False,
            "exit_order_pending": True,
            "exit_order_id": "stage-2-order",
            "exit_reservation_token": "reservation",
        }
        db.positions_by_status["partial"].append(position)
        db.inserted_trades.append(
            {
                "id": "stage-2-trade",
                "alert_id": "entry-alert-767p",
                "alert_status_owned": False,
                "position_id": "position-767p",
                "ticker": "SPY",
                "strike": 767.0,
                "option_type": "PUT",
                "expiration": "2026-09-04",
                "exit_price": 0.38,
                "quantity": 2,
                "side": "SELL",
                "broker": "alpaca",
                "status": "pending_broker",
                "order_id": "stage-2-order",
                "exit_trigger": "profit_stage_2",
            }
        )
        broker = CancelledExitBrokerClient()
        originals = self.patch_server(server, fake_db=db)
        order_execution.get_configured_broker_client = lambda *args, **kwargs: broker
        settings_raw = {
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
        }
        try:
            processed = asyncio.run(
                server.process_exit_alert(
                    Alert(
                        id="analyst-out-alert",
                        ticker="SPY",
                        strike=767.0,
                        option_type="PUT",
                        expiration="2026-09-04",
                        entry_price=0.38,
                        alert_type="sell",
                        sell_percentage=100.0,
                    ),
                    {
                        "alert_type": "sell",
                        "ticker": "SPY",
                        "strike": 767.0,
                        "option_type": "PUT",
                        "expiration": "2026-09-04",
                        "entry_price": 0.38,
                        "sell_percentage": 100.0,
                    },
                    Settings(active_broker="alpaca", broker_configs=settings_raw["broker_configs"]),
                    settings_raw,
                    source_config={},
                )
            )
        finally:
            self.restore_server(server, originals)

        self.assertTrue(processed)
        self.assertEqual(broker.cancelled, [])
        self.assertEqual(broker.orders[-1]["quantity"], 5)
        self.assertEqual(db.inserted_trades[-1]["alert_id"], "analyst-out-alert")
        self.assertEqual(db.inserted_trades[-1]["status"], "pending")

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

    def test_removed_mode_flags_do_not_block_live_like_buy(self):
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "simulation_mode": True,
            "default_quantity": 1,
            "max_position_size": 1000.0,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        fake_db.runtime_state["live_trading_armed"] = False
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db, live_role=False)
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-legacy-flags",
                        ticker="SPY",
                        strike=500.0,
                        option_type="CALL",
                        expiration="6/21",
                        entry_price=1.25,
                    ),
                    {
                        "alert_type": "buy",
                        "_force_simulation": True,
                        "_source_config": {
                            "paper_shadow": True,
                            "paper_only": True,
                            "require_manual_confirm": True,
                        },
                    },
                )
            )
        finally:
            self.restore_server(server, originals)

        self.assertEqual(len(FakeBrokerClient.orders), 1)
        self.assertEqual(fake_mongo.trades.inserted[0]["status"], "pending")
        self.assertFalse(fake_mongo.trades.inserted[0]["simulated"])
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-legacy-flags"},
                    {"$set": {"processed": True, "trade_executed": False}},
                )
            ],
        )

    def test_entry_alignment_reduces_order_quantity_and_persists_decision(self):
        from entry_alignment import EntryAlignmentDecision
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "default_quantity": 10,
            "max_position_size": 5000.0,
            "smart_sizing_enabled": True,
            "smart_sizing_agreement_percent": 100.0,
            "smart_sizing_mixed_percent": 50.0,
            "smart_sizing_conflict_percent": 25.0,
            "risk_budget_sizing_enabled": False,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        original_resolver = server.resolve_entry_alignment

        async def conflict_alignment(*args, **kwargs):
            return EntryAlignmentDecision(
                tier="conflict",
                alignment_score=-3.0,
                underlying_score=-3.0,
                multiplier_percent=25.0,
                quote_spread_percent=10.0,
                reasons=["underlying trend conflicts with CALL"],
                context_available=True,
                source="alpaca",
            )

        server.resolve_entry_alignment = conflict_alignment
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-smart-size",
                        ticker="SPY",
                        strike=765.0,
                        option_type="CALL",
                        expiration="09/01/26",
                        entry_price=1.00,
                    ),
                    {"alert_type": "buy"},
                )
            )
        finally:
            server.resolve_entry_alignment = original_resolver
            self.restore_server(server, originals)

        self.assertEqual(FakeBrokerClient.orders[0]["quantity"], 2)
        trade = fake_mongo.trades.inserted[0]
        self.assertEqual(trade["entry_alignment_tier"], "conflict")
        self.assertEqual(trade["entry_alignment_score"], -3.0)
        self.assertEqual(trade["entry_sizing_percent"], 25.0)
        self.assertEqual(fake_db.operator_events[-1]["action"], "entry_size_selected")
        self.assertEqual(fake_db.operator_events[-1]["details"]["base_quantity"], 10)
        self.assertEqual(fake_db.operator_events[-1]["details"]["selected_quantity"], 2)

    def test_high_risk_lotto_language_caps_market_aligned_order_quantity(self):
        from entry_alignment import EntryAlignmentDecision
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "default_quantity": 10,
            "max_position_size": 5000.0,
            "smart_sizing_enabled": True,
            "smart_sizing_agreement_percent": 100.0,
            "smart_sizing_mixed_percent": 50.0,
            "smart_sizing_conflict_percent": 25.0,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        original_resolver = server.resolve_entry_alignment

        async def agreement_alignment(*args, **kwargs):
            return EntryAlignmentDecision(
                tier="agreement",
                alignment_score=3.0,
                underlying_score=-3.0,
                multiplier_percent=100.0,
                quote_spread_percent=4.88,
                reasons=["underlying trend supports PUT"],
                context_available=True,
                source="alpaca",
            )

        server.resolve_entry_alignment = agreement_alignment
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-high-risk-lotto",
                        ticker="SPY",
                        strike=762.0,
                        option_type="PUT",
                        expiration="09/02/26",
                        entry_price=0.20,
                        raw_message=(
                            "$SPY $762 PUTS EXPIRATION 9/2/2026 $.20 Entry "
                            "high risk lotto, size for $0, sized for a full loss"
                        ),
                    ),
                    {"alert_type": "buy"},
                )
            )
        finally:
            server.resolve_entry_alignment = original_resolver
            self.restore_server(server, originals)

        self.assertEqual(FakeBrokerClient.orders[0]["quantity"], 2)
        trade = fake_mongo.trades.inserted[0]
        self.assertEqual(trade["entry_alignment_tier"], "agreement")
        self.assertEqual(trade["entry_sizing_percent"], 25.0)
        self.assertEqual(trade["entry_alignment_context"]["market_alignment_percent"], 100.0)
        self.assertEqual(trade["entry_alignment_context"]["risk_language_cap_percent"], 25.0)
        self.assertIn("high risk", trade["entry_alignment_context"]["risk_language_reasons"])

    def test_buy_submits_order_when_runtime_is_not_armed(self):
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

        self.assertEqual(len(FakeBrokerClient.orders), 1)
        self.assertEqual(fake_mongo.trades.inserted[0]["status"], "pending")
        self.assertFalse(fake_mongo.trades.inserted[0]["simulated"])
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-unarmed"},
                    {"$set": {"processed": True, "trade_executed": False}},
                )
            ],
        )

    def test_buy_submits_order_when_sentinel_echo_role_is_not_executioner(self):
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

        self.assertEqual(len(FakeBrokerClient.orders), 1)
        self.assertEqual(fake_mongo.trades.inserted[0]["status"], "pending")
        self.assertFalse(fake_mongo.trades.inserted[0]["simulated"])
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-role-blocked"},
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

        self.assertTrue(processed)
        self.assertEqual(fake_db.inserted_trades[0]["status"], "pending")
        self.assertEqual(fake_db.inserted_trades[0]["order_id"], "live-order-1")
        self.assertEqual(fake_db.inserted_trades[0]["position_id"], "pos-live")

    def test_exit_alert_without_matching_position_closes_reconciliation_client(self):
        from models import Alert, Settings
        import order_execution
        import server

        fake_db = FakeRuntimeDb()
        broker = ClosableNoPositionsBrokerClient()
        originals = self.patch_server(server, fake_db=fake_db)
        order_execution.get_configured_broker_client = lambda *args, **kwargs: broker
        try:
            processed = asyncio.run(
                server.process_exit_alert(
                    Alert(
                        id="alert-sell-no-position",
                        ticker="SPY",
                        strike=765.0,
                        option_type="CALL",
                        expiration="",
                        entry_price=0.52,
                        alert_type="sell",
                        sell_percentage=90.0,
                    ),
                    {
                        "alert_type": "sell",
                        "ticker": "SPY",
                        "strike": 765.0,
                        "option_type": "CALL",
                        "expiration": None,
                        "entry_price": 0.52,
                        "sell_percentage": 90.0,
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
        self.assertTrue(broker.closed)

    def test_exit_alert_uses_fresh_option_bid_instead_of_analyst_fill(self):
        from models import Alert, Settings
        import order_execution
        import server

        fake_db = FakeRuntimeDb()
        fake_db.positions_by_status["open"] = [
            {
                "id": "pos-fresh-exit-quote",
                "ticker": "TSLA",
                "strike": 400.0,
                "option_type": "CALL",
                "expiration": "09/04/26",
                "entry_price": 0.93,
                "current_price": 0.80,
                "original_quantity": 5,
                "remaining_quantity": 3,
                "total_cost": 465.0,
                "broker": "alpaca",
                "status": "partial",
                "realized_pnl": 50.0,
                "simulated": False,
                "trade_ids": ["entry-trade", "stage-one-trade"],
            }
        ]
        originals = self.patch_server(server, fake_db=fake_db)
        order_execution.get_configured_broker_client = lambda *args, **kwargs: FreshQuoteBrokerClient()
        try:
            processed = asyncio.run(
                server.process_exit_alert(
                    Alert(
                        id="alert-tsla-sold",
                        ticker="TSLA",
                        strike=400.0,
                        option_type="CALL",
                        expiration="",
                        entry_price=1.22,
                        alert_type="sell",
                        sell_percentage=25.0,
                    ),
                    {
                        "alert_type": "sell",
                        "ticker": "TSLA",
                        "strike": 400.0,
                        "option_type": "CALL",
                        "expiration": None,
                        "entry_price": 1.22,
                        "sell_percentage": 25.0,
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

        self.assertTrue(processed)
        self.assertEqual(FreshQuoteBrokerClient.orders[0]["price"], 0.91)
        self.assertEqual(fake_db.inserted_trades[0]["exit_price"], 0.91)

    def test_exit_alert_uses_fresh_bid_when_alert_and_position_have_no_price(self):
        from models import Alert, Settings
        import order_execution
        import server

        fake_db = FakeRuntimeDb()
        fake_db.positions_by_status["open"] = [
            {
                "id": "pos-no-local-exit-quote",
                "ticker": "SPY",
                "strike": 773.0,
                "option_type": "CALL",
                "expiration": "2026-09-03",
                "entry_price": 0.174,
                "current_price": None,
                "original_quantity": 3,
                "remaining_quantity": 3,
                "total_cost": 52.2,
                "broker": "alpaca",
                "status": "open",
                "realized_pnl": 0.0,
                "simulated": False,
                "trade_ids": ["entry-trade"],
            }
        ]
        originals = self.patch_server(server, fake_db=fake_db)
        order_execution.get_configured_broker_client = lambda *args, **kwargs: FreshQuoteBrokerClient()
        try:
            processed = asyncio.run(
                server.process_exit_alert(
                    Alert(
                        id="alert-sold-majority",
                        ticker="SPY",
                        strike=773.0,
                        option_type="CALL",
                        expiration="2026-09-03",
                        entry_price=0.01,
                        alert_type="sell",
                        sell_percentage=75.0,
                    ),
                    {
                        "alert_type": "sell",
                        "ticker": "SPY",
                        "strike": 773.0,
                        "option_type": "CALL",
                        "expiration": "2026-09-03",
                        "entry_price": None,
                        "sell_percentage": 75.0,
                        "market_price": True,
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

        self.assertTrue(processed)
        self.assertEqual(FreshQuoteBrokerClient.orders[0]["quantity"], 2)
        self.assertEqual(FreshQuoteBrokerClient.orders[0]["price"], 0.91)

    def test_exit_submits_order_when_sentinel_echo_role_is_not_executioner(self):
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

        self.assertTrue(processed)
        self.assertEqual(len(FakeBrokerClient.orders), 1)
        self.assertEqual(fake_db.inserted_trades[0]["status"], "pending")
        self.assertFalse(fake_db.inserted_trades[0]["simulated"])

    def test_exit_alert_does_not_submit_sell_when_broker_position_reconciliation_fails(self):
        from models import Alert, Settings
        import order_execution
        import server

        fake_db = FakeRuntimeDb()
        fake_db.positions_by_status["open"] = [
            {
                "id": "pos-stale-risk",
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
                "broker_mark_refreshed_at": "2026-08-31T13:57:43+00:00",
            }
        ]
        originals = self.patch_server(server, fake_db=fake_db)
        order_execution.get_configured_broker_client = lambda *args, **kwargs: FailingPositionLookupBrokerClient()
        try:
            processed = asyncio.run(
                server.process_exit_alert(
                    Alert(
                        id="alert-sell-reconcile-failed",
                        ticker="SPY",
                        strike=500.0,
                        option_type="CALL",
                        expiration="6/21",
                        entry_price=1.50,
                        alert_type="sell",
                        sell_percentage=100.0,
                    ),
                    {
                        "alert_type": "sell",
                        "ticker": "SPY",
                        "strike": 500.0,
                        "option_type": "CALL",
                        "expiration": "6/21",
                        "entry_price": 1.50,
                        "sell_percentage": 100.0,
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
        self.assertEqual(FailingPositionLookupBrokerClient.orders, [])
        self.assertEqual(fake_db.inserted_trades, [])

    def test_live_buy_premium_buffer_caps_fill_price_above_alert_price(self):
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

        self.assertEqual(FakeBrokerClient.orders[0]["price"], 5.10)

    def test_legacy_simulation_setting_submits_pending_buy_without_local_position(self):
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

        self.assertEqual(len(FakeBrokerClient.orders), 1)
        self.assertEqual(FakeBrokerClient.orders[0]["side"], "BUY")
        self.assertEqual(fake_mongo.trades.inserted[0]["status"], "pending")
        self.assertFalse(fake_mongo.trades.inserted[0]["simulated"])
        self.assertEqual(fake_mongo.positions.inserted, [])

    def test_legacy_simulated_average_down_submits_pending_broker_order(self):
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
        self.assertEqual(trade["status"], "pending")
        self.assertFalse(trade["simulated"])
        self.assertEqual(fake_db.updated_positions, [])
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-avg-down"},
                    {"$set": {"processed": True, "trade_executed": False}},
                )
            ],
        )

    def test_average_down_without_matching_position_opens_starter_buy(self):
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "simulation_mode": False,
            "default_quantity": 1,
            "max_position_size": 1000.0,
            "averaging_down_enabled": True,
            "averaging_down_threshold": 10.0,
            "averaging_down_percentage": 50.0,
            "averaging_down_max_buys": 2,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-avg-starter",
                        ticker="QQQ",
                        strike=716.0,
                        option_type="CALL",
                        expiration="8/26",
                        entry_price=0.65,
                        alert_type="average_down",
                    ),
                    {
                        "alert_type": "average_down",
                        "ticker": "QQQ",
                        "strike": 716.0,
                        "option_type": "CALL",
                        "expiration": "8/26",
                        "entry_price": 0.65,
                    },
                )
            )
        finally:
            self.restore_server(server, originals)

        self.assertEqual(len(FakeBrokerClient.orders), 1)
        order = FakeBrokerClient.orders[0]
        self.assertEqual(order["side"], "BUY")
        self.assertEqual(order["ticker"], "QQQ")
        self.assertEqual(order["strike"], 716.0)
        self.assertEqual(order["option_type"], "CALL")
        self.assertEqual(order["expiration"], "8/26")
        self.assertEqual(order["quantity"], 1)
        self.assertEqual(order["price"], 0.65)
        self.assertIn("buy", order["client_order_id"])

        self.assertEqual(len(fake_mongo.trades.inserted), 1)
        trade = fake_mongo.trades.inserted[0]
        self.assertEqual(trade["side"], "BUY")
        self.assertEqual(trade["quantity"], 1)
        self.assertEqual(trade["status"], "pending")
        self.assertEqual(trade["order_id"], "live-order-1")
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-avg-starter"},
                    {
                        "$set": {
                            "processed": True,
                            "trade_executed": False,
                            "trade_result": "pending: average_down fallback opened starter buy",
                        }
                    },
                )
            ],
        )

    def test_average_down_fallback_does_not_reopen_contract_closed_this_session(self):
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "simulation_mode": False,
            "default_quantity": 4,
            "max_position_size": 1000.0,
            "averaging_down_enabled": True,
            "averaging_down_threshold": 10.0,
            "averaging_down_percentage": 50.0,
            "averaging_down_max_buys": 2,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        fake_db.positions_by_status["closed"] = [
            {
                "id": "position-closed",
                "status": "closed",
                "ticker": "TSLA",
                "strike": 385.0,
                "option_type": "CALL",
                "expiration": "2026-09-09",
                "remaining_quantity": 0,
                "closed_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-recycled-dca",
                        ticker="TSLA",
                        strike=385.0,
                        option_type="CALL",
                        expiration="09/09/26",
                        entry_price=0.60,
                        alert_type="average_down",
                        raw_message=(
                            "$TSLA $385 CALLS EXPIRATION 9/9/2026 $.6 Entry "
                            "DCA & buy on backtests"
                        ),
                    ),
                    {
                        "alert_type": "average_down",
                        "ticker": "TSLA",
                        "strike": 385.0,
                        "option_type": "CALL",
                        "expiration": "09/09/26",
                        "entry_price": 0.60,
                    },
                )
            )
        finally:
            self.restore_server(server, originals)

        self.assertEqual(FakeBrokerClient.orders, [])
        self.assertEqual(fake_mongo.trades.inserted, [])
        self.assertEqual(
            fake_mongo.alerts.updated[-1][1]["$set"]["trade_result"],
            "blocked: contract already closed this session for TSLA 385.0 CALL 2026-09-09",
        )

    def test_explicit_readding_after_close_is_recorded_as_fresh_reentry(self):
        from models import Alert
        import server

        settings = {
            "id": "main_settings",
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"broker_type": "alpaca"}},
            "simulation_mode": False,
            "default_quantity": 4,
            "max_position_size": 1000.0,
            "averaging_down_enabled": True,
            "averaging_down_threshold": 10.0,
            "averaging_down_percentage": 50.0,
            "averaging_down_max_buys": 2,
        }
        fake_mongo = FakeSyncMongo(settings)
        fake_db = FakeRuntimeDb()
        fake_db.positions_by_status["closed"] = [
            {
                "id": "position-closed",
                "status": "closed",
                "ticker": "SPY",
                "strike": 768.0,
                "option_type": "CALL",
                "expiration": "2026-09-11",
                "remaining_quantity": 0,
                "closed_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        raw_message = (
            "$SPY $768 CALLS EXPIRATION 9/11/2026 $.5 Entry\n"
            "RE-ADDING SPY $768 CALLS $.35 FILL "
            "(looking for a $.28-$.3 final AVG)"
        )
        originals = self.patch_server(server, fake_sync_mongo=fake_mongo, fake_db=fake_db)
        try:
            asyncio.run(
                server.process_trade(
                    Alert(
                        id="alert-explicit-reentry",
                        ticker="SPY",
                        strike=768.0,
                        option_type="CALL",
                        expiration="09/11/26",
                        entry_price=0.35,
                        alert_type="average_down",
                        raw_message=raw_message,
                    ),
                    {
                        "alert_type": "average_down",
                        "ticker": "SPY",
                        "strike": 768.0,
                        "option_type": "CALL",
                        "expiration": "09/11/26",
                        "entry_price": 0.35,
                    },
                )
            )
        finally:
            self.restore_server(server, originals)

        self.assertEqual(len(FakeBrokerClient.orders), 1)
        self.assertEqual(FakeBrokerClient.orders[0]["price"], 0.35)
        self.assertIn("buy", FakeBrokerClient.orders[0]["client_order_id"])
        self.assertEqual(
            fake_mongo.alerts.updated[-1][1]["$set"],
            {
                "processed": True,
                "trade_executed": False,
                "alert_type": "buy",
                "trade_result": "pending: explicit re-entry opened fresh buy",
            },
        )

    def test_legacy_paper_shadow_source_submits_normal_broker_order(self):
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

        self.assertEqual(len(FakeBrokerClient.orders), 1)
        self.assertEqual(FakeBrokerClient.orders[0]["side"], "BUY")
        self.assertEqual(fake_mongo.trades.inserted[0]["status"], "pending")
        self.assertFalse(fake_mongo.trades.inserted[0]["simulated"])
        self.assertEqual(fake_mongo.positions.inserted, [])

    def test_unarmed_buy_with_legacy_paper_shadow_source_submits_normal_broker_order(self):
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

        self.assertEqual(len(FakeBrokerClient.orders), 1)
        self.assertEqual(fake_mongo.trades.inserted[0]["status"], "pending")
        self.assertFalse(fake_mongo.trades.inserted[0]["simulated"])
        self.assertEqual(fake_mongo.positions.inserted, [])
        self.assertEqual(
            fake_mongo.alerts.updated,
            [
                (
                    {"id": "alert-shadow-unarmed"},
                    {"$set": {"processed": True, "trade_executed": False}},
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
