import pathlib
import sys
import unittest
from datetime import date


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

    def test_duplicate_detection_can_use_shared_sqlite_store(self):
        import tempfile
        import risk

        alert = {
            "alert_type": "entry",
            "ticker": "SPY",
            "strike": 500.0,
            "option_type": "CALL",
            "expiration": "6/21",
            "entry_price": 1.25,
        }

        with tempfile.TemporaryDirectory() as tmp:
            db_path = f"{tmp}/duplicates.sqlite3"
            first_worker_store = risk.SQLiteDuplicateAlertStore(db_path)
            second_worker_store = risk.SQLiteDuplicateAlertStore(db_path)

            self.assertFalse(risk.is_duplicate_alert(alert, store=first_worker_store))
            self.assertTrue(risk.is_duplicate_alert(alert, store=second_worker_store))

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


class FakePositionDb:
    def __init__(self, positions):
        self.positions = positions

    async def get_positions(self, status):
        self.status = status
        return self.positions


class CorrelationRiskTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_mode_ignores_simulated_positions_for_ticker_limit(self):
        from risk import check_correlation

        allowed, reason = await check_correlation(
            "SPY",
            FakePositionDb(
                [
                    {
                        "ticker": "SPY",
                        "status": "open",
                        "simulated": True,
                    }
                ]
            ),
            {"max_positions_per_ticker": 1, "simulation_mode": False},
        )

        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    async def test_simulation_mode_counts_simulated_positions_for_ticker_limit(self):
        from risk import check_correlation

        allowed, reason = await check_correlation(
            "SPY",
            FakePositionDb(
                [
                    {
                        "ticker": "SPY",
                        "status": "open",
                        "simulated": True,
                    }
                ]
            ),
            {"max_positions_per_ticker": 1, "simulation_mode": True},
        )

        self.assertFalse(allowed)
        self.assertIn("Correlation limit", reason)

    async def test_correlation_ignores_expired_option_positions(self):
        from risk import check_correlation

        allowed, reason = await check_correlation(
            "SPY",
            FakePositionDb(
                [
                    {
                        "ticker": "SPY",
                        "status": "open",
                        "simulated": False,
                        "expiration": "6/26/2026",
                    }
                ]
            ),
            {"max_positions_per_ticker": 1, "simulation_mode": False},
            today=date(2026, 7, 1),
        )

        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    async def test_correlation_counts_same_day_expiration_positions(self):
        from risk import check_correlation

        allowed, reason = await check_correlation(
            "SPY",
            FakePositionDb(
                [
                    {
                        "ticker": "SPY",
                        "status": "open",
                        "simulated": False,
                        "expiration": "7/1/2026",
                    }
                ]
            ),
            {"max_positions_per_ticker": 1, "simulation_mode": False},
            today=date(2026, 7, 1),
        )

        self.assertFalse(allowed)
        self.assertIn("Correlation limit", reason)


if __name__ == "__main__":
    unittest.main()
