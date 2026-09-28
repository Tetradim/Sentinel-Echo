import pathlib
import sys
import unittest
from datetime import datetime, timezone


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class EntryControlsTests(unittest.TestCase):
    def test_explicit_high_risk_language_caps_but_does_not_block_entry(self):
        from entry_controls import alert_risk_size_cap

        cap, reasons = alert_risk_size_cap(
            "$SPY $762 PUTS EXPIRATION 9/2/2026 $.18 Entry high risk lotto, "
            "size for $0, or skip; sized for a full loss"
        )

        self.assertEqual(cap, 25.0)
        self.assertIn("high risk", reasons)
        self.assertIn("lotto", reasons)
        self.assertIn("size for zero", reasons)
        self.assertIn("full loss", reasons)

    def test_normal_entry_has_no_textual_risk_cap(self):
        from entry_controls import alert_risk_size_cap

        cap, reasons = alert_risk_size_cap(
            "$SPY $765 CALLS EXPIRATION 9/2/2026 $.55 Entry"
        )

        self.assertIsNone(cap)
        self.assertEqual(reasons, [])

    def test_wont_go_itm_language_uses_high_risk_size_cap(self):
        from entry_controls import alert_risk_size_cap

        cap, reasons = alert_risk_size_cap(
            "$SPY $764 PUTS EXPIRATION 9/8/2026 $.29 Entry; these won't go ITM"
        )

        self.assertEqual(cap, 25.0)
        self.assertIn("not expected in the money", reasons)

    def test_sudden_profit_language_selects_fast_scalp_exit_profile(self):
        from entry_controls import alert_exit_profile

        self.assertEqual(
            alert_exit_profile("Looking for a sudden profit to sell"),
            "fast_scalp",
        )
        self.assertEqual(alert_exit_profile("Regular swing entry"), "standard")

    def test_plain_buy_is_blocked_when_same_contract_is_already_open(self):
        from entry_controls import existing_contract_entry_block_reason

        reason = existing_contract_entry_block_reason(
            [
                {
                    "id": "position-1",
                    "status": "open",
                    "ticker": "QQQ",
                    "strike": 716.0,
                    "option_type": "CALL",
                    "expiration": "8/26/2026",
                    "remaining_quantity": 100,
                }
            ],
            {
                "ticker": "QQQ",
                "strike": 716.0,
                "option_type": "CALL",
                "expiration": "2026-08-26",
            },
            "$QQQ 716C 8/26 @ .50 Entry",
        )

        self.assertEqual(reason, "blocked: open position exists for QQQ 716.0 CALL 2026-08-26")

    def test_explicit_scale_in_language_allows_same_contract_buy(self):
        from entry_controls import existing_contract_entry_block_reason

        reason = existing_contract_entry_block_reason(
            [
                {
                    "id": "position-1",
                    "status": "open",
                    "ticker": "QQQ",
                    "strike": 716.0,
                    "option_type": "CALL",
                    "expiration": "8/26/2026",
                    "remaining_quantity": 100,
                }
            ],
            {
                "ticker": "QQQ",
                "strike": 716.0,
                "option_type": "CALL",
                "expiration": "2026-08-26",
            },
            "$QQQ 716C 8/26 @ .47 average down",
        )

        self.assertIsNone(reason)

    def test_average_fill_followup_does_not_count_as_scale_in_permission(self):
        from entry_controls import existing_contract_entry_block_reason

        reason = existing_contract_entry_block_reason(
            [
                {
                    "id": "position-1",
                    "status": "open",
                    "ticker": "QQQ",
                    "strike": 716.0,
                    "option_type": "CALL",
                    "expiration": "8/26/2026",
                    "remaining_quantity": 100,
                }
            ],
            {
                "ticker": "QQQ",
                "strike": 716.0,
                "option_type": "CALL",
                "expiration": "2026-08-26",
            },
            "$QQQ 716C 8/26 @ .50 Entry\nAVG FILL .48",
        )

        self.assertEqual(reason, "blocked: open position exists for QQQ 716.0 CALL 2026-08-26")

    def test_closed_contract_cannot_be_reopened_same_session_by_recycled_alert(self):
        from entry_controls import existing_contract_entry_block_reason

        reason = existing_contract_entry_block_reason(
            [
                {
                    "id": "position-closed",
                    "status": "closed",
                    "ticker": "SPY",
                    "strike": 757.0,
                    "option_type": "PUT",
                    "expiration": "2026-09-10",
                    "remaining_quantity": 0,
                    "closed_at": "2026-09-09T16:36:25+00:00",
                }
            ],
            {
                "ticker": "SPY",
                "strike": 757.0,
                "option_type": "PUT",
                "expiration": "09/10/26",
            },
            (
                "$SPY $757 PUTS EXPIRATION 9/10/2026 $.92 Entry\n"
                "Swinging into tomorrow. No DCA. No adds. Simply riding original position."
            ),
            now=datetime(2026, 9, 9, 19, 11, tzinfo=timezone.utc),
        )

        self.assertEqual(
            reason,
            "blocked: contract already closed this session for SPY 757.0 PUT 2026-09-10",
        )

    def test_explicit_reentry_can_reopen_closed_contract_same_session(self):
        from entry_controls import existing_contract_entry_block_reason

        reason = existing_contract_entry_block_reason(
            [
                {
                    "id": "position-closed",
                    "status": "closed",
                    "ticker": "SPY",
                    "strike": 757.0,
                    "option_type": "PUT",
                    "expiration": "2026-09-10",
                    "closed_at": "2026-09-09T16:36:25+00:00",
                }
            ],
            {
                "ticker": "SPY",
                "strike": 757.0,
                "option_type": "PUT",
                "expiration": "09/10/26",
            },
            "RE-ENTER SPY 757P 9/10 @ .52",
            now=datetime(2026, 9, 9, 19, 11, tzinfo=timezone.utc),
        )

        self.assertIsNone(reason)

    def test_explicit_readding_can_reopen_closed_contract_same_session(self):
        from entry_controls import existing_contract_entry_block_reason

        reason = existing_contract_entry_block_reason(
            [
                {
                    "id": "position-closed",
                    "status": "closed",
                    "ticker": "SPY",
                    "strike": 768.0,
                    "option_type": "CALL",
                    "expiration": "2026-09-11",
                    "remaining_quantity": 0,
                    "closed_at": "2026-09-11T14:06:15+00:00",
                }
            ],
            {
                "ticker": "SPY",
                "strike": 768.0,
                "option_type": "CALL",
                "expiration": "09/11/26",
            },
            (
                "$SPY $768 CALLS EXPIRATION 9/11/2026 $.5 Entry\n"
                "RE-ADDING SPY $768 CALLS $.35 FILL "
                "(looking for a $.28-$.3 final AVG)"
            ),
            now=datetime(2026, 9, 11, 14, 28, tzinfo=timezone.utc),
        )

        self.assertIsNone(reason)

    def test_future_readding_plan_cannot_reopen_closed_contract(self):
        from entry_controls import existing_contract_entry_block_reason

        reason = existing_contract_entry_block_reason(
            [
                {
                    "status": "closed",
                    "ticker": "SPY",
                    "strike": 768.0,
                    "option_type": "CALL",
                    "expiration": "2026-09-11",
                    "closed_at": "2026-09-11T14:06:15+00:00",
                }
            ],
            {
                "ticker": "SPY",
                "strike": 768.0,
                "option_type": "CALL",
                "expiration": "09/11/26",
            },
            "Looking to re-add SPY 768C if the setup returns",
            now=datetime(2026, 9, 11, 14, 28, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(reason)

    def test_future_reentry_plan_cannot_reopen_closed_contract(self):
        from entry_controls import existing_contract_entry_block_reason

        reason = existing_contract_entry_block_reason(
            [
                {
                    "status": "closed",
                    "ticker": "SPY",
                    "strike": 757.0,
                    "option_type": "PUT",
                    "expiration": "2026-09-10",
                    "closed_at": "2026-09-09T16:36:25+00:00",
                }
            ],
            {
                "ticker": "SPY",
                "strike": 757.0,
                "option_type": "PUT",
                "expiration": "09/10/26",
            },
            "Will re-enter SPY 757P if the setup returns",
            now=datetime(2026, 9, 9, 19, 11, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(reason)

    def test_trusted_source_can_reopen_closed_contract_for_distinct_alert(self):
        from entry_controls import existing_contract_entry_block_reason

        reason = existing_contract_entry_block_reason(
            [
                {
                    "status": "closed",
                    "alert_id": "first-spy-757p-alert",
                    "ticker": "SPY",
                    "strike": 757.0,
                    "option_type": "PUT",
                    "expiration": "2026-09-18",
                    "closed_at": "2026-09-18T13:56:00+00:00",
                }
            ],
            {
                "ticker": "SPY",
                "strike": 757.0,
                "option_type": "PUT",
                "expiration": "09/18/26",
            },
            "$SPY $757 PUTS EXPIRATION 9/18/2026 $.55 Entry range, $.48 AVG",
            alert_id="second-spy-757p-alert",
            allow_fresh_entry_after_close=True,
            now=datetime(2026, 9, 18, 14, 4, tzinfo=timezone.utc),
        )

        self.assertIsNone(reason)

    def test_trusted_source_does_not_reopen_same_alert_id(self):
        from entry_controls import existing_contract_entry_block_reason

        reason = existing_contract_entry_block_reason(
            [
                {
                    "status": "closed",
                    "alert_id": "same-alert",
                    "ticker": "SPY",
                    "strike": 757.0,
                    "option_type": "PUT",
                    "expiration": "2026-09-18",
                    "closed_at": "2026-09-18T13:56:00+00:00",
                }
            ],
            {
                "ticker": "SPY",
                "strike": 757.0,
                "option_type": "PUT",
                "expiration": "09/18/26",
            },
            "$SPY $757 PUTS EXPIRATION 9/18/2026 $.55 Entry range, $.48 AVG",
            alert_id="same-alert",
            allow_fresh_entry_after_close=True,
            now=datetime(2026, 9, 18, 14, 4, tzinfo=timezone.utc),
        )

        self.assertIsNotNone(reason)


if __name__ == "__main__":
    unittest.main()
