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
        self.settings_updates = []
        self.runtime_updates = []
        self.runtime_state = {}

    async def get_trades(self, limit=50):
        return [dict(self.trade)]

    async def get_alerts(self, limit=50):
        return list(reversed(self.inserted_alerts))[:limit]

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

    async def update_settings(self, update):
        self.settings_updates.append(update)
        return dict(update)

    async def update_runtime_state(self, update):
        self.runtime_updates.append(update)
        self.runtime_state.update(update)
        return dict(update)

    async def get_runtime_state(self):
        return dict(self.runtime_state)

    async def get_settings(self):
        return {
            "active_broker": "ibkr",
            "simulation_mode": True,
            "auto_shutdown_enabled": False,
        }


class FakeRawTradingDb(FakeTradingDb):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    async def get_settings(self):
        return self.settings


class FakeBrokerDb:
    async def get_settings(self):
        return {
            "active_broker": "alpaca",
            "broker_configs": {"alpaca": {"api_key": "key", "api_secret": "secret"}},
        }


class FakeRawBrokerDb:
    def __init__(self, settings):
        self.settings = settings
        self.updated = []
        self.events = []

    async def get_settings(self):
        return self.settings

    async def update_settings(self, update):
        self.updated.append(update)
        return dict(update)

    async def insert_operator_event(self, event):
        self.events.append(event)
        return event["id"]


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
        self.assertIn(("GET", "/api/operator/alert-chains"), routes)

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

    def test_operator_alert_chains_returns_deterministic_report(self):
        from routes import operator as operator_route

        fake_db = FakeTradingDb()
        fake_db.inserted_alerts.append(
            {
                "id": "alert-1",
                "ticker": "SPY",
                "alert_type": "buy",
                "trade_executed": True,
                "processed": True,
                "simulated": False,
            }
        )
        fake_db.trade.update({"id": "trade-1", "alert_id": "alert-1", "status": "executed", "simulated": False})
        fake_db.position.update({"id": "pos-1", "trade_ids": ["trade-1"], "simulated": False})
        fake_db.inserted_events.append(
            {
                "id": "event-1",
                "timestamp": "2026-06-22T14:30:00Z",
                "action": "bridge_alert_decision",
                "details": {
                    "event_id": "bridge-1",
                    "parsed": {"ticker": "SPY"},
                    "decision": {
                        "status": "accepted",
                        "alert_inserted": True,
                        "alert_id": "alert-1",
                        "trade_requested": True,
                        "trade_request_reason": "auto trading enabled",
                    },
                },
            }
        )
        operator_route.set_db(fake_db)

        response = asyncio.run(operator_route.get_alert_chains(limit=50))

        self.assertTrue(response["summary"]["deterministic"])
        self.assertEqual(response["summary"]["total"], 1)
        self.assertEqual(response["rows"][0]["alert_id"], "alert-1")
        self.assertEqual(response["rows"][0]["trade_id"], "trade-1")
        self.assertEqual(response["rows"][0]["position_id"], "pos-1")

    def test_operator_live_readiness_payload_injects_alert_chain_attention(self):
        from routes import operator as operator_route

        fake_db = FakeTradingDb()
        fake_db.inserted_events.append(
            {
                "id": "event-1",
                "timestamp": "2026-06-22T14:30:00Z",
                "action": "bridge_alert_decision",
                "details": {
                    "event_id": "bridge-1",
                    "parsed": {"ticker": "SPY"},
                    "decision": {
                        "status": "accepted",
                        "alert_inserted": True,
                        "alert_id": "",
                        "trade_requested": True,
                        "trade_request_reason": "auto trading enabled",
                    },
                },
            }
        )
        operator_route.set_db(fake_db)

        response = asyncio.run(operator_route._live_readiness_payload())

        self.assertIn("alert_chain_attention", response["blocking_codes"])
        self.assertEqual(response["checks"]["alert_chains"]["attention_count"], 1)

    def test_operator_live_readiness_payload_injects_cached_replay_acceptance(self):
        from routes import operator as operator_route

        fake_db = FakeTradingDb()
        fake_db.runtime_state.update(
            {
                "simulation_replay_acceptance_status": "failed",
                "simulation_replay_acceptance_failed_count": 1,
                "simulation_replay_acceptance_expected_count": 3,
            }
        )
        operator_route.set_db(fake_db)

        response = asyncio.run(operator_route._live_readiness_payload())

        self.assertIn("simulation_replay_acceptance_failed", response["blocking_codes"])
        self.assertEqual(response["checks"]["simulation_replay"]["acceptance_status"], "failed")
        self.assertEqual(response["checks"]["simulation_replay"]["failed_count"], 1)

    def test_operator_live_arm_block_audit_normalizes_malformed_blocking_issues(self):
        from fastapi import HTTPException
        from routes import operator as operator_route

        fake_db = FakeTradingDb()
        operator_route.set_db(fake_db)

        async def malformed_readiness():
            return {"ready_for_live": False, "blocking_issues": "blocked"}

        original_readiness = operator_route._live_readiness_payload
        operator_route._live_readiness_payload = malformed_readiness
        try:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    operator_route.live_arm(
                        operator_route.LiveArmRequest(confirmation="ARM LIVE TRADING")
                    )
                )
        finally:
            operator_route._live_readiness_payload = original_readiness

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(fake_db.inserted_events[-1]["details"]["blocking_issues"], [])

    def test_operator_live_arm_treats_malformed_readiness_payload_as_blocked(self):
        from fastapi import HTTPException
        from routes import operator as operator_route

        fake_db = FakeTradingDb()
        operator_route.set_db(fake_db)

        async def malformed_readiness():
            return "readiness"

        original_readiness = operator_route._live_readiness_payload
        operator_route._live_readiness_payload = malformed_readiness
        try:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    operator_route.live_arm(
                        operator_route.LiveArmRequest(confirmation="ARM LIVE TRADING")
                    )
                )
        finally:
            operator_route._live_readiness_payload = original_readiness

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(fake_db.inserted_events[-1]["action"], "live_trading_arm_blocked")
        self.assertEqual(fake_db.inserted_events[-1]["details"]["blocking_issues"], [])

    def test_operator_live_arm_blocks_serialized_false_readiness(self):
        from fastapi import HTTPException
        from routes import operator as operator_route

        fake_db = FakeTradingDb()
        operator_route.set_db(fake_db)

        async def serialized_false_readiness():
            return {"ready_for_live": "false", "blocking_issues": []}

        original_readiness = operator_route._live_readiness_payload
        operator_route._live_readiness_payload = serialized_false_readiness
        try:
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(
                    operator_route.live_arm(
                        operator_route.LiveArmRequest(confirmation="ARM LIVE TRADING")
                    )
                )
        finally:
            operator_route._live_readiness_payload = original_readiness

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(fake_db.runtime_updates, [])
        self.assertEqual(fake_db.inserted_events[-1]["action"], "live_trading_arm_blocked")

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

    def test_active_broker_defaults_when_settings_are_malformed(self):
        from routes import brokers as brokers_route

        brokers_route.set_db(FakeRawBrokerDb("settings"))

        response = asyncio.run(brokers_route.get_active_broker())

        self.assertEqual(response, {"active_broker": "ibkr"})

    def test_active_broker_normalizes_enum_value(self):
        from models import BrokerType
        from routes import brokers as brokers_route

        brokers_route.set_db(FakeRawBrokerDb({"active_broker": BrokerType.ALPACA}))

        response = asyncio.run(brokers_route.get_active_broker())

        self.assertEqual(response, {"active_broker": "alpaca"})

    def test_active_broker_defaults_when_active_broker_value_is_malformed(self):
        from routes import brokers as brokers_route

        brokers_route.set_db(FakeRawBrokerDb({"active_broker": {"id": "alpaca"}}))

        response = asyncio.run(brokers_route.get_active_broker())

        self.assertEqual(response, {"active_broker": "ibkr"})

    def test_switch_broker_blocks_malformed_settings(self):
        from fastapi import HTTPException
        from routes import brokers as brokers_route

        fake_db = FakeRawBrokerDb("settings")
        brokers_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(brokers_route.set_active_broker("alpaca"))

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("has no saved configuration", raised.exception.detail)
        self.assertEqual(fake_db.updated, [])
        self.assertEqual(fake_db.events, [])

    def test_switch_broker_blocks_malformed_broker_configs_container(self):
        from fastapi import HTTPException
        from routes import brokers as brokers_route

        fake_db = FakeRawBrokerDb({"broker_configs": "alpaca"})
        brokers_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(brokers_route.set_active_broker("alpaca"))

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("has no saved configuration", raised.exception.detail)
        self.assertEqual(fake_db.updated, [])
        self.assertEqual(fake_db.events, [])

    def test_switch_broker_blocks_malformed_broker_config_entry(self):
        from fastapi import HTTPException
        from routes import brokers as brokers_route

        fake_db = FakeRawBrokerDb({"broker_configs": {"alpaca": "configured"}})
        brokers_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(brokers_route.set_active_broker("alpaca"))

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("has no saved configuration", raised.exception.detail)
        self.assertEqual(fake_db.updated, [])
        self.assertEqual(fake_db.events, [])

    def test_switch_broker_blocks_empty_broker_config_entry(self):
        from fastapi import HTTPException
        from routes import brokers as brokers_route

        fake_db = FakeRawBrokerDb({"broker_configs": {"alpaca": {}}})
        brokers_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(brokers_route.set_active_broker("alpaca"))

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("has no saved configuration", raised.exception.detail)
        self.assertEqual(fake_db.updated, [])
        self.assertEqual(fake_db.events, [])

    def test_switch_broker_blocks_incomplete_broker_config_entry(self):
        from fastapi import HTTPException
        from routes import brokers as brokers_route

        fake_db = FakeRawBrokerDb({"broker_configs": {"alpaca": {"api_key": "stored-api-key-value"}}})
        brokers_route.set_db(fake_db)

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(brokers_route.set_active_broker("alpaca"))

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("missing required fields", raised.exception.detail)
        self.assertIn("api_secret", raised.exception.detail)
        self.assertNotIn("stored-api-key-value", raised.exception.detail)
        self.assertEqual(fake_db.updated, [])
        self.assertEqual(fake_db.events, [])

    def test_broker_check_reports_no_config_when_settings_are_malformed(self):
        from unittest.mock import patch
        from routes import brokers as brokers_route

        brokers_route.set_db(FakeRawBrokerDb("settings"))

        with patch("order_execution.get_configured_broker_client") as get_client:
            response = asyncio.run(brokers_route.check_broker_alias("alpaca"))

        self.assertFalse(response["connected"])
        self.assertEqual(response["broker"], "alpaca")
        self.assertIn("has no saved configuration", response["message"])
        get_client.assert_not_called()

    def test_broker_check_reports_no_config_for_malformed_broker_configs_container(self):
        from unittest.mock import patch
        from routes import brokers as brokers_route

        brokers_route.set_db(FakeRawBrokerDb({"broker_configs": "alpaca"}))

        with patch("order_execution.get_configured_broker_client") as get_client:
            response = asyncio.run(brokers_route.check_broker_alias("alpaca"))

        self.assertFalse(response["connected"])
        self.assertEqual(response["broker"], "alpaca")
        self.assertIn("has no saved configuration", response["message"])
        get_client.assert_not_called()

    def test_broker_check_reports_no_config_for_malformed_broker_config_entry(self):
        from unittest.mock import patch
        from routes import brokers as brokers_route

        brokers_route.set_db(FakeRawBrokerDb({"broker_configs": {"alpaca": "configured"}}))

        with patch("order_execution.get_configured_broker_client") as get_client:
            response = asyncio.run(brokers_route.check_broker_alias("alpaca"))

        self.assertFalse(response["connected"])
        self.assertEqual(response["broker"], "alpaca")
        self.assertIn("has no saved configuration", response["message"])
        get_client.assert_not_called()

    def test_broker_check_reports_no_config_for_blank_broker_config_entry(self):
        from unittest.mock import patch
        from routes import brokers as brokers_route

        brokers_route.set_db(
            FakeRawBrokerDb({"broker_configs": {"alpaca": {"api_key": " ", "api_secret": ""}}})
        )

        with patch("order_execution.get_configured_broker_client") as get_client:
            response = asyncio.run(brokers_route.check_broker_alias("alpaca"))

        self.assertFalse(response["connected"])
        self.assertEqual(response["broker"], "alpaca")
        self.assertIn("has no saved configuration", response["message"])
        get_client.assert_not_called()

    def test_broker_check_reports_no_config_for_incomplete_broker_config_entry(self):
        from unittest.mock import patch
        from routes import brokers as brokers_route

        brokers_route.set_db(
            FakeRawBrokerDb({"broker_configs": {"alpaca": {"api_key": "stored-api-key-value"}}})
        )

        with patch("order_execution.get_configured_broker_client") as get_client:
            response = asyncio.run(brokers_route.check_broker_alias("alpaca"))

        self.assertFalse(response["connected"])
        self.assertEqual(response["broker"], "alpaca")
        self.assertIn("missing required fields", response["message"])
        self.assertEqual(response["missing_required_fields"], ["api_secret"])
        self.assertNotIn("stored-api-key-value", str(response))
        get_client.assert_not_called()

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

    def test_position_sell_defaults_to_simulated_when_settings_are_malformed(self):
        from routes import settings as settings_route
        from routes import trading as trading_route

        fake_db = FakeRawTradingDb("settings")
        trading_route.set_db(fake_db)
        settings_route.set_db(fake_db)

        response = asyncio.run(
            trading_route.sell_position_from_operator(
                "pos-1",
                sell_percentage=50,
                exit_price=3.0,
            )
        )

        self.assertEqual(response["sold_quantity"], 2)
        self.assertEqual(fake_db.inserted_trades[0]["broker"], "ibkr")
        self.assertEqual(fake_db.inserted_trades[0]["status"], "simulated")
        self.assertTrue(fake_db.inserted_trades[0]["simulated"])
        self.assertEqual(fake_db.runtime_updates[-1]["shutdown_reason"], "Settings are malformed")

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

    def test_test_alert_endpoint_defaults_to_simulated_when_settings_are_malformed(self):
        from routes import trading as trading_route

        fake_db = FakeRawTradingDb("settings")
        trading_route.set_db(fake_db)

        response = asyncio.run(trading_route.create_test_alert())

        self.assertEqual(response["message"], "Test alert created")
        self.assertEqual(fake_db.inserted_trades[0]["broker"], "ibkr")
        self.assertTrue(fake_db.inserted_trades[0]["simulated"])
        self.assertEqual(fake_db.inserted_trades[0]["status"], "simulated")
        self.assertTrue(fake_db.inserted_positions[0]["simulated"])


if __name__ == "__main__":
    unittest.main()
