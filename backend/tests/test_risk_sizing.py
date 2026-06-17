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


if __name__ == "__main__":
    unittest.main()
