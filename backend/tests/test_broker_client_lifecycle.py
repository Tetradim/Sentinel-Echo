import asyncio
import inspect
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class ClosableBroker:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class FilledClosableBroker(ClosableBroker):
    async def get_order_status(self, order_id):
        return {"status": "filled", "filled_qty": 2, "avg_fill_price": 1.25}


class FakeDb:
    def __init__(self):
        self.positions = {}

    async def update_trade(self, trade_id, updates):
        return None

    async def insert_position(self, position):
        self.positions[position["id"]] = dict(position)
        return position["id"]

    async def get_position_by_id(self, position_id):
        return self.positions.get(position_id)

    async def update_position(self, position_id, updates):
        position = dict(self.positions[position_id])
        position.update(updates.get("$set", {}))
        self.positions[position_id] = position


class FailingSession:
    def __init__(self):
        self.closed = False

    def get(self, url, *, headers=None):
        raise TimeoutError("stale pooled connection")

    async def close(self):
        self.closed = True


class SuccessfulPositionResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def json(self):
        return [
            {
                "asset_class": "us_option",
                "symbol": "SPY260902C00765000",
                "qty": "2",
                "avg_entry_price": "1.25",
                "current_price": "1.30",
            }
        ]


class SuccessfulSession:
    closed = False

    def get(self, url, *, headers=None):
        return SuccessfulPositionResponse()


class BrokerClientLifecycleTests(unittest.TestCase):
    def test_isolated_http_fallback_retries_transient_transport_failure(self):
        import broker_clients

        with (
            patch.object(
                broker_clients,
                "_request_json_via_stdlib_sync",
                side_effect=[TimeoutError("temporary TLS timeout"), {"ok": True}],
            ) as request,
            patch.object(broker_clients.asyncio, "sleep", new=AsyncMock()) as sleep,
        ):
            result = asyncio.run(
                broker_clients._request_json_via_stdlib(
                    "https://paper-api.alpaca.markets/v2/positions",
                    headers={"test": "value"},
                )
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(request.call_count, 2)
        sleep.assert_awaited_once()

    def test_alpaca_position_listing_retries_with_fresh_session_after_transport_failure(self):
        from broker_clients import AlpacaClient
        from models import BrokerConfig, BrokerType

        first_session = FailingSession()
        second_session = SuccessfulSession()
        sessions = [first_session, second_session]
        client = AlpacaClient(
            BrokerConfig(
                broker_type=BrokerType.ALPACA,
                api_key="key",
                api_secret="secret",
                base_url="https://paper-api.alpaca.markets",
            )
        )

        async def get_session():
            session = sessions.pop(0)
            client._session = session
            return session

        client._get_session = get_session

        positions = asyncio.run(client.list_positions())

        self.assertTrue(first_session.closed)
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["symbol"], "SPY260902C00765000")
        self.assertEqual(client.last_positions_error, "")

    def test_alpaca_position_listing_survives_two_consecutive_transport_failures(self):
        from broker_clients import AlpacaClient
        from models import BrokerConfig, BrokerType

        first_session = FailingSession()
        second_session = FailingSession()
        sessions = [first_session, second_session, SuccessfulSession()]
        client = AlpacaClient(
            BrokerConfig(
                broker_type=BrokerType.ALPACA,
                api_key="key",
                api_secret="secret",
                base_url="https://paper-api.alpaca.markets",
            )
        )

        async def get_session():
            session = sessions.pop(0)
            client._session = session
            return session

        client._get_session = get_session

        positions = asyncio.run(client.list_positions())

        self.assertTrue(first_session.closed)
        self.assertTrue(second_session.closed)
        self.assertEqual(len(positions), 1)
        self.assertEqual(client.last_positions_error, "")

    def test_alpaca_position_listing_falls_back_after_aiohttp_transport_exhaustion(self):
        import broker_clients
        from broker_clients import AlpacaClient
        from models import BrokerConfig, BrokerType

        sessions = [FailingSession(), FailingSession(), FailingSession()]
        client = AlpacaClient(
            BrokerConfig(
                broker_type=BrokerType.ALPACA,
                api_key="key",
                api_secret="secret",
                base_url="https://paper-api.alpaca.markets",
            )
        )

        async def get_session():
            session = sessions.pop(0)
            client._session = session
            return session

        client._get_session = get_session
        fallback_payload = [
            {
                "asset_class": "us_option",
                "symbol": "SPY260902C00765000",
                "qty": "2",
                "avg_entry_price": "1.25",
                "current_price": "1.30",
            }
        ]

        with patch.object(
            broker_clients,
            "_request_json_via_stdlib",
            new=AsyncMock(return_value=fallback_payload),
        ) as fallback:
            positions = asyncio.run(client.list_positions())

        fallback.assert_awaited_once()
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0]["symbol"], "SPY260902C00765000")
        self.assertEqual(client.last_positions_error, "")

    def test_pre_entry_reconciliation_closes_its_temporary_broker_client(self):
        import server

        broker = ClosableBroker()
        settings = SimpleNamespace(active_broker=SimpleNamespace(value="alpaca"))
        with (
            patch("order_execution.get_configured_broker_client", return_value=broker),
            patch(
                "bot_managed_exits.reconcile_local_positions_against_broker",
                new=AsyncMock(return_value={"checked": 0, "closed": 0}),
            ),
        ):
            asyncio.run(
                server._reconcile_local_positions_before_entry(
                    object(), settings, {"active_broker": "alpaca"}, "test"
                )
            )

        self.assertTrue(broker.closed)

    def test_fill_monitor_closes_a_broker_client_it_owns(self):
        from fill_monitor import monitor_fill
        from fill_reconciliation import OrderContext

        self.assertIn("close_broker_client_when_done", inspect.signature(monitor_fill).parameters)
        broker = FilledClosableBroker()
        context = OrderContext(
            trade_id="trade-owned-client",
            order_id="order-owned-client",
            side="BUY",
            ticker="SPY",
            strike=500.0,
            option_type="CALL",
            expiration="09/01/26",
            requested_quantity=2,
            broker="alpaca",
            alert_id="alert-owned-client",
            alert_price=1.25,
            simulated=False,
        )

        asyncio.run(
            monitor_fill(
                order_context=context,
                broker_client=broker,
                db=FakeDb(),
                settings={},
                poll_interval_secs=0,
                max_polls=1,
                close_broker_client_when_done=True,
            )
        )

        self.assertTrue(broker.closed)


if __name__ == "__main__":
    unittest.main()
