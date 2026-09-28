import pathlib
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


NOW = datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc)


def position(**updates):
    value = {
        "entry_price": 1.00,
        "current_price": 1.00,
        "option_bid": 1.00,
        "highest_price": 1.00,
        "original_quantity": 8,
        "remaining_quantity": 8,
        "expiration": "2026-09-04",
        "entry_risk_profile": "normal",
        "option_quote_observed_at": NOW.isoformat(),
    }
    value.update(updates)
    return value


class PremiumExitProfileTests(unittest.TestCase):
    def test_core_runner_settings_expose_customizable_defaults(self):
        from models import Settings

        settings = Settings()

        self.assertFalse(settings.core_runner_enabled)
        self.assertEqual(settings.core_runner_allocation_mode, "greater_of")
        self.assertEqual(settings.core_runner_allocation_percent, 20.0)
        self.assertEqual(settings.core_runner_activation_mfe_percent, 100.0)
        self.assertEqual(settings.core_runner_catastrophic_stop_percent, 65.0)
        self.assertEqual(
            settings.core_runner_trailing_tiers[-1],
            {"mfe_percent": 1000.0, "trail_percent": 20.0},
        )

    def test_core_runner_catastrophic_stop_accepts_zero_as_full_risk(self):
        from models import SettingsUpdate

        update = SettingsUpdate(core_runner_catastrophic_stop_percent=0)

        self.assertEqual(update.core_runner_catastrophic_stop_percent, 0)

    def test_exit_policy_settings_expose_loss_ladder_and_elastic_trail_defaults(self):
        from models import Settings

        settings = Settings()

        self.assertTrue(settings.coordinated_loss_ladder_enabled)
        self.assertEqual(
            [step["loss_percent"] for step in settings.coordinated_loss_ladder],
            [12.0, 18.0, 25.0, 35.0],
        )
        self.assertEqual(settings.coordinated_trailing_mode, "tightening")
        self.assertEqual(settings.exit_reprice_interval_seconds, 5)
        self.assertEqual(settings.profit_exit_reprice_interval_seconds, 3)
        self.assertEqual(settings.coordinated_break_even_required_confirmations, 2)
        self.assertTrue(settings.coordinated_break_even_preserve_runner)
        self.assertEqual(settings.profit_exit_marketable_offset_cents, 1.0)
    def test_coordinated_trailing_protection_ignores_non_executable_mark_high(self):
        from options_exit_policy import is_trailing_protection_eligible

        protected = is_trailing_protection_eligible(
            position(
                entry_price=0.35,
                highest_price=0.81,
                highest_executable_bid=0.38,
                option_bid=0.38,
                current_price=0.60,
                coordinated_trailing_armed=False,
            ),
            {"coordinated_exit_enabled": True},
            now=NOW,
        )

        self.assertFalse(protected)

    def test_progressive_trailing_settings_are_retained_by_api_model(self):
        from models import Settings

        settings = Settings(
            coordinated_progressive_trailing_enabled=False,
            coordinated_trailing_step_gain_percent=12,
            coordinated_trailing_step_tighten_percent=0.5,
            coordinated_trailing_min_percent=7,
            coordinated_trailing_volatility_gate_percent=9,
        )

        self.assertFalse(settings.coordinated_progressive_trailing_enabled)
        self.assertEqual(settings.coordinated_trailing_step_gain_percent, 12)
        self.assertEqual(settings.coordinated_trailing_step_tighten_percent, 0.5)
        self.assertEqual(settings.coordinated_trailing_min_percent, 7)
        self.assertEqual(settings.coordinated_trailing_volatility_gate_percent, 9)

    def test_trailing_protection_eligibility_uses_recorded_high_before_armed_flag_persists(self):
        from options_exit_policy import is_trailing_protection_eligible

        protected = is_trailing_protection_eligible(
            position(
                entry_price=0.28,
                highest_executable_bid=0.38,
                coordinated_trailing_armed=False,
                expiration="2026-09-04",
            ),
            {"coordinated_exit_enabled": True},
            now=datetime(2026, 9, 4, 15, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(protected)

    def test_low_premium_profile_has_wider_absolute_protection(self):
        from options_exit_policy import select_premium_exit_profile

        profile = select_premium_exit_profile(position(entry_price=0.19), {}, now=NOW)

        self.assertEqual(profile.tier, "low")
        self.assertEqual(profile.activation_percent, 25.0)
        self.assertEqual(profile.minimum_activation_cents, 5.0)
        self.assertEqual(profile.trailing_percent, 18.0)
        self.assertEqual(profile.minimum_trailing_cents, 4.0)

    def test_zero_dte_uses_low_premium_profile_even_when_premium_is_high(self):
        from options_exit_policy import select_premium_exit_profile

        profile = select_premium_exit_profile(
            position(entry_price=2.00, expiration="2026-09-03"),
            {},
            now=NOW,
        )

        self.assertEqual(profile.tier, "zero_dte")
        self.assertEqual(profile.activation_percent, 25.0)

    def test_medium_and_high_profiles(self):
        from options_exit_policy import select_premium_exit_profile

        medium = select_premium_exit_profile(position(entry_price=0.75), {}, now=NOW)
        high = select_premium_exit_profile(position(entry_price=4.50), {}, now=NOW)

        self.assertEqual((medium.activation_percent, medium.trailing_percent), (20.0, 15.0))
        self.assertEqual((high.activation_percent, high.trailing_percent), (12.0, 10.0))


class CoordinatedExitDecisionTests(unittest.TestCase):
    def test_suppressed_profit_floor_does_not_bypass_emergency_stop_for_runner_candidate(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                entry_price=0.15,
                option_bid=0.03,
                current_price=0.03,
                highest_executable_bid=0.19,
                original_quantity=5,
                remaining_quantity=1,
                profit_floor_armed=True,
                profit_floor_price=0.16,
                profit_stage_1_completed=True,
                core_runner_allocation_initialized=True,
                core_runner_candidate_quantity=1,
                core_runner_dedicated_quantity=0,
                core_runner_activated=False,
            ),
            {
                "core_runner_enabled": True,
                "core_runner_allocation_mode": "fixed",
                "core_runner_fixed_contracts": 1,
                "core_runner_min_contracts": 1,
                "core_runner_max_contracts": 1,
                "core_runner_activation_mfe_percent": 100,
                "core_runner_reserve_candidates_from_profit": True,
                "coordinated_emergency_stop_loss_percent": 50,
            },
            now=NOW,
        )

        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["exit_trigger"], "coordinated_emergency_stop")
        self.assertEqual(decision["quantity"], 1)
        self.assertEqual(decision["target_remaining_quantity"], 0)

    def test_suppressed_profit_floor_falls_through_to_loss_ladder_for_runner_candidate(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                entry_price=1.00,
                option_bid=0.80,
                current_price=0.80,
                highest_executable_bid=1.30,
                original_quantity=5,
                remaining_quantity=1,
                profit_floor_armed=True,
                profit_floor_price=1.01,
                profit_stage_1_completed=True,
                core_runner_allocation_initialized=True,
                core_runner_candidate_quantity=1,
                core_runner_dedicated_quantity=0,
                core_runner_activated=False,
            ),
            {
                "core_runner_enabled": True,
                "core_runner_allocation_mode": "fixed",
                "core_runner_fixed_contracts": 1,
                "core_runner_min_contracts": 1,
                "core_runner_max_contracts": 1,
                "core_runner_activation_mfe_percent": 100,
                "core_runner_reserve_candidates_from_profit": True,
                "core_runner_loss_ladder_consumes_candidates": True,
                "coordinated_emergency_stop_loss_percent": 50,
                "coordinated_loss_ladder_enabled": True,
                "coordinated_loss_ladder": [
                    {
                        "loss_percent": 15,
                        "quantity_mode": "percent_original",
                        "quantity": 10,
                        "confirmations": 1,
                        "allocation_target": "core_only",
                    }
                ],
            },
            now=NOW,
        )

        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["exit_trigger"], "loss_ladder_1")
        self.assertEqual(decision["quantity"], 1)
        self.assertEqual(decision["target_remaining_quantity"], 0)

    def test_core_runner_candidate_is_reserved_from_profit_stage(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                option_bid=1.25,
                current_price=1.25,
                highest_executable_bid=1.25,
                original_quantity=8,
                remaining_quantity=2,
            ),
            {
                "core_runner_enabled": True,
                "core_runner_allocation_mode": "fixed",
                "core_runner_fixed_contracts": 1,
                "core_runner_min_contracts": 1,
                "core_runner_max_contracts": 1,
                "core_runner_activation_mfe_percent": 100,
                "core_runner_reserve_candidates_from_profit": True,
                "coordinated_runner_reserve_quantity": 0,
            },
            now=NOW,
        )

        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["exit_trigger"], "profit_stage_1")
        self.assertEqual(decision["quantity"], 1)
        self.assertEqual(decision["target_remaining_quantity"], 1)
        self.assertEqual(decision["position_updates"]["core_runner_candidate_quantity"], 1)

    def test_activated_runner_is_excluded_from_core_loss_ladder_exit(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                option_bid=0.60,
                current_price=0.60,
                highest_executable_bid=1.00,
                original_quantity=8,
                remaining_quantity=3,
                core_runner_candidate_quantity=1,
                core_runner_dedicated_quantity=1,
                core_runner_activated=True,
                coordinated_loss_ladder_completed_steps=[0, 1, 2],
            ),
            {
                "core_runner_enabled": True,
                "core_runner_allocation_mode": "fixed",
                "core_runner_fixed_contracts": 1,
                "core_runner_min_contracts": 1,
                "core_runner_max_contracts": 1,
                "core_runner_activation_mfe_percent": 100,
                "core_runner_protect_loss_ladder": True,
                "core_runner_catastrophic_stop_percent": 0,
                "core_runner_trailing_enabled": False,
                "coordinated_loss_ladder_enabled": True,
                "coordinated_loss_ladder": [
                    {"loss_percent": 10, "quantity_mode": "fixed", "quantity": 1, "confirmations": 1},
                    {"loss_percent": 20, "quantity_mode": "fixed", "quantity": 1, "confirmations": 1},
                    {"loss_percent": 30, "quantity_mode": "fixed", "quantity": 1, "confirmations": 1},
                    {"loss_percent": 35, "quantity_mode": "percent_remaining", "quantity": 100, "confirmations": 1},
                ],
            },
            now=NOW,
        )

        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["exit_trigger"], "loss_ladder_4")
        self.assertEqual(decision["quantity"], 2)
        self.assertEqual(decision["target_remaining_quantity"], 1)
        self.assertEqual(decision["exit_allocation_target"], "core_only")

    def test_ordinary_trail_cannot_liquidate_only_remaining_runner(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                option_bid=1.50,
                option_ask=1.52,
                current_price=1.50,
                highest_executable_bid=2.00,
                original_quantity=8,
                remaining_quantity=1,
                profit_stage_1_completed=True,
                profit_stage_2_completed=True,
                core_runner_candidate_quantity=1,
                core_runner_dedicated_quantity=1,
                core_runner_activated=True,
            ),
            {
                "core_runner_enabled": True,
                "core_runner_allocation_mode": "fixed",
                "core_runner_fixed_contracts": 1,
                "core_runner_min_contracts": 1,
                "core_runner_max_contracts": 1,
                "core_runner_activation_mfe_percent": 100,
                "core_runner_protect_ordinary_trailing": True,
                "core_runner_catastrophic_stop_percent": 0,
                "core_runner_trailing_enabled": False,
            },
            now=NOW,
        )

        self.assertFalse(decision["triggered"])
        self.assertEqual(decision["position_updates"]["core_runner_suppressed_trigger"], "coordinated_trailing_stop")
        self.assertEqual(decision["target_remaining_quantity"], 1)

    def test_runner_trail_closes_only_dedicated_runner_quantity(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                option_bid=1.20,
                option_ask=1.22,
                current_price=1.20,
                highest_executable_bid=2.00,
                original_quantity=8,
                remaining_quantity=1,
                core_runner_candidate_quantity=1,
                core_runner_dedicated_quantity=1,
                core_runner_activated=True,
            ),
            {
                "core_runner_enabled": True,
                "core_runner_allocation_mode": "fixed",
                "core_runner_fixed_contracts": 1,
                "core_runner_min_contracts": 1,
                "core_runner_max_contracts": 1,
                "core_runner_activation_mfe_percent": 100,
                "core_runner_catastrophic_stop_percent": 0,
                "core_runner_trailing_enabled": True,
                "core_runner_trailing_mode": "tiered",
                "core_runner_trailing_tiers": [
                    {"mfe_percent": 100, "trail_percent": 35},
                ],
                "core_runner_trailing_confirmations": 1,
                "core_runner_trailing_confirmation_interval_seconds": 0,
            },
            now=NOW,
        )

        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["exit_trigger"], "runner_trailing_stop")
        self.assertEqual(decision["quantity"], 1)
        self.assertEqual(decision["target_remaining_quantity"], 0)
        self.assertEqual(decision["exit_allocation_target"], "runners_only")

    def test_loss_ladder_sells_configured_percent_and_records_completed_step(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                option_bid=0.87,
                current_price=0.87,
                original_quantity=10,
                remaining_quantity=10,
            ),
            {
                "coordinated_loss_ladder_enabled": True,
                "coordinated_loss_ladder": [
                    {"loss_percent": 12, "quantity_mode": "percent_original", "quantity": 10, "confirmations": 1},
                    {"loss_percent": 18, "quantity_mode": "percent_original", "quantity": 20},
                ],
            },
            now=NOW,
        )

        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["exit_trigger"], "loss_ladder_1")
        self.assertEqual(decision["quantity"], 1)
        self.assertEqual(decision["position_updates"]["coordinated_loss_ladder_pending_step"], 0)

    def test_loss_ladder_skips_completed_steps_and_uses_fixed_contract_quantity(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                option_bid=0.80,
                current_price=0.80,
                original_quantity=10,
                remaining_quantity=9,
                coordinated_loss_ladder_completed_steps=[0],
            ),
            {
                "coordinated_loss_ladder_enabled": True,
                "coordinated_loss_ladder": [
                    {"loss_percent": 12, "quantity_mode": "fixed", "quantity": 1},
                    {"loss_percent": 18, "quantity_mode": "fixed", "quantity": 2, "confirmations": 1},
                ],
            },
            now=NOW,
        )

        self.assertEqual(decision["exit_trigger"], "loss_ladder_2")
        self.assertEqual(decision["quantity"], 2)
        self.assertEqual(decision["position_updates"]["coordinated_loss_ladder_pending_step"], 1)

    def test_elastic_trail_widens_by_gain_step_but_never_lowers_floor(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                entry_price=2.00,
                option_bid=2.52,
                option_ask=2.54,
                current_price=2.52,
                highest_price=2.70,
                highest_executable_bid=2.70,
                coordinated_trailing_armed=True,
                coordinated_trailing_floor=2.50,
                profit_stage_1_completed=True,
                profit_stage_2_completed=True,
                premium_mark_history=[2.30, 2.45, 2.60, 2.70],
            ),
            {
                "coordinated_trailing_mode": "elastic",
                "coordinated_elastic_trailing_start_percent": 6,
                "coordinated_elastic_trailing_step_gain_percent": 10,
                "coordinated_elastic_trailing_step_widen_percent": 1,
                "coordinated_elastic_trailing_max_percent": 10,
                "coordinated_trailing_spread_multiplier": 2,
            },
            now=NOW,
        )

        self.assertEqual(decision["position_updates"]["coordinated_effective_trailing_percent"], 9.0)
        self.assertEqual(decision["position_updates"]["coordinated_trailing_floor"], 2.50)

    def test_calm_premium_staircase_tightens_trail_as_profit_expands(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                entry_price=0.35,
                option_bid=0.55,
                current_price=0.55,
                highest_price=0.63,
                highest_executable_bid=0.62,
                original_quantity=8,
                remaining_quantity=2,
                profit_stage_1_completed=True,
                profit_stage_2_completed=True,
                premium_mark_history=[0.50, 0.52, 0.55, 0.58, 0.60, 0.62],
            ),
            {
                "coordinated_progressive_trailing_enabled": True,
                "coordinated_trailing_step_gain_percent": 10.0,
                "coordinated_trailing_step_tighten_percent": 1.0,
                "coordinated_trailing_min_percent": 8.0,
                "coordinated_trailing_volatility_gate_percent": 8.0,
            },
            now=NOW,
        )

        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["exit_trigger"], "coordinated_trailing_stop")
        self.assertEqual(decision["position_updates"]["coordinated_trailing_step"], 5)
        self.assertEqual(decision["position_updates"]["coordinated_effective_trailing_percent"], 10.0)
        self.assertEqual(decision["position_updates"]["coordinated_trailing_floor"], 0.558)

    def test_noisy_premium_history_gates_next_staircase_tightening(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                entry_price=0.35,
                option_bid=0.54,
                current_price=0.54,
                highest_price=0.63,
                highest_executable_bid=0.62,
                original_quantity=8,
                remaining_quantity=2,
                profit_stage_1_completed=True,
                profit_stage_2_completed=True,
                premium_mark_history=[0.30, 0.60, 0.40, 0.62],
            ),
            {
                "coordinated_progressive_trailing_enabled": True,
                "coordinated_trailing_step_gain_percent": 10.0,
                "coordinated_trailing_step_tighten_percent": 1.0,
                "coordinated_trailing_min_percent": 8.0,
                "coordinated_trailing_volatility_gate_percent": 8.0,
            },
            now=NOW,
        )

        self.assertFalse(decision["triggered"])
        self.assertEqual(decision["position_updates"]["coordinated_trailing_step"], 0)
        self.assertEqual(decision["position_updates"]["coordinated_effective_trailing_percent"], 15.0)
        self.assertGreater(decision["position_updates"]["coordinated_premium_volatility_percent"], 8.0)

    def test_progressive_trailing_floor_never_moves_down(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                entry_price=0.35,
                option_bid=0.57,
                current_price=0.57,
                highest_price=0.63,
                highest_executable_bid=0.62,
                original_quantity=8,
                remaining_quantity=2,
                profit_stage_1_completed=True,
                profit_stage_2_completed=True,
                coordinated_trailing_armed=True,
                coordinated_trailing_step=4,
                coordinated_effective_trailing_percent=11.0,
                coordinated_trailing_floor=0.58,
                premium_mark_history=[0.56, 0.58, 0.60, 0.62],
            ),
            {"coordinated_progressive_trailing_enabled": True},
            now=NOW,
        )

        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["position_updates"]["coordinated_trailing_floor"], 0.58)

    def test_losing_reversal_warning_honors_partial_sell_percentage(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                entry_price=0.94,
                option_bid=0.80,
                current_price=0.80,
                highest_price=0.95,
                original_quantity=3,
                remaining_quantity=3,
            ),
            {},
            intelligence=SimpleNamespace(
                triggered=True,
                exit_trigger="reversal_warning",
                sell_percent=25.0,
                reasons=("persistent reversal warning reached",),
            ),
            now=NOW,
        )

        self.assertEqual(decision["exit_trigger"], "reversal_warning")
        self.assertEqual(decision["quantity"], 1)

    def test_confirmed_reversal_still_closes_entire_position(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                entry_price=0.94,
                option_bid=0.80,
                current_price=0.80,
                highest_price=0.95,
                original_quantity=3,
                remaining_quantity=3,
            ),
            {},
            intelligence=SimpleNamespace(
                triggered=True,
                exit_trigger="reversal_confirmed",
                sell_percent=100.0,
                reasons=("persistent market reversal confirmed",),
            ),
            now=NOW,
        )

        self.assertEqual(decision["quantity"], 3)

    def test_first_profit_stage_sells_half_of_original_quantity(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(option_bid=1.25, current_price=1.25, highest_price=1.25),
            {},
            now=NOW,
        )

        self.assertEqual(decision["exit_trigger"], "profit_stage_1")
        self.assertEqual(decision["quantity"], 4)

    def test_fast_scalp_profile_takes_first_profit_at_ten_percent(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                option_bid=1.10,
                current_price=1.10,
                highest_price=1.10,
                entry_exit_profile="fast_scalp",
            ),
            {},
            now=NOW,
        )

        self.assertEqual(decision["exit_trigger"], "profit_stage_1")
        self.assertEqual(decision["quantity"], 4)

    def test_second_profit_stage_sells_quarter_of_original_quantity(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                option_bid=1.35,
                current_price=1.35,
                highest_price=1.35,
                remaining_quantity=4,
                profit_stage_1_completed=True,
                profit_floor_armed=True,
                profit_floor_price=1.01,
            ),
            {},
            now=NOW,
        )

        self.assertEqual(decision["exit_trigger"], "profit_stage_2")
        self.assertEqual(decision["quantity"], 2)

    def test_second_profit_stage_preserves_last_trailing_runner(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                entry_price=0.31,
                option_bid=0.42,
                current_price=0.42,
                highest_price=0.42,
                highest_executable_bid=0.42,
                original_quantity=2,
                remaining_quantity=1,
                profit_stage_1_completed=True,
                profit_floor_armed=True,
                profit_floor_price=0.32,
            ),
            {"coordinated_runner_reserve_quantity": 1},
            now=NOW,
        )

        self.assertFalse(decision["triggered"])
        self.assertTrue(decision["position_updates"]["profit_stage_2_completed"])
        self.assertTrue(decision["position_updates"]["coordinated_trailing_armed"])

    def test_normal_stop_requires_two_distinct_confirming_quotes(self):
        from options_exit_policy import evaluate_coordinated_exit

        first = evaluate_coordinated_exit(
            position(option_bid=0.64, current_price=0.64),
            {
                "coordinated_stop_required_confirmations": 2,
                "coordinated_stop_confirmation_interval_seconds": 1,
                "coordinated_emergency_stop_loss_percent": 50,
            },
            now=NOW,
        )
        second = evaluate_coordinated_exit(
            position(
                option_bid=0.63,
                current_price=0.63,
                option_quote_observed_at="2026-09-03T15:00:02+00:00",
                coordinated_stop_confirmation_count=1,
                coordinated_stop_last_quote_observed_at=NOW.isoformat(),
                coordinated_stop_last_confirmation_at=NOW.isoformat(),
            ),
            {
                "coordinated_stop_required_confirmations": 2,
                "coordinated_stop_confirmation_interval_seconds": 1,
                "coordinated_emergency_stop_loss_percent": 50,
            },
            now=datetime(2026, 9, 3, 15, 0, 2, tzinfo=timezone.utc),
        )

        self.assertFalse(first["triggered"])
        self.assertEqual(first["action"], "stop_confirmation_pending")
        self.assertEqual(first["position_updates"]["coordinated_stop_confirmation_count"], 1)
        self.assertTrue(second["triggered"])
        self.assertEqual(second["exit_trigger"], "coordinated_hard_stop")

    def test_repeated_evaluation_of_same_quote_does_not_confirm_stop(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                option_bid=0.64,
                current_price=0.64,
                coordinated_stop_confirmation_count=1,
                coordinated_stop_last_quote_observed_at=NOW.isoformat(),
                coordinated_stop_last_confirmation_at=NOW.isoformat(),
            ),
            {
                "coordinated_stop_required_confirmations": 2,
                "coordinated_stop_confirmation_interval_seconds": 1,
                "coordinated_emergency_stop_loss_percent": 50,
            },
            now=NOW,
        )

        self.assertFalse(decision["triggered"])
        self.assertEqual(decision["position_updates"]["coordinated_stop_confirmation_count"], 1)

    def test_emergency_stop_exits_immediately(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(option_bid=0.49, current_price=0.49),
            {
                "coordinated_stop_required_confirmations": 2,
                "coordinated_emergency_stop_loss_percent": 50,
            },
            now=NOW,
        )

        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["exit_trigger"], "coordinated_emergency_stop")

    def test_emergency_stop_is_not_delayed_by_armed_break_even_confirmation(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                entry_price=0.30,
                option_bid=0.14,
                current_price=0.14,
                highest_price=0.38,
                highest_executable_bid=0.38,
                expiration="2026-09-03",
            ),
            {
                "coordinated_break_even_required_confirmations": 2,
                "coordinated_emergency_stop_loss_percent": 50,
            },
            now=NOW,
        )

        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["exit_trigger"], "coordinated_emergency_stop")

    def test_profit_floor_replaces_negative_stop_after_first_stage(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                option_bid=1.00,
                current_price=1.00,
                highest_price=1.30,
                remaining_quantity=4,
                profit_stage_1_completed=True,
                profit_floor_armed=True,
                profit_floor_price=1.01,
            ),
            {},
            now=NOW,
        )

        self.assertEqual(decision["exit_trigger"], "profit_floor")
        self.assertEqual(decision["quantity"], 4)

    def test_high_premium_trail_arms_at_twelve_percent_and_exits_on_retrace(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                entry_price=4.50,
                option_bid=4.98,
                current_price=4.98,
                highest_price=5.60,
                highest_executable_bid=5.60,
            ),
            {},
            now=NOW,
        )

        self.assertEqual(decision["exit_trigger"], "coordinated_trailing_stop")
        self.assertEqual(decision["quantity"], 8)

    def test_high_premium_break_even_guard_arms_before_first_profit_stage(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                entry_price=4.50,
                option_bid=4.50,
                current_price=4.50,
                highest_price=5.10,
                highest_executable_bid=5.10,
            ),
            {
                "coordinated_break_even_required_confirmations": 1,
                "coordinated_break_even_preserve_runner": False,
            },
            now=NOW,
        )

        self.assertEqual(decision["exit_trigger"], "coordinated_break_even")
        self.assertEqual(decision["quantity"], 8)

    def test_zero_dte_break_even_requires_distinct_quotes_and_preserves_runner(self):
        from options_exit_policy import evaluate_coordinated_exit

        first = evaluate_coordinated_exit(
            position(
                entry_price=0.30,
                option_bid=0.30,
                current_price=0.30,
                highest_price=0.385,
                highest_executable_bid=0.38,
                original_quantity=5,
                remaining_quantity=5,
                expiration="2026-09-03",
            ),
            {
                "coordinated_break_even_required_confirmations": 2,
                "coordinated_break_even_confirmation_interval_seconds": 1,
                "coordinated_break_even_preserve_runner": True,
                "coordinated_runner_reserve_quantity": 1,
            },
            now=NOW,
        )

        second_position = position(
            entry_price=0.30,
            option_bid=0.30,
            current_price=0.30,
            original_quantity=5,
            remaining_quantity=5,
            expiration="2026-09-03",
            option_quote_observed_at="2026-09-03T15:00:02+00:00",
            **first["position_updates"],
        )
        second = evaluate_coordinated_exit(
            second_position,
            {
                "coordinated_break_even_required_confirmations": 2,
                "coordinated_break_even_confirmation_interval_seconds": 1,
                "coordinated_break_even_preserve_runner": True,
                "coordinated_runner_reserve_quantity": 1,
            },
            now=datetime(2026, 9, 3, 15, 0, 2, tzinfo=timezone.utc),
        )

        self.assertFalse(first["triggered"])
        self.assertEqual(first["action"], "break_even_confirmation_pending")
        self.assertEqual(first["position_updates"]["coordinated_break_even_confirmation_count"], 1)
        self.assertTrue(second["triggered"])
        self.assertEqual(second["exit_trigger"], "coordinated_break_even")
        self.assertEqual(second["quantity"], 4)

        runner = evaluate_coordinated_exit(
            position(
                entry_price=0.30,
                option_bid=0.30,
                current_price=0.30,
                highest_price=0.385,
                highest_executable_bid=0.38,
                original_quantity=5,
                remaining_quantity=1,
                expiration="2026-09-03",
                coordinated_break_even_runner_reserved=True,
                coordinated_break_even_runner_high=0.38,
                coordinated_break_even_confirmation_count=2,
            ),
            {
                "coordinated_break_even_required_confirmations": 2,
                "coordinated_break_even_preserve_runner": True,
                "coordinated_runner_reserve_quantity": 1,
            },
            now=NOW,
        )
        self.assertFalse(runner["triggered"])
        self.assertEqual(runner["action"], "break_even_runner_held")

    def test_normal_and_high_risk_hard_stops_differ(self):
        from options_exit_policy import evaluate_coordinated_exit

        confirmation_settings = {
            "coordinated_stop_required_confirmations": 1,
            "coordinated_emergency_stop_loss_percent": 60,
        }
        normal = evaluate_coordinated_exit(
            position(option_bid=0.64, current_price=0.64), confirmation_settings, now=NOW
        )
        high_risk = evaluate_coordinated_exit(
            position(
                option_bid=0.49,
                current_price=0.49,
                entry_risk_profile="high_risk",
            ),
            confirmation_settings,
            now=NOW,
        )

        self.assertEqual(normal["exit_trigger"], "coordinated_hard_stop")
        self.assertEqual(high_risk["exit_trigger"], "coordinated_hard_stop")

    def test_stale_quote_cannot_trigger_discretionary_exit(self):
        from options_exit_policy import evaluate_coordinated_exit

        decision = evaluate_coordinated_exit(
            position(
                option_bid=0.50,
                current_price=0.50,
                option_quote_observed_at="2026-09-03T14:59:30+00:00",
            ),
            {"coordinated_exit_quote_max_age_seconds": 15.0},
            now=NOW,
        )

        self.assertFalse(decision["triggered"])
        self.assertEqual(decision["action"], "stale_quote")


if __name__ == "__main__":
    unittest.main()
