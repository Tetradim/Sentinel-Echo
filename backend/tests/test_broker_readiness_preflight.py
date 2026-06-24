import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class BrokerReadinessPreflightTests(unittest.TestCase):
    def test_preflight_passes_with_auto_trading_enabled_when_simulation_mode_is_on(self):
        from broker_readiness_preflight import run_broker_readiness_preflight

        class FakeClient:
            def __init__(self):
                self.connection_checked = False
                self.open_orders_listed = False
                self.place_order_called = False
                self.closed = False

            async def check_connection(self):
                self.connection_checked = True
                return True

            async def list_open_orders(self):
                self.open_orders_listed = True
                return []

            async def place_order(self, *args, **kwargs):
                self.place_order_called = True

            async def close(self):
                self.closed = True

        fake_client = FakeClient()

        async def client_factory(settings, broker_id):
            self.assertEqual(broker_id, "alpaca")
            return fake_client

        report = asyncio.run(
            run_broker_readiness_preflight(
                {
                    "active_broker": "alpaca",
                    "simulation_mode": True,
                    "auto_trading_enabled": True,
                },
                client_factory=client_factory,
            )
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["checks"]["execution_flags"]["evidence"]["auto_trading_enabled"], True)
        self.assertTrue(fake_client.connection_checked)
        self.assertTrue(fake_client.open_orders_listed)
        self.assertFalse(fake_client.place_order_called)
        self.assertTrue(fake_client.closed)
        self.assertEqual(report["checks"]["open_orders"]["evidence"], {"open_order_count": 0})

    def test_preflight_blocks_when_open_orders_need_reconciliation(self):
        from broker_readiness_preflight import run_broker_readiness_preflight

        class FakeClient:
            async def check_connection(self):
                return True

            async def list_open_orders(self):
                return [{"order_id": "order-1"}, {"order_id": "order-2"}]

            async def close(self):
                return None

        async def client_factory(settings, broker_id):
            return FakeClient()

        report = asyncio.run(
            run_broker_readiness_preflight(
                {
                    "active_broker": "alpaca",
                    "simulation_mode": True,
                    "auto_trading_enabled": False,
                },
                client_factory=client_factory,
            )
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["checks"]["open_orders"]["status"], "blocked")
        self.assertEqual(report["checks"]["open_orders"]["evidence"], {"open_order_count": 2})

    def test_preflight_blocks_when_execution_flags_are_not_safe(self):
        from broker_readiness_preflight import run_broker_readiness_preflight

        async def client_factory(settings, broker_id):
            raise AssertionError("broker client should not be created when execution flags are unsafe")

        report = asyncio.run(
            run_broker_readiness_preflight(
                {
                    "active_broker": "alpaca",
                    "simulation_mode": False,
                    "auto_trading_enabled": True,
                },
                client_factory=client_factory,
            )
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["checks"]["execution_flags"]["status"], "blocked")
        self.assertEqual(
            report["checks"]["execution_flags"]["evidence"],
            {"simulation_mode": False, "auto_trading_enabled": True},
        )


if __name__ == "__main__":
    unittest.main()
