import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

NOW = datetime(2026, 9, 22, 15, 0, tzinfo=timezone.utc)


def settings(**updates):
    value = {
        "core_runner_enabled": True,
        "core_runner_allocation_mode": "greater_of",
        "core_runner_allocation_percent": 20.0,
        "core_runner_fixed_contracts": 1,
        "core_runner_min_contracts": 1,
        "core_runner_max_contracts": 2,
        "core_runner_allow_single_contract": False,
        "core_runner_activation_mfe_percent": 100.0,
        "core_runner_reserve_candidates_from_profit": True,
        "core_runner_loss_ladder_consumes_candidates": True,
        "core_runner_protect_loss_ladder": True,
        "core_runner_protect_hard_stop": True,
        "core_runner_protect_break_even": True,
        "core_runner_protect_profit_stages": True,
        "core_runner_protect_ordinary_trailing": True,
        "core_runner_protect_reversal_warning": True,
        "core_runner_confirmed_reversal_exits": True,
        "core_runner_catastrophic_stop_percent": 65.0,
        "core_runner_catastrophic_confirmations": 2,
        "core_runner_catastrophic_confirmation_interval_seconds": 3.0,
        "core_runner_trailing_enabled": True,
        "core_runner_trailing_mode": "tiered",
        "core_runner_fixed_trailing_percent": 35.0,
        "core_runner_trailing_tiers": [
            {"mfe_percent": 100.0, "trail_percent": 35.0},
            {"mfe_percent": 300.0, "trail_percent": 30.0},
            {"mfe_percent": 500.0, "trail_percent": 25.0},
            {"mfe_percent": 1000.0, "trail_percent": 20.0},
        ],
        "core_runner_min_trailing_cents": 0.0,
        "core_runner_spread_multiplier": 2.0,
        "core_runner_trailing_confirmations": 2,
        "core_runner_trailing_confirmation_interval_seconds": 3.0,
        "core_runner_allow_floor_to_move_down": False,
    }
    value.update(updates)
    return value


def position(**updates):
    value = {
        "id": "position-1",
        "entry_price": 1.0,
        "option_bid": 1.0,
        "option_ask": 1.02,
        "highest_executable_bid": 1.0,
        "original_quantity": 8,
        "remaining_quantity": 8,
        "opened_at": (NOW - timedelta(minutes=30)).isoformat(),
        "option_quote_observed_at": NOW.isoformat(),
    }
    value.update(updates)
    return value


class RunnerAllocationTests(unittest.TestCase):
    def test_greater_of_allocation_reserves_twenty_percent_or_minimum(self):
        from core_runner_policy import update_runner_state

        state = update_runner_state(position(), settings(), bid=1.0, now=NOW)

        self.assertEqual(state.candidate_quantity, 1)
        self.assertEqual(state.core_quantity, 7)
        self.assertFalse(state.activated)

    def test_maximum_caps_runner_allocation(self):
        from core_runner_policy import update_runner_state

        state = update_runner_state(
            position(original_quantity=20, remaining_quantity=20),
            settings(core_runner_allocation_percent=50, core_runner_max_contracts=2),
            bid=1.0,
            now=NOW,
        )

        self.assertEqual(state.candidate_quantity, 2)

    def test_single_contract_requires_explicit_permission(self):
        from core_runner_policy import update_runner_state

        blocked = update_runner_state(
            position(original_quantity=1, remaining_quantity=1),
            settings(),
            bid=1.0,
            now=NOW,
        )
        allowed = update_runner_state(
            position(original_quantity=1, remaining_quantity=1),
            settings(core_runner_allow_single_contract=True),
            bid=1.0,
            now=NOW,
        )

        self.assertEqual(blocked.candidate_quantity, 0)
        self.assertEqual(allowed.candidate_quantity, 1)

    def test_candidate_becomes_permanently_dedicated_at_mfe(self):
        from core_runner_policy import update_runner_state

        state = update_runner_state(
            position(highest_executable_bid=2.05, option_bid=2.0),
            settings(),
            bid=2.0,
            now=NOW,
        )

        self.assertTrue(state.activated)
        self.assertEqual(state.dedicated_quantity, 1)
        self.assertEqual(state.protected_quantity, 1)
        self.assertIn("core_runner_activated_at", state.updates)

    def test_profit_stage_is_capped_to_preserve_candidate_before_activation(self):
        from core_runner_policy import cap_exit_quantity, update_runner_state

        state = update_runner_state(position(remaining_quantity=2), settings(), bid=1.2, now=NOW)
        decision = cap_exit_quantity(
            {
                "triggered": True,
                "action": "sell",
                "exit_trigger": "profit_stage_1",
                "quantity": 2,
                "position_updates": {},
            },
            state,
            settings(),
        )

        self.assertEqual(decision["quantity"], 1)
        self.assertEqual(decision["target_remaining_quantity"], 1)

    def test_loss_ladder_can_consume_candidate_before_activation(self):
        from core_runner_policy import cap_exit_quantity, update_runner_state

        state = update_runner_state(position(remaining_quantity=2), settings(), bid=0.8, now=NOW)
        decision = cap_exit_quantity(
            {
                "triggered": True,
                "action": "sell",
                "exit_trigger": "loss_ladder_4",
                "quantity": 2,
                "position_updates": {},
            },
            state,
            settings(),
        )

        self.assertEqual(decision["quantity"], 2)

    def test_consumed_candidate_is_not_recreated_on_next_quote(self):
        from core_runner_policy import update_runner_state

        state = update_runner_state(
            position(
                remaining_quantity=3,
                core_runner_original_quantity=8,
                core_runner_candidate_quantity=0,
                core_runner_dedicated_quantity=0,
            ),
            settings(),
            bid=0.80,
            now=NOW,
        )

        self.assertEqual(state.candidate_quantity, 0)

    def test_greater_of_allocation_includes_fixed_contract_setting(self):
        from core_runner_policy import update_runner_state

        state = update_runner_state(
            position(original_quantity=10, remaining_quantity=10),
            settings(core_runner_allocation_percent=10, core_runner_fixed_contracts=3),
            bid=1.0,
            now=NOW,
        )

        self.assertEqual(state.candidate_quantity, 2)


class RunnerExitTests(unittest.TestCase):
    def activated_position(self, **updates):
        value = position(
            option_bid=1.8,
            option_ask=1.82,
            highest_executable_bid=2.0,
            remaining_quantity=2,
            core_runner_candidate_quantity=1,
            core_runner_dedicated_quantity=1,
            core_runner_activated=True,
            core_runner_activated_at=(NOW - timedelta(minutes=5)).isoformat(),
        )
        value.update(updates)
        return value

    def test_zero_catastrophic_stop_disables_price_exit(self):
        from core_runner_policy import evaluate_runner_exit, update_runner_state

        p = self.activated_position(option_bid=0.01, highest_executable_bid=2.0)
        state = update_runner_state(p, settings(), bid=0.01, now=NOW)
        decision = evaluate_runner_exit(
            p,
            settings(
                core_runner_catastrophic_stop_percent=0,
                core_runner_trailing_enabled=False,
            ),
            state,
            bid=0.01,
            ask=0.02,
            now=NOW,
        )

        self.assertIsNone(decision)

    def test_catastrophic_stop_requires_configured_confirmations(self):
        from core_runner_policy import evaluate_runner_exit, update_runner_state

        p = self.activated_position(option_bid=0.30, option_quote_observed_at=NOW.isoformat())
        state = update_runner_state(p, settings(), bid=0.30, now=NOW)
        first = evaluate_runner_exit(p, settings(), state, bid=0.30, ask=0.31, now=NOW)
        p.update(first["position_updates"])
        p["option_quote_observed_at"] = (NOW + timedelta(seconds=4)).isoformat()
        state = update_runner_state(p, settings(), bid=0.29, now=NOW + timedelta(seconds=4))
        second = evaluate_runner_exit(
            p,
            settings(),
            state,
            bid=0.29,
            ask=0.30,
            now=NOW + timedelta(seconds=4),
        )

        self.assertFalse(first["triggered"])
        self.assertTrue(second["triggered"])
        self.assertEqual(second["exit_trigger"], "runner_catastrophic_stop")
        self.assertEqual(second["quantity"], 1)

    def test_tiered_trail_selects_highest_earned_tier_and_confirms_breach(self):
        from core_runner_policy import evaluate_runner_exit, update_runner_state

        p = self.activated_position(
            option_bid=3.35,
            option_ask=3.37,
            highest_executable_bid=5.0,
            core_runner_trailing_floor=3.5,
            option_quote_observed_at=NOW.isoformat(),
        )
        state = update_runner_state(p, settings(), bid=3.35, now=NOW)
        first = evaluate_runner_exit(p, settings(), state, bid=3.35, ask=3.37, now=NOW)
        p.update(first["position_updates"])
        p["option_quote_observed_at"] = (NOW + timedelta(seconds=4)).isoformat()
        state = update_runner_state(p, settings(), bid=3.30, now=NOW + timedelta(seconds=4))
        second = evaluate_runner_exit(
            p,
            settings(),
            state,
            bid=3.30,
            ask=3.32,
            now=NOW + timedelta(seconds=4),
        )

        self.assertEqual(first["position_updates"]["core_runner_trailing_tier_mfe_percent"], 300.0)
        self.assertEqual(first["position_updates"]["core_runner_trailing_percent"], 30.0)
        self.assertFalse(first["triggered"])
        self.assertTrue(second["triggered"])
        self.assertEqual(second["exit_trigger"], "runner_trailing_stop")

    def test_runner_zero_dte_liquidation_uses_runner_specific_cutoff(self):
        from core_runner_policy import evaluate_runner_exit, update_runner_state

        now = datetime(2026, 9, 22, 19, 41, tzinfo=timezone.utc)
        p = self.activated_position(expiration="2026-09-22", option_bid=1.80)
        state = update_runner_state(p, settings(), bid=1.80, now=now)
        decision = evaluate_runner_exit(
            p,
            settings(
                core_runner_zero_dte_liquidation_enabled=True,
                core_runner_zero_dte_liquidation_time="15:40",
            ),
            state,
            bid=1.80,
            ask=1.82,
            now=now,
        )

        self.assertTrue(decision["triggered"])
        self.assertEqual(decision["exit_trigger"], "runner_0dte_liquidation")
        self.assertEqual(decision["quantity"], 1)


if __name__ == "__main__":
    unittest.main()
