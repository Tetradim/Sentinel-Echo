import importlib
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class AlertParsingTests(unittest.TestCase):
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
