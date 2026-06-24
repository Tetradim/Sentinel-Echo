import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class RiskSizingTests(unittest.TestCase):
    def test_source_risk_multiplier_reduces_contract_quantity(self):
        from risk import calculate_position_size

        quantity = calculate_position_size(
            entry_price=1.00,
            default_quantity=6,
            max_position_size=1000.0,
            risk_multiplier=0.5,
        )

        self.assertEqual(quantity, 3)

    def test_source_risk_multiplier_can_increase_within_max_position_size(self):
        from risk import calculate_position_size

        quantity = calculate_position_size(
            entry_price=1.00,
            default_quantity=2,
            max_position_size=1000.0,
            risk_multiplier=2.0,
        )

        self.assertEqual(quantity, 4)

    def test_source_risk_multiplier_still_respects_max_position_size(self):
        from risk import calculate_position_size

        quantity = calculate_position_size(
            entry_price=2.50,
            default_quantity=4,
            max_position_size=500.0,
            risk_multiplier=3.0,
        )

        self.assertEqual(quantity, 2)

    def test_trade_is_blocked_when_one_contract_exceeds_max_position_size(self):
        from risk import calculate_position_size

        quantity = calculate_position_size(
            entry_price=15.00,
            default_quantity=5,
            max_position_size=1000.0,
            risk_multiplier=1.0,
        )

        self.assertEqual(quantity, 0)

    def test_trade_is_blocked_when_entry_price_is_not_positive(self):
        from risk import calculate_position_size

        for entry_price in (0.0, -1.25):
            with self.subTest(entry_price=entry_price):
                quantity = calculate_position_size(
                    entry_price=entry_price,
                    default_quantity=5,
                    max_position_size=1000.0,
                    risk_multiplier=1.0,
                )

                self.assertEqual(quantity, 0)

    def test_position_sizing_log_is_windows_console_safe(self):
        from risk import calculate_position_size

        with self.assertLogs("risk", level="INFO") as logs:
            calculate_position_size(
                entry_price=1.00,
                default_quantity=2,
                max_position_size=1000.0,
            )

        for line in logs.output:
            line.encode("cp1252")

    def test_average_down_duplicate_detection_includes_contract(self):
        import risk

        risk._seen_fingerprints.clear()
        first = {
            "alert_type": "average_down",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
        }
        second = {
            "alert_type": "average_down",
            "ticker": "SPY",
            "strike": 501.0,
            "option_type": "CALL",
            "expiration": "6/21",
        }

        self.assertFalse(risk.is_duplicate_alert(first))
        self.assertFalse(risk.is_duplicate_alert(second))

    def test_contract_exit_duplicate_detection_includes_contract(self):
        import risk

        risk._seen_fingerprints.clear()
        first = {
            "alert_type": "close",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
        }
        second = {
            "alert_type": "close",
            "ticker": "SPY",
            "strike": 501.0,
            "option_type": "CALL",
            "expiration": "6/21",
        }

        self.assertFalse(risk.is_duplicate_alert(first))
        self.assertFalse(risk.is_duplicate_alert(second))

    def test_exact_duplicate_alert_is_suppressed(self):
        import risk

        risk._seen_fingerprints.clear()
        alert = {
            "alert_type": "average_down",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "entry_price": 0.80,
        }

        self.assertFalse(risk.is_duplicate_alert(alert))
        self.assertTrue(risk.is_duplicate_alert(alert))

    def test_average_down_duplicate_detection_includes_entry_price(self):
        import risk

        risk._seen_fingerprints.clear()
        first = {
            "alert_type": "average_down",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "entry_price": 0.80,
        }
        corrected = dict(first, entry_price=0.75)

        self.assertFalse(risk.is_duplicate_alert(first))
        self.assertFalse(risk.is_duplicate_alert(corrected))

    def test_exit_duplicate_detection_includes_exit_price(self):
        import risk

        risk._seen_fingerprints.clear()
        first = {
            "alert_type": "close",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "entry_price": 0.80,
            "sell_percentage": 100.0,
        }
        corrected = dict(first, entry_price=0.01)

        self.assertFalse(risk.is_duplicate_alert(first))
        self.assertFalse(risk.is_duplicate_alert(corrected))


if __name__ == "__main__":
    unittest.main()
