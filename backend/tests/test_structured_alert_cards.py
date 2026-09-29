import unittest

from structured_alert_cards import parse_card


ENTRY = """Alerted By | AQTrades
NVDA $230 Calls
Exp
Sep 03, 2026
Entry
$0.85
@NPAS_Andres Not Financial Advice 09/03/2026 08:38 AM CST"""
EDIT = ENTRY + "\nTRIMS\nTRIMMED 3/4 - $1.19 | 40.0%\nTrimmed 3/4"
TRIM = """Position Update - NVDA $230 Calls
Exit @ $1.19 | 40.0% ($+0.34)
Type
Trimmed 3/4
Time
09/03/2026 08:39 AM CST"""
CLOSE = """Position Update - QQQ $712 Puts
Final Exit @ $0.60
Weighted Avg Exit: $0.60
35.5% total on position ($-0.33)
Type
Full Close
Time
08/31/2026 09:36 AM CST"""
MONEY_GLITCH_ENTRY = """Money GlitchAPP2:00 PM

**SPY $775C** 09-21 · Austin Filled **74× @ $0.34** (take, drift +0.0%, alert $0.34) Stop-only · stop **−20%** ($0.27) · target: **manual** (you)

` exit    price    qty       pnl
-------------------------------
(no trims yet)
-------------------------------
open   74x · stop $0.27
peak   +0%   ·   net +0.00`"""

MONEY_GLITCH_TRIM = MONEY_GLITCH_ENTRY.replace(
    "(no trims yet)\n-------------------------------\nopen   74x · stop $0.27\npeak   +0%   ·   net +0.00",
    "trim   $  0.37    37x   +107.30  +9%\n"
    "-------------------------------\nopen   37x · stop $0.34 (BE)\npeak   +10%   ·   net +107.30",
)

MONEY_GLITCH_CLOSE = MONEY_GLITCH_TRIM.replace(
    "-------------------------------\nopen   37x · stop $0.34 (BE)\npeak   +10%   ·   net +107.30",
    "close  $  0.42    37x   +292.30 +24%\n"
    "-------------------------------\npeak   +26%   ·   net +399.60",
)

MONEY_GLITCH_STOP = MONEY_GLITCH_TRIM.replace(
    "-------------------------------\nopen   37x · stop $0.34 (BE)\npeak   +10%   ·   net +107.30",
    "stop   $  0.34    37x     -3.70  +0%\n"
    "-------------------------------\npeak   +10%   ·   net +103.60",
)


class CardParserTests(unittest.TestCase):
    def test_entry_uses_labelled_expiration(self):
        card = parse_card(ENTRY)
        self.assertTrue(card.recognized)
        self.assertEqual(card.parsed['alert_type'], 'buy')
        self.assertEqual(card.parsed['expiration'], '09/03/26')
        self.assertEqual(card.parsed['entry_price'], 0.85)

    def test_trim_and_edit_are_exits_not_buys_or_dates(self):
        for text in (EDIT, TRIM):
            with self.subTest(text=text):
                parsed = parse_card(text).parsed
                self.assertEqual(parsed['alert_type'], 'trim')
                self.assertEqual(parsed['ticker'], 'NVDA')
                self.assertEqual(parsed['sell_percentage'], 75)
                self.assertIsNone(parsed['entry_price'])
                self.assertEqual(parsed['_card']['reported_exit_price'], 1.19)
        self.assertIsNone(parse_card(TRIM).parsed['expiration'])

    def test_full_close_does_not_buy_time(self):
        parsed = parse_card(CLOSE).parsed
        self.assertEqual(parsed['alert_type'], 'close')
        self.assertEqual(parsed['ticker'], 'QQQ')
        self.assertEqual(parsed['sell_percentage'], 100)
        self.assertIsNone(parsed['expiration'])

    def test_comment_is_never_an_order_even_with_trade_words(self):
        card = parse_card(TRIM.replace('Trimmed 3/4', 'Comment').replace('Exit @ $1.19', 'SELL at $1.19'))
        self.assertTrue(card.recognized)
        self.assertIsNone(card.parsed)
        self.assertIn('comment', card.reason)

    def test_invalid_or_missing_expiration_does_not_use_footer(self):
        for value in ('', '02/30/2026', '3/4', 'tomorrow'):
            self.assertIsNone(parse_card(ENTRY.replace('Sep 03, 2026', value)).parsed)

    def test_supported_expiration_formats(self):
        for value in ('September 03, 2026', '2026-09-03', '09/03/26'):
            self.assertEqual(parse_card(ENTRY.replace('Sep 03, 2026', value)).parsed['expiration'], '09/03/26')

    def test_labelled_cards_without_provider_brand_are_supported(self):
        text = 'NVDA $230 Calls\nExpiration: 2026-09-03\nEntry Price: $0.85'
        self.assertEqual(parse_card(text).parsed['alert_type'], 'buy')

    def test_final_exit_on_entry_card_supersedes_previous_trim_history(self):
        parsed = parse_card(EDIT + '\nFull Close\nFinal Exit @ $1.50').parsed
        self.assertEqual(parsed['alert_type'], 'close')
        self.assertEqual(parsed['_card']['reported_exit_price'], 1.50)

    def test_ambiguous_cards_and_invalid_trim_are_not_guessed(self):
        for text in (ENTRY + '\nSPY $640 Puts', TRIM.replace('3/4', '4/3'), TRIM.replace('3/4', 'some')):
            self.assertIsNone(parse_card(text).parsed)

    def test_generic_alert_is_left_to_existing_parser(self):
        self.assertFalse(parse_card('BTO SPY 640C 09/03/26 @ 1.20').recognized)

    def test_money_glitch_filled_card_uses_headline_entry_not_results_table(self):
        card = parse_card(MONEY_GLITCH_ENTRY)

        self.assertTrue(card.recognized)
        self.assertEqual(card.parsed['alert_type'], 'buy')
        self.assertEqual(card.parsed['ticker'], 'SPY')
        self.assertEqual(card.parsed['strike'], 775)
        self.assertEqual(card.parsed['option_type'], 'CALL')
        self.assertEqual(card.parsed['expiration'], '09/21')
        self.assertEqual(card.parsed['entry_price'], 0.34)
        self.assertIsNone(card.parsed['sell_percentage'])
        self.assertEqual(card.parsed['_card']['schema'], 'filled_position_v1')
        self.assertEqual(card.parsed['_card']['reported_quantity'], 74)
        self.assertEqual(card.parsed['_card']['reported_stop_percent'], -20)
        self.assertEqual(card.parsed['_card']['reported_stop_price'], 0.27)
        self.assertEqual(card.parsed['_card']['target_mode'], 'manual')

    def test_money_glitch_edit_emits_incremental_trim_and_break_even_stop(self):
        parsed = parse_card(MONEY_GLITCH_TRIM).parsed

        self.assertEqual(parsed['alert_type'], 'trim')
        self.assertEqual(parsed['sell_percentage'], 50)
        self.assertEqual(parsed['exit_trigger'], 'source_card_trim')
        self.assertEqual(parsed['_card']['reported_exit_price'], 0.37)
        self.assertEqual(parsed['_card']['reported_exit_quantity'], 37)
        self.assertEqual(parsed['_card']['reported_open_quantity'], 37)
        self.assertEqual(parsed['_card']['reported_stop_price'], 0.34)
        self.assertTrue(parsed['_card']['reported_break_even_stop'])

    def test_money_glitch_close_and_stop_edits_are_full_exits(self):
        close = parse_card(MONEY_GLITCH_CLOSE).parsed
        stop = parse_card(MONEY_GLITCH_STOP).parsed

        self.assertEqual(close['alert_type'], 'close')
        self.assertEqual(close['sell_percentage'], 100)
        self.assertEqual(close['exit_trigger'], 'source_card_close')
        self.assertEqual(close['_card']['reported_exit_price'], 0.42)
        self.assertEqual(stop['alert_type'], 'close')
        self.assertEqual(stop['sell_percentage'], 100)
        self.assertEqual(stop['exit_trigger'], 'source_card_stop')
        self.assertEqual(stop['_card']['reported_exit_price'], 0.34)

    def test_malformed_filled_card_is_blocked_instead_of_falling_through(self):
        card = parse_card('SPY $775C 09-21 · Austin Filled 74× at market')

        self.assertTrue(card.recognized)
        self.assertIsNone(card.parsed)
        self.assertIn('price', card.reason)

    def test_generic_parser_and_preview_use_card_dispatch(self):
        from utils import parse_alert
        from routes.discord import _parse_alert_for_preview
        self.assertEqual(parse_alert(EDIT)['alert_type'], 'trim')
        parsed, metadata = _parse_alert_for_preview(CLOSE, {'buy_patterns': ['EXIT']})
        self.assertEqual(parsed['alert_type'], 'close')
        self.assertEqual(metadata['pattern_source'], 'structured_card')
        parsed, metadata = _parse_alert_for_preview(TRIM.replace('Trimmed 3/4', 'Comment'), {})
        self.assertIsNone(parsed)
        self.assertTrue(metadata['ignored'])

        parsed, metadata = _parse_alert_for_preview(MONEY_GLITCH_ENTRY, {})
        self.assertEqual(parsed['alert_type'], 'buy')
        self.assertEqual(parsed['ticker'], 'SPY')
        self.assertEqual(metadata['pattern_source'], 'structured_card')
