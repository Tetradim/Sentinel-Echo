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


if __name__ == "__main__":
    unittest.main()
