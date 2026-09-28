import pathlib
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def _bars(closes, *, volumes=None):
    volumes = volumes or [100] * len(closes)
    return [
        {
            "o": close - 0.03,
            "c": close,
            "v": volume,
        }
        for close, volume in zip(closes, volumes)
    ]


def _position(**overrides):
    position = {
        "id": "pos-spy-call",
        "ticker": "SPY",
        "strike": 765.0,
        "option_type": "CALL",
        "expiration": "2026-09-01",
        "entry_price": 1.0,
        "current_price": 1.1,
        "highest_price": 1.5,
        "remaining_quantity": 8,
        "status": "open",
        "reversal_conflict_count": 0,
        "premium_mark_history": [1.5, 1.42, 1.36],
    }
    position.update(overrides)
    return position


def _settings(**overrides):
    settings = {
        "reversal_exit_enabled": True,
        "reversal_warning_confirmations": 3,
        "reversal_confirmed_confirmations": 5,
        "reversal_warning_sell_percent": 25.0,
        "reversal_premium_drawdown_percent": 12.0,
        "reversal_reduce_min_return_percent": 5.0,
        "reversal_reduce_min_mfe_percent": 20.0,
        "trailing_stop_enabled": True,
        "trailing_stop_type": "percent",
        "trailing_stop_percent": 15.0,
        "adaptive_trailing_enabled": True,
        "adaptive_trailing_min_percent": 8.0,
        "adaptive_trailing_max_percent": 35.0,
        "zero_dte_liquidation_time": "15:40",
    }
    settings.update(overrides)
    return settings


NOW_ET = datetime(2026, 9, 1, 14, 0, tzinfo=ZoneInfo("America/New_York"))


class MarketExitIntelligenceTests(unittest.TestCase):
    def test_settings_expose_validated_intelligence_defaults(self):
        from models import Settings

        settings = Settings()

        self.assertTrue(settings.reversal_exit_enabled)
        self.assertEqual(settings.reversal_warning_confirmations, 3)
        self.assertEqual(settings.reversal_confirmed_confirmations, 5)
        self.assertEqual(settings.reversal_warning_sell_percent, 25.0)
        self.assertEqual(settings.reversal_premium_drawdown_percent, 12.0)
        self.assertEqual(settings.reversal_reduce_min_return_percent, 5.0)
        self.assertEqual(settings.reversal_reduce_min_mfe_percent, 20.0)
        self.assertTrue(settings.adaptive_trailing_enabled)
        self.assertEqual(settings.adaptive_trailing_min_percent, 8.0)
        self.assertEqual(settings.adaptive_trailing_max_percent, 35.0)
        self.assertTrue(settings.zero_dte_liquidation_enabled)
        self.assertEqual(settings.zero_dte_liquidation_time, "15:40")

    def test_settings_update_rejects_invalid_intelligence_values(self):
        from models import SettingsUpdate
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            SettingsUpdate(reversal_warning_confirmations=0)
        with self.assertRaises(ValidationError):
            SettingsUpdate(adaptive_trailing_max_percent=101)
        with self.assertRaises(ValidationError):
            SettingsUpdate(zero_dte_liquidation_time="25:90")

    def test_third_profitable_call_conflict_creates_one_automatic_reduction(self):
        from market_exit_intelligence import evaluate_market_exit_intelligence

        decision = evaluate_market_exit_intelligence(
            _position(reversal_conflict_count=2),
            _settings(),
            bars=_bars([100.5, 100.4, 100.3, 100.2, 100.1, 100.0]),
            option_bid=1.19,
            option_ask=1.21,
            now=NOW_ET,
        )

        self.assertEqual(decision.reversal_state, "reversal_reduce")
        self.assertTrue(decision.triggered)
        self.assertEqual(decision.exit_trigger, "reversal_reduce")
        self.assertEqual(decision.sell_percent, 25.0)
        self.assertEqual(decision.position_updates["reversal_conflict_count"], 3)

    def test_losing_reversal_observation_does_not_reduce_before_confirmation(self):
        from market_exit_intelligence import evaluate_market_exit_intelligence

        decision = evaluate_market_exit_intelligence(
            _position(
                current_price=0.80,
                highest_price=1.05,
                max_favorable_excursion_percent=5.0,
                reversal_conflict_count=2,
            ),
            _settings(),
            bars=_bars([100.5, 100.4, 100.3, 100.2, 100.1, 100.0]),
            option_bid=0.79,
            option_ask=0.81,
            now=NOW_ET,
        )

        self.assertEqual(decision.reversal_state, "reversal_observed")
        self.assertFalse(decision.triggered)
        self.assertIsNone(decision.exit_trigger)

    def test_warning_does_not_repeat_after_completed_stage(self):
        from market_exit_intelligence import evaluate_market_exit_intelligence

        decision = evaluate_market_exit_intelligence(
            _position(reversal_conflict_count=3, reversal_warning_completed=True),
            _settings(),
            bars=_bars([100.5, 100.4, 100.3, 100.2, 100.1, 100.0]),
            option_bid=1.19,
            option_ask=1.21,
            now=NOW_ET,
        )

        self.assertEqual(decision.reversal_state, "reversal_observed")
        self.assertFalse(decision.triggered)

    def test_fifth_persistent_conflict_confirms_full_exit(self):
        from market_exit_intelligence import evaluate_market_exit_intelligence

        decision = evaluate_market_exit_intelligence(
            _position(reversal_conflict_count=4, reversal_warning_completed=True),
            _settings(),
            bars=_bars([100.5, 100.4, 100.3, 100.2, 100.1, 100.0]),
            option_bid=1.19,
            option_ask=1.21,
            now=NOW_ET,
        )

        self.assertEqual(decision.reversal_state, "reversal_confirmed")
        self.assertTrue(decision.triggered)
        self.assertEqual(decision.exit_trigger, "reversal_confirmed")
        self.assertEqual(decision.sell_percent, 100.0)

    def test_put_direction_inverts_underlying_conflict(self):
        from market_exit_intelligence import evaluate_market_exit_intelligence

        decision = evaluate_market_exit_intelligence(
            _position(option_type="PUT", reversal_conflict_count=2),
            _settings(),
            bars=_bars([100.0, 100.1, 100.2, 100.3, 100.4, 100.5]),
            option_bid=1.19,
            option_ask=1.21,
            now=NOW_ET,
        )

        self.assertEqual(decision.reversal_state, "reversal_reduce")
        self.assertLessEqual(decision.alignment_score, -2.0)

    def test_missing_context_never_creates_a_sell_or_erases_persistence(self):
        from market_exit_intelligence import evaluate_market_exit_intelligence

        decision = evaluate_market_exit_intelligence(
            _position(reversal_conflict_count=3),
            _settings(),
            bars=[],
            option_bid=None,
            option_ask=None,
            now=NOW_ET,
        )

        self.assertFalse(decision.context_available)
        self.assertFalse(decision.triggered)
        self.assertEqual(decision.position_updates["reversal_conflict_count"], 3)

    def test_adaptive_trailing_is_bounded_and_respects_master_switch(self):
        from market_exit_intelligence import evaluate_market_exit_intelligence

        decision = evaluate_market_exit_intelligence(
            _position(premium_mark_history=[1.5, 1.2, 1.45, 1.18]),
            _settings(trailing_stop_percent=34.0),
            bars=_bars([100.0, 100.1, 100.2, 100.3, 100.4, 100.5]),
            option_bid=1.0,
            option_ask=1.4,
            now=NOW_ET,
        )
        disabled = evaluate_market_exit_intelligence(
            _position(),
            _settings(trailing_stop_enabled=False),
            bars=_bars([100.0, 100.1, 100.2, 100.3, 100.4, 100.5]),
            option_bid=1.19,
            option_ask=1.21,
            now=NOW_ET,
        )

        self.assertEqual(decision.adaptive_trailing_percent, 35.0)
        self.assertIsNone(disabled.adaptive_trailing_percent)

    def test_updates_mfe_mae_and_counterfactual_threshold_hits(self):
        from market_exit_intelligence import evaluate_market_exit_intelligence

        decision = evaluate_market_exit_intelligence(
            _position(
                entry_price=1.0,
                highest_price=1.4,
                max_favorable_excursion_percent=25.0,
                max_adverse_excursion_percent=-10.0,
                counterfactual_stop_hits={},
                counterfactual_trailing_hits={},
            ),
            _settings(reversal_exit_enabled=False),
            bars=_bars([100.0, 100.0, 100.0, 100.0, 100.0, 100.0]),
            option_bid=0.69,
            option_ask=0.71,
            now=NOW_ET,
        )

        updates = decision.position_updates
        self.assertEqual(updates["max_favorable_excursion_percent"], 40.0)
        self.assertEqual(updates["max_adverse_excursion_percent"], -30.0)
        self.assertIn("20", updates["counterfactual_stop_hits"])
        self.assertIn("30", updates["counterfactual_stop_hits"])
        self.assertIn("10", updates["counterfactual_trailing_hits"])
        self.assertIn("15", updates["counterfactual_trailing_hits"])
        self.assertIn("20", updates["counterfactual_trailing_hits"])


if __name__ == "__main__":
    unittest.main()
