import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class AlertReplayHardeningTests(unittest.TestCase):
    def test_structured_entry_wins_over_narrative_sell_instruction(self):
        from utils import parse_alert

        parsed = parse_alert(
            "$SPY\n$742 CALLS\nEXPIRATION 6/29/2026\n"
            "$.5 Entry, $.4 AVG\n"
            "Rejection of this level then sell immediately."
        )

        self.assertEqual(parsed["alert_type"], "buy")
        self.assertEqual(parsed["ticker"], "SPY")
        self.assertEqual(parsed["entry_price"], 0.5)

    def test_structured_entry_wins_over_avg_down_risk_note(self):
        from utils import parse_alert

        parsed = parse_alert(
            "$SPY\n$748 CALLS\nEXPIRATION 7/1/2026\n"
            "$.95 Entry\nSize one half and leave one half to DCA/AVG DOWN."
        )

        self.assertEqual(parsed["alert_type"], "buy")
        self.assertEqual(parsed["entry_price"], 0.95)

    def test_price_before_entry_label_is_supported(self):
        from utils import parse_alert

        parsed = parse_alert(
            "$QQQ\n$713 PUTS\nEXPIRATION 7/13/2026\n"
            "$1.5 Entry, $1.15 AVG"
        )

        self.assertEqual(parsed["alert_type"], "buy")
        self.assertEqual(parsed["entry_price"], 1.5)

    def test_shorthand_premium_does_not_capture_later_price_target(self):
        from utils import parse_alert

        parsed = parse_alert(
            "ENTERING SPY $753P 0DTE FOR A RE-ENTRY AT A $.2 FILL\n"
            "$753.8-$754 PT",
            created_at="06/15/2026 12:57 PM",
        )

        self.assertEqual(parsed["entry_price"], 0.2)
        self.assertEqual(parsed["expiration"], "6/15/2026")

    def test_zero_dte_uses_discord_message_timestamp(self):
        from utils import parse_alert

        parsed = parse_alert(
            "RE-ADDING SPY $750C 0DTE EXTREME RISK LOTTO\n"
            "$.15 ENTRY FILL",
            created_at="07/17/2026 10:40 AM",
        )

        self.assertEqual(parsed["alert_type"], "buy")
        self.assertEqual(parsed["expiration"], "7/17/2026")
        self.assertEqual(parsed["entry_price"], 0.15)

    def test_watch_notice_is_not_an_entry(self):
        from utils import parse_alert

        self.assertIsNone(
            parse_alert(
                "QQQ $716C 0DTE ON WATCH NOTICE\n"
                "ENTRY NOT VALID YET\n$.30 possible fill",
                created_at="07/14/2026 9:00 AM",
            )
        )

    def test_market_commentary_sold_off_is_not_an_exit(self):
        from utils import parse_alert

        self.assertIsNone(
            parse_alert("The market sold off after the open and recovered into VWAP.")
        )

    def test_plain_trimming_now_is_not_service_now_exit(self):
        from utils import parse_alert

        self.assertIsNone(parse_alert("TRIMMING NOW 🚨🚨"))

    def test_valid_now_contract_exit_is_preserved(self):
        from utils import parse_alert

        parsed = parse_alert("SOLD 90% NOW $110 CALLS POSITION AT $3.2 FILL")

        self.assertEqual(parsed["alert_type"], "sell")
        self.assertEqual(parsed["ticker"], "NOW")
        self.assertEqual(parsed["strike"], 110.0)
        self.assertEqual(parsed["option_type"], "CALL")
        self.assertEqual(parsed["sell_percentage"], 90.0)
        self.assertEqual(parsed["entry_price"], 3.2)

    def test_parenthetical_sold_all_exit_is_detected(self):
        from utils import parse_alert

        parsed = parse_alert(
            "Failed extension into upper zone. "
            "(Sold all SPY $750C 0DTE's)",
            created_at="07/17/2026 10:02 AM",
        )

        self.assertEqual(parsed["alert_type"], "sell")
        self.assertEqual(parsed["ticker"], "SPY")
        self.assertEqual(parsed["expiration"], "7/17/2026")
        self.assertEqual(parsed["sell_percentage"], 100.0)


if __name__ == "__main__":
    unittest.main()
