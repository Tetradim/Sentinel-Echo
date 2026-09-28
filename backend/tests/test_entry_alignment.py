import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def _bars(closes, *, volumes=None):
    volumes = volumes or [100] * len(closes)
    return [
        {
            "o": close - 0.05,
            "h": close + 0.10,
            "l": close - 0.10,
            "c": close,
            "v": volume,
            "t": f"2026-09-01T14:{index:02d}:00Z",
        }
        for index, (close, volume) in enumerate(zip(closes, volumes))
    ]


class EntryAlignmentScoringTests(unittest.TestCase):
    def test_settings_enable_default_sizing_tiers(self):
        from models import Settings

        settings = Settings()

        self.assertTrue(settings.smart_sizing_enabled)
        self.assertEqual(settings.smart_sizing_agreement_percent, 100.0)
        self.assertEqual(settings.smart_sizing_mixed_percent, 50.0)
        self.assertEqual(settings.smart_sizing_conflict_percent, 25.0)

    def test_settings_update_rejects_percentage_over_one_hundred(self):
        from pydantic import ValidationError
        from models import SettingsUpdate

        with self.assertRaises(ValidationError):
            SettingsUpdate(smart_sizing_conflict_percent=101)

    def test_bullish_context_fully_sizes_call(self):
        from entry_alignment import evaluate_entry_alignment

        decision = evaluate_entry_alignment(
            option_type="CALL",
            bars=_bars([100.00, 100.05, 100.10, 100.18, 100.28, 100.40]),
            option_bid=0.95,
            option_ask=1.05,
        )

        self.assertEqual(decision.tier, "agreement")
        self.assertEqual(decision.multiplier_percent, 100.0)
        self.assertGreaterEqual(decision.alignment_score, 2.0)

    def test_bearish_context_fully_sizes_put(self):
        from entry_alignment import evaluate_entry_alignment

        decision = evaluate_entry_alignment(
            option_type="PUT",
            bars=_bars([100.40, 100.30, 100.22, 100.12, 100.04, 99.90]),
            option_bid=0.95,
            option_ask=1.05,
        )

        self.assertEqual(decision.tier, "agreement")
        self.assertEqual(decision.multiplier_percent, 100.0)
        self.assertGreaterEqual(decision.alignment_score, 2.0)

    def test_bearish_context_reduces_call_to_conflict_tier(self):
        from entry_alignment import evaluate_entry_alignment

        decision = evaluate_entry_alignment(
            option_type="CALL",
            bars=_bars([100.40, 100.30, 100.22, 100.12, 100.04, 99.90]),
            option_bid=0.95,
            option_ask=1.05,
        )

        self.assertEqual(decision.tier, "conflict")
        self.assertEqual(decision.multiplier_percent, 25.0)
        self.assertLessEqual(decision.alignment_score, -2.0)

    def test_missing_context_uses_mixed_tier_instead_of_blocking(self):
        from entry_alignment import evaluate_entry_alignment

        decision = evaluate_entry_alignment(
            option_type="CALL",
            bars=[],
            option_bid=None,
            option_ask=None,
        )

        self.assertEqual(decision.tier, "mixed")
        self.assertEqual(decision.multiplier_percent, 50.0)
        self.assertIn("market context unavailable", decision.reasons)

    def test_wide_option_spread_caps_agreement_at_mixed(self):
        from entry_alignment import evaluate_entry_alignment

        decision = evaluate_entry_alignment(
            option_type="CALL",
            bars=_bars([100.00, 100.05, 100.10, 100.18, 100.28, 100.40]),
            option_bid=0.40,
            option_ask=1.00,
        )

        self.assertEqual(decision.tier, "mixed")
        self.assertEqual(decision.multiplier_percent, 50.0)
        self.assertIn("option spread is too wide for full sizing", decision.reasons)

    def test_quantity_reduction_never_drops_below_one_contract(self):
        from entry_alignment import apply_alignment_quantity

        self.assertEqual(apply_alignment_quantity(10, 25.0), 2)
        self.assertEqual(apply_alignment_quantity(5, 50.0), 2)
        self.assertEqual(apply_alignment_quantity(2, 25.0), 1)
        self.assertEqual(apply_alignment_quantity(1, 25.0), 1)

    def test_configured_tier_percentages_are_used(self):
        from entry_alignment import evaluate_entry_alignment

        decision = evaluate_entry_alignment(
            option_type="CALL",
            bars=_bars([100.40, 100.30, 100.22, 100.12, 100.04, 99.90]),
            option_bid=0.95,
            option_ask=1.05,
            agreement_percent=90,
            mixed_percent=40,
            conflict_percent=15,
        )

        self.assertEqual(decision.tier, "conflict")
        self.assertEqual(decision.multiplier_percent, 15.0)

    def test_entry_slippage_reduces_size_without_blocking(self):
        from entry_alignment import entry_slippage_size_cap

        self.assertEqual(entry_slippage_size_cap(0.29, 0.31), (None, 6.897))
        self.assertEqual(entry_slippage_size_cap(0.29, 0.34), (50.0, 17.241))
        self.assertEqual(entry_slippage_size_cap(0.29, 0.36), (25.0, 24.138))

    def test_entry_slippage_disabled_mode_keeps_full_size(self):
        from entry_alignment import entry_slippage_size_cap

        self.assertEqual(
            entry_slippage_size_cap(0.29, 0.50, mode="disabled"),
            (None, 72.414),
        )

    def test_entry_slippage_binary_mode_rejects_only_beyond_limit(self):
        from entry_alignment import entry_slippage_size_cap

        self.assertEqual(
            entry_slippage_size_cap(0.29, 0.31, mode="binary", severe_percent=20),
            (None, 6.897),
        )
        self.assertEqual(
            entry_slippage_size_cap(0.29, 0.36, mode="binary", severe_percent=20),
            (0.0, 24.138),
        )

    def test_alignment_decision_keeps_live_option_quote(self):
        from entry_alignment import evaluate_entry_alignment

        decision = evaluate_entry_alignment(
            option_type="CALL",
            bars=_bars([100.00, 100.05, 100.10, 100.18, 100.28, 100.40]),
            option_bid=0.30,
            option_ask=0.34,
        )

        self.assertEqual(decision.option_bid, 0.30)
        self.assertEqual(decision.option_ask, 0.34)


if __name__ == "__main__":
    unittest.main()
