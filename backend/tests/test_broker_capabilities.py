import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class BrokerCapabilityTests(unittest.TestCase):
    def test_known_broker_capabilities_expose_order_status_and_cancel_support(self):
        from broker_capabilities import get_broker_capabilities

        alpaca = get_broker_capabilities("alpaca")

        self.assertTrue(alpaca["supports_options"])
        self.assertTrue(alpaca["supports_order_status"])
        self.assertTrue(alpaca["supports_cancel_order"])
        self.assertEqual(alpaca["auth_mode"], "api_key")

    def test_unknown_broker_capabilities_are_safe(self):
        from broker_capabilities import get_broker_capabilities

        unknown = get_broker_capabilities("unknown")

        self.assertFalse(unknown["supports_live_trading"])
        self.assertFalse(unknown["supports_order_status"])
        self.assertFalse(unknown["supports_cancel_order"])


if __name__ == "__main__":
    unittest.main()
