import importlib
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class AlertParsingTests(unittest.TestCase):
    def test_conversational_exit_words_are_not_invented_as_tickers(self):
        from utils import parse_alert

        self.assertIsNone(parse_alert("I'm going to trim slowly now"))
        self.assertIsNone(parse_alert("Sell for +20% rule here"))
        self.assertIsNone(parse_alert("SOLD FULL POSITION & TOOK THE LOSS."))

    def test_explicit_dollar_ticker_still_allows_word_like_symbols(self):
        from utils import parse_alert

        parsed = parse_alert("SELL $NOW 900C 9/18 @ 2.10")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["ticker"], "NOW")

    def test_advanced_analyst_formats_import_and_include_regional_formats(self):
        module = importlib.import_module("analyst_formats")

        self.assertIn("chinabull", module.ANALYST_FORMATS)
        self.assertIn("korean", module.ANALYST_FORMATS)

    def test_common_bto_without_cash_tag_parses_contract_and_price(self):
        from utils import parse_alert

        parsed = parse_alert("BTO SPY 500C 6/21 @ 1.25")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "buy")
        self.assertEqual(parsed["ticker"], "SPY")
        self.assertEqual(parsed["strike"], 500.0)
        self.assertEqual(parsed["option_type"], "CALL")
        self.assertEqual(parsed["expiration"], "6/21")
        self.assertEqual(parsed["entry_price"], 1.25)

    def test_buy_alert_without_price_is_rejected(self):
        from utils import parse_alert

        self.assertIsNone(parse_alert("BTO SPY 500C 6/21"))

    def test_analyst_dollar_price_before_entry_parses(self):
        from utils import parse_alert

        parsed = parse_alert(
            "$SPY\n"
            "$740 CALLS\n"
            " EXPIRATION 6/12/2026\n"
            "$1.1 Entry\n"
            "@everyone"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "buy")
        self.assertEqual(parsed["ticker"], "SPY")
        self.assertEqual(parsed["strike"], 740.0)
        self.assertEqual(parsed["option_type"], "CALL")
        self.assertEqual(parsed["expiration"], "6/12/2026")
        self.assertEqual(parsed["entry_price"], 1.10)

    def test_copied_alert_buy_uses_entry_price_before_target_price(self):
        from utils import parse_alert

        parsed = parse_alert(
            "[copied-alert]\n"
            "Source: https://discord.com/channels/850715868539519026/872226993557606440\n"
            "From: [ 10:12 AM ]\n"
            "\n"
            "$SPY $749 CALLS EXPIRATION 7/1/2026 $.28 Entry @everyone "
            "extension #3 play. Break above $748 & $750 is next, "
            "these will be trading at $.45+ on premiums value if hit"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "buy")
        self.assertEqual(parsed["ticker"], "SPY")
        self.assertEqual(parsed["strike"], 749.0)
        self.assertEqual(parsed["option_type"], "CALL")
        self.assertEqual(parsed["expiration"], "7/1/2026")
        self.assertEqual(parsed["entry_price"], 0.28)

    def test_sell_alert_parses_percentage_contract_and_price(self):
        from utils import parse_alert

        parsed = parse_alert("SELL 50% SPY 500C 6/21 @ 1.40")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "sell")
        self.assertEqual(parsed["ticker"], "SPY")
        self.assertEqual(parsed["strike"], 500.0)
        self.assertEqual(parsed["option_type"], "CALL")
        self.assertEqual(parsed["expiration"], "6/21")
        self.assertEqual(parsed["sell_percentage"], 50.0)
        self.assertEqual(parsed["entry_price"], 1.40)

    def test_sold_alert_parses_partial_fill_percentage_contract_and_fill(self):
        from utils import parse_alert

        parsed = parse_alert("SOLD 80% SPY $738 CALLS HERE AT $.59 FILL 80%")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "sell")
        self.assertEqual(parsed["ticker"], "SPY")
        self.assertEqual(parsed["strike"], 738.0)
        self.assertEqual(parsed["option_type"], "CALL")
        self.assertIsNone(parsed["expiration"])
        self.assertEqual(parsed["sell_percentage"], 80.0)
        self.assertEqual(parsed["entry_price"], 0.59)

    def test_copied_alert_sold_partial_fill_parses_after_header(self):
        from utils import parse_alert

        parsed = parse_alert(
            "[copied-alert]\n"
            "Source: https://discord.com/channels/850715868539519026/1102404702857072691\n"
            "From: MikeInvesting - — 10:18 AM\n"
            "\n"
            "SOLD 70% SPY $750 CALLS HERE AT $.41 FILL @everyone"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "sell")
        self.assertEqual(parsed["ticker"], "SPY")
        self.assertEqual(parsed["strike"], 750.0)
        self.assertEqual(parsed["option_type"], "CALL")
        self.assertEqual(parsed["sell_percentage"], 70.0)
        self.assertEqual(parsed["entry_price"], 0.41)

    def test_sell_alert_parses_fractional_at_price_without_leading_zero(self):
        from utils import parse_alert

        parsed = parse_alert("STC QQQ 735C 6/25/2026 @ .55")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "sell")
        self.assertEqual(parsed["ticker"], "QQQ")
        self.assertEqual(parsed["strike"], 735.0)
        self.assertEqual(parsed["option_type"], "CALL")
        self.assertEqual(parsed["expiration"], "6/25/2026")
        self.assertEqual(parsed["sell_percentage"], 100.0)
        self.assertEqual(parsed["entry_price"], 0.55)

    def test_trade_echo_open_summary_parses_as_buy(self):
        from utils import parse_alert

        parsed = parse_alert(
            "Trade by chapsyboobs\n"
            "Opened 500 QQQ 709C 07/02 @ $1.35 (Actual Cost: $1.35)"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "buy")
        self.assertEqual(parsed["ticker"], "QQQ")
        self.assertEqual(parsed["strike"], 709.0)
        self.assertEqual(parsed["option_type"], "CALL")
        self.assertEqual(parsed["expiration"], "07/02")
        self.assertEqual(parsed["entry_price"], 1.35)

    def test_trade_echo_closed_summary_parses_as_sell_not_buy(self):
        from utils import parse_alert

        parsed = parse_alert(
            "Trade by steel5477\n"
            "Closed 60 AAPL 307.5P 07/02 @ $1.01 (Entry: $0.79) | Gain: +27.8%\n"
            "Trade Summary\n"
            "Total Closed: 520/500\n"
            "Average Close Price: $1.01"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "close")
        self.assertEqual(parsed["ticker"], "AAPL")
        self.assertEqual(parsed["strike"], 307.5)
        self.assertEqual(parsed["option_type"], "PUT")
        self.assertEqual(parsed["expiration"], "07/02")
        self.assertEqual(parsed["entry_price"], 1.01)

    def test_trade_echo_partial_closed_summary_parses_as_trim(self):
        from utils import parse_alert

        parsed = parse_alert(
            "Trade by steel5477\n"
            "Partially Closed 60 AAPL 307.5P 07/02 @ $0.92 (Entry: $0.79) | Gain: +16.5%\n"
            "Partial Close\n"
            "Closed: 60/500 (12%)\n"
            "Remaining: 40 @ $0.79"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "trim")
        self.assertEqual(parsed["ticker"], "AAPL")
        self.assertEqual(parsed["entry_price"], 0.92)

    def test_no_year_expiration_normalizes_for_order_execution(self):
        from datetime import date
        from utils import normalize_expiration_for_order

        self.assertEqual(
            normalize_expiration_for_order("7/2", today=date(2026, 7, 2)),
            "07/02/26",
        )
        self.assertEqual(
            normalize_expiration_for_order("07/02", today=date(2026, 7, 1)),
            "07/02/26",
        )

    def test_market_marker_is_preserved_for_unpriced_exit(self):
        from utils import parse_alert

        parsed = parse_alert("STC 500 qqq 709c 7/2 @M")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "sell")
        self.assertEqual(parsed["ticker"], "QQQ")
        self.assertIsNone(parsed["entry_price"])
        self.assertTrue(parsed["market_price"])

    def test_action_ticker_wins_over_trailing_moneyness_commentary(self):
        from utils import parse_alert

        parsed = parse_alert("BTO 1 AAPL 307.5C 7/2 @ 0.60 OTM call allowed")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "buy")
        self.assertEqual(parsed["ticker"], "AAPL")
        self.assertEqual(parsed["strike"], 307.5)
        self.assertEqual(parsed["option_type"], "CALL")
        self.assertEqual(parsed["entry_price"], 0.60)

    def test_keyword_substrings_do_not_trigger_exit_alerts(self):
        from utils import parse_alert

        for message in (
            "TRIMMER SPY 500C 6/21 @ 1.40",
            "WITHOUT SPY 500C 6/21 @ 1.40",
        ):
            parsed = parse_alert(message)

            self.assertIsNotNone(parsed)
            self.assertEqual(parsed["alert_type"], "buy")

    def test_sell_percentage_does_not_treat_calls_as_all_out(self):
        from utils import parse_alert

        parsed = parse_alert("SELL 50% SPY 500 CALLS 6/21 @ 1.40")

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "sell")
        self.assertEqual(parsed["sell_percentage"], 50.0)

    def test_market_commentary_does_not_parse_as_sell_alert(self):
        from utils import parse_alert

        messages = (
            (
                "Stock market futures are gapping higher after crude sold off. "
                "On watch: SPY $753C 0DTE QQQ $739C 0DTE"
            ),
            (
                "Seeing significant amounts of calls being loaded + puts being sold here by whales. "
                "Will RE-ENTER QQQ $743C 0DTE & DCA UPON THE SETUP"
            ),
            "SOLD THOSE. 90% POSITION SECURED.",
            "Sold at $.66 fills for that +20% gain.",
            "STOPPED OUT OF FINAL $758C at B/E",
        )

        for message in messages:
            with self.subTest(message=message):
                self.assertIsNone(parse_alert(message))

    def test_edited_entry_with_dca_language_is_average_down_not_fresh_buy(self):
        from utils import parse_alert

        parsed = parse_alert(
            "$SPY $758 PUTS EXPIRATION 9/1/2026 $.32 Entry, $.27 AVG "
            "seeking an extension into gap fill region below.\n"
            "DCA'd down to $.27 AVG Filled adds at $.2"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "average_down")
        self.assertEqual(parsed["ticker"], "SPY")
        self.assertEqual(parsed["strike"], 758.0)
        self.assertEqual(parsed["option_type"], "PUT")

    def test_entry_with_future_dca_guidance_remains_a_buy(self):
        from utils import parse_alert

        for message in (
            "$SPY $758 PUTS EXPIRATION 9/1/2026 $.32 Entry leave DCA room and be patient",
            "$QQQ $716 CALLS EXPIRATION 8/26/2026 $.65 Entry add on pullbacks",
            "$QQQ $716 CALLS EXPIRATION 8/26/2026 $.65 Entry adding to setup",
            "$TSLA $385 CALLS EXPIRATION 9/9/2026 $.6 Entry DCA & buy on backtests",
            (
                "$SPY $757 PUTS EXPIRATION 9/10/2026 $.92 Entry\n"
                "Swinging into tomorrow. No DCA. No adds. Simply riding original position."
            ),
        ):
            with self.subTest(message=message):
                parsed = parse_alert(message)

                self.assertIsNotNone(parsed)
                self.assertEqual(parsed["alert_type"], "buy")

    def test_negated_average_down_language_is_not_actionable(self):
        from utils import is_actionable_average_down_alert

        for message in (
            "No DCA. No adds.",
            "Do not DCA or add here.",
            "Without adding to this position.",
        ):
            with self.subTest(message=message):
                self.assertFalse(is_actionable_average_down_alert(message))

    def test_future_dca_followup_is_not_an_average_down_signal(self):
        from utils import parse_alert

        parsed = parse_alert(
            "$SPCX $150 CALLS EXPIRATION 9/4/2026 $1.2 Entry\n"
            "b/e HERE ON SPCX & STILL LOOKING FOR DOWNSIDE TO DCA"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "buy")

    def test_trim_update_with_ticker_and_option_side_parses_broad_exit(self):
        from utils import parse_alert

        parsed = parse_alert(
            "$.5 HERE ON SPY PUTS\n"
            "UP +20%\n"
            "- trim out initials/sell majority"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "trim")
        self.assertEqual(parsed["ticker"], "SPY")
        self.assertIsNone(parsed["strike"])
        self.assertEqual(parsed["option_type"], "PUT")
        self.assertIsNone(parsed["expiration"])
        self.assertEqual(parsed["entry_price"], 0.50)
        self.assertEqual(parsed["sell_percentage"], 75.0)


if __name__ == "__main__":
    unittest.main()
