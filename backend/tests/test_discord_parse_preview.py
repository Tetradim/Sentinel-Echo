import asyncio
import pathlib
import sys
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakePreviewDb:
    def __init__(self, settings, patterns=None):
        self.settings = settings
        self.patterns = patterns or {}
        self.updated_settings = []
        self.updated_patterns = []

    async def get_settings(self):
        return dict(self.settings)

    async def update_settings(self, update):
        self.updated_settings.append(update)
        self.settings.update(update)
        return dict(self.settings)

    async def get_discord_patterns(self):
        return dict(self.patterns)

    async def update_discord_patterns(self, patterns):
        self.updated_patterns.append(patterns)


class FakeRawPreviewDb(FakePreviewDb):
    async def get_settings(self):
        return self.settings


class DiscordParsePreviewTests(unittest.TestCase):
    def test_parse_preview_returns_policy_and_quantity_without_saving(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "default_quantity": 4,
                "max_position_size": 1000.0,
                "source_overrides": {
                    "alerts": {
                        "risk_multiplier": 0.5,
                        "max_premium": 2.0,
                        "max_contracts": 1,
                    }
                },
            }
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "BTO SPY 500C 6/21 @ 1.25",
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertIsNone(result["skip_reason"])
        self.assertTrue(result["execution_preview"]["would_request_trade"])
        self.assertEqual(result["execution_preview"]["quantity"], 1)
        self.assertEqual(result["execution_preview"]["uncapped_quantity"], 2)
        self.assertEqual(result["execution_preview"]["estimated_premium_cost"], 125.0)
        self.assertEqual(result["execution_preview"]["uncapped_premium_cost"], 250.0)
        self.assertEqual(result["execution_preview"]["max_contracts"], 1)
        self.assertIn(
            "Source max_contracts capped quantity from 2 to 1.",
            result["warnings"],
        )
        self.assertEqual(fake_db.updated_settings, [])
        self.assertEqual(fake_db.updated_patterns, [])

    def test_parse_preview_treats_malformed_settings_as_operational_defaults(self):
        from routes import discord as discord_route

        fake_db = FakeRawPreviewDb("settings")
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "BTO SPY 500C 6/21 @ 1.25",
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertTrue(result["execution_preview"]["would_request_trade"])
        self.assertIsNone(result["execution_preview"]["reason"])
        self.assertTrue(result["execution_preview"]["auto_trading_enabled"])
        self.assertNotIn("Auto trading is disabled; preview will not request a trade.", result["warnings"])

    def test_parse_preview_reports_malformed_source_overrides_without_crashing(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "default_quantity": 1,
                "max_position_size": 1000.0,
                "source_overrides": "alerts",
            }
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "BTO SPY 500C 6/21 @ 1.25",
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertEqual(result["skip_reason"], "invalid source config: source overrides must be an object")
        self.assertFalse(result["execution_preview"]["would_request_trade"])
        self.assertIn(
            "Source config is invalid: source overrides must be an object.",
            result["warnings"],
        )

    def test_parse_preview_does_not_break_entry_price_label_patterns(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": True,
                "default_quantity": 1,
                "max_position_size": 1000.0,
                "source_overrides": {},
            },
            patterns={
                "buy_patterns": ["ENTRY"],
                "case_sensitive": False,
            },
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "$SPY\n$740 CALLS\n EXPIRATION 6/12/2026\n$1.1 Entry",
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertEqual(result["parsed"]["strike"], 740.0)
        self.assertEqual(result["parsed"]["entry_price"], 1.10)
        self.assertTrue(result["execution_preview"]["would_request_trade"])

    def test_parse_preview_ignores_discord_fill_update_that_replays_entry_text(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "default_quantity": 10,
                "max_position_size": 100000.0,
                "source_overrides": {},
            },
            patterns={
                "buy_patterns": ["ENTRY"],
                "case_sensitive": False,
            },
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": (
                        "$QQQ $716 CALLS EXPIRATION 8/26/2026 $.5 Entry @everyone "
                        "$715/$716 upper band extension pt , last alert for today ,\n"
                        "JUST FILLED IN @ $.47 AVG FILL @everyone"
                    ),
                    "source_key": "alerts",
                }
            )
        )

        self.assertIsNone(result["parsed"])
        self.assertEqual(result["skip_reason"], "ignored by alert pattern")
        self.assertFalse(result["execution_preview"]["would_request_trade"])
        self.assertEqual(result["parser_metadata"]["matched_pattern_type"], "followup_update")

    def test_parse_preview_ignores_discord_profit_update_that_replays_entry_text(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "default_quantity": 10,
                "max_position_size": 100000.0,
                "source_overrides": {},
            },
            patterns={
                "buy_patterns": ["ENTRY"],
                "case_sensitive": False,
            },
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": (
                        "$QQQ $716 CALLS EXPIRATION 8/26/2026 $.5 Entry, $.47 AVG "
                        "@everyone $715/$716 upper band extension pt , last alert for today , "
                        "(edited) Wednesday, August 26, 2026 at 2:15 PM\n"
                        "$.54 HERE ON QQQ CALLS UP +17% @everyone"
                    ),
                    "source_key": "alerts",
                }
            )
        )

        self.assertIsNone(result["parsed"])
        self.assertEqual(result["skip_reason"], "ignored by alert pattern")
        self.assertFalse(result["execution_preview"]["would_request_trade"])
        self.assertEqual(result["parser_metadata"]["matched_pattern_type"], "followup_update")

    def test_parse_preview_treats_appended_break_even_stop_as_contract_exit(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "default_quantity": 10,
                "max_position_size": 100000.0,
                "source_overrides": {},
            },
            patterns={
                "buy_patterns": ["ENTRY"],
                "case_sensitive": False,
            },
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": (
                        "$SPY $760 PUTS EXPIRATION 9/1/2026 $.18 Entry high risk lotto\n"
                        "Solid attempt at a selloff. Runners hit b/e SL @everyone"
                    ),
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["alert_type"], "sell")
        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertEqual(result["parsed"]["strike"], 760.0)
        self.assertEqual(result["parsed"]["option_type"], "PUT")
        self.assertEqual(result["parsed"]["expiration"], "09/01/26")
        self.assertIsNone(result["parsed"].get("entry_price"))
        self.assertEqual(result["parsed"]["sell_percentage"], 100.0)
        self.assertTrue(result["execution_preview"]["would_request_trade"])
        self.assertEqual(result["parser_metadata"]["matched_pattern_type"], "followup_exit")

    def test_parse_preview_uses_latest_fill_for_appended_dca(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "default_quantity": 10,
                "max_position_size": 100000.0,
                "source_overrides": {},
            },
            patterns={
                "buy_patterns": ["ENTRY"],
                "average_down_patterns": ["DCA"],
                "case_sensitive": False,
            },
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": (
                        "$SPY $758 PUTS EXPIRATION 9/1/2026 $.32 Entry, $.27 AVG\n"
                        "DCA'd down to $.27 AVG Filled adds at $.2"
                    ),
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["alert_type"], "average_down")
        self.assertEqual(result["parsed"]["entry_price"], 0.20)
        self.assertEqual(result["parser_metadata"]["matched_pattern_type"], "followup_average_down")

    def test_parse_preview_uses_readding_fill_not_target_average(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "default_quantity": 10,
                "max_position_size": 100000.0,
                "source_overrides": {},
            },
            patterns={
                "buy_patterns": ["ENTRY"],
                "average_down_patterns": ["ADDING"],
                "case_sensitive": False,
            },
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": (
                        "$SPY $768 CALLS EXPIRATION 9/11/2026 $.5 Entry\n"
                        "RE-ADDING SPY $768 CALLS $.35 FILL "
                        "(looking for a $.28-$.3 final AVG)"
                    ),
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["alert_type"], "average_down")
        self.assertEqual(result["parsed"]["entry_price"], 0.35)
        self.assertEqual(result["parser_metadata"]["matched_pattern_type"], "followup_average_down")

    def test_parse_preview_ignores_future_dca_followup(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "default_quantity": 10,
                "max_position_size": 100000.0,
                "source_overrides": {},
            },
            patterns={
                "buy_patterns": ["ENTRY"],
                "average_down_patterns": ["DCA"],
                "case_sensitive": False,
            },
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": (
                        "$SPCX $150 CALLS EXPIRATION 9/4/2026 $1.2 Entry\n"
                        "b/e HERE ON SPCX & STILL LOOKING FOR DOWNSIDE TO DCA"
                    ),
                    "source_key": "alerts",
                }
            )
        )

        self.assertIsNone(result["parsed"])
        self.assertEqual(result["skip_reason"], "ignored by alert pattern")
        self.assertEqual(result["parser_metadata"]["matched_pattern_type"], "followup_update")

    def test_parse_preview_treats_sold_runners_at_break_even_as_exit(self):
        from routes import discord as discord_route

        discord_route.set_db(FakePreviewDb({"auto_trading_enabled": True}))

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": (
                        "$SPY $768 PUTS EXPIRATION 8/28/2026 $.35 Entry\n"
                        "SOLD RUNNERS AT B/E @everyone"
                    ),
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["alert_type"], "sell")
        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertEqual(result["parsed"]["strike"], 768.0)
        self.assertEqual(result["parsed"]["sell_percentage"], 100.0)
        self.assertEqual(result["parser_metadata"]["matched_pattern_type"], "followup_exit")

    def test_parse_preview_treats_in_cash_followup_as_exit(self):
        from routes import discord as discord_route

        discord_route.set_db(FakePreviewDb({"auto_trading_enabled": True}))

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": (
                        "$SPY $763 PUTS EXPIRATION 8/26/2026 $.65 Entry\n"
                        "Markets are back into chop. For now staying hands off, & in cash."
                    ),
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["alert_type"], "sell")
        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertEqual(result["parsed"]["strike"], 763.0)
        self.assertEqual(result["parsed"]["sell_percentage"], 100.0)
        self.assertEqual(result["parser_metadata"]["matched_pattern_type"], "followup_exit")

    def test_parse_preview_reports_source_policy_skip(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "default_quantity": 4,
                "max_position_size": 1000.0,
                "source_overrides": {
                    "alerts": {
                        "ticker_blocklist": ["TSLA"],
                    }
                },
            }
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "BTO TSLA 250C 6/21 @ 1.25",
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["ticker"], "TSLA")
        self.assertEqual(result["skip_reason"], "ticker TSLA blocked for source")
        self.assertFalse(result["execution_preview"]["would_request_trade"])
        self.assertEqual(result["execution_preview"]["reason"], "ticker TSLA blocked for source")

    def test_parse_preview_rejects_missing_text(self):
        from fastapi import HTTPException
        from routes import discord as discord_route

        discord_route.set_db(FakePreviewDb({}))

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(discord_route.preview_discord_alert({"raw_text": "  "}))

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("raw_text is required", caught.exception.detail)

    def test_parse_preview_uses_configured_sell_pattern(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": True,
                "default_quantity": 4,
                "max_position_size": 1000.0,
                "source_overrides": {},
            },
            patterns={
                "sell_patterns": ["SCALE"],
                "ignore_patterns": [],
                "case_sensitive": False,
            },
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "SCALE 50% SPY 500C 6/21 @ 1.40",
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["alert_type"], "sell")
        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertEqual(result["parsed"]["sell_percentage"], 50.0)
        self.assertEqual(result["execution_preview"]["quantity"], None)
        self.assertEqual(result["execution_preview"]["matched_pattern"], "SCALE")
        self.assertEqual(result["parser_metadata"]["confidence"], "high")
        self.assertEqual(result["confidence"], "high")

    def test_parse_preview_keeps_trade_echo_closed_summary_as_sell(self):
        from models import DiscordAlertPatterns
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "default_quantity": 1,
                "max_position_size": 1000.0,
                "source_overrides": {},
            },
            patterns=DiscordAlertPatterns().model_dump(),
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": (
                        "Trade by steel5477\n"
                        "Closed 60 AAPL 307.5P 07/02 @ $1.01 "
                        "(Entry: $0.79) | Gain: +27.8%"
                    ),
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["alert_type"], "sell")
        self.assertEqual(result["parsed"]["ticker"], "AAPL")
        self.assertEqual(result["parsed"]["expiration"], "07/02/26")
        self.assertEqual(result["parsed"]["entry_price"], 1.01)
        self.assertTrue(result["execution_preview"]["would_request_trade"])

    def test_parse_preview_keeps_trade_echo_partial_summary_as_trim(self):
        from models import DiscordAlertPatterns
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "default_quantity": 1,
                "max_position_size": 1000.0,
                "source_overrides": {},
            },
            patterns=DiscordAlertPatterns().model_dump(),
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": (
                        "Trade by steel5477\n"
                        "Partially Closed 60 AAPL 307.5P 07/02 @ $0.92 "
                        "(Entry: $0.79) | Gain: +16.5%"
                    ),
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["alert_type"], "trim")
        self.assertEqual(result["parsed"]["ticker"], "AAPL")
        self.assertEqual(result["parsed"]["expiration"], "07/02/26")
        self.assertEqual(result["parsed"]["entry_price"], 0.92)

    def test_parse_preview_configured_action_pattern_does_not_replace_ticker(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": True,
                "source_overrides": {},
            },
            patterns={
                "sell_patterns": ["SCALE"],
                "case_sensitive": False,
            },
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "SCALE SPY 500C 6/21 @ 1.40",
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["alert_type"], "sell")
        self.assertEqual(result["parsed"]["ticker"], "SPY")

    def test_parse_preview_applies_configured_ticker_pattern(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": True,
                "default_quantity": 1,
                "max_position_size": 1000.0,
                "source_overrides": {},
            },
            patterns={
                "ticker_pattern": r"ALERT:([A-Z]{1,6})\b",
            },
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "BTO ALERT:SPY 500C 6/21 @ 1.25",
                    "source_key": "alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["ticker"], "SPY")
        self.assertTrue(result["parser_metadata"]["ticker_pattern_applied"])
        self.assertEqual(
            result["parser_metadata"]["matched_ticker_pattern"],
            r"ALERT:([A-Z]{1,6})\b",
        )
        self.assertEqual(result["parser_metadata"]["ticker_pattern_source"], "settings")

    def test_parse_preview_applies_request_pattern_overrides_without_saving(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": True,
                "default_quantity": 4,
                "max_position_size": 1000.0,
                "source_overrides": {},
            },
            patterns={
                "sell_patterns": ["SCALE"],
                "ignore_patterns": [],
                "case_sensitive": False,
            },
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "LIGHTENUP 50% SPY 500C 6/21 @ 1.40",
                    "source_key": "alerts",
                    "pattern_overrides": {
                        "sell_patterns": ["LIGHTENUP"],
                    },
                }
            )
        )

        self.assertEqual(result["parsed"]["alert_type"], "sell")
        self.assertEqual(result["execution_preview"]["matched_pattern"], "LIGHTENUP")
        self.assertEqual(result["parser_metadata"]["pattern_source"], "request")
        self.assertEqual(fake_db.updated_patterns, [])

    def test_parse_preview_uses_configured_ignore_pattern(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": True,
                "source_overrides": {},
            },
            patterns={
                "ignore_patterns": ["WATCH"],
                "case_sensitive": False,
            },
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "WATCH BTO SPY 500C 6/21 @ 1.25",
                    "source_key": "alerts",
                }
            )
        )

        self.assertIsNone(result["parsed"])
        self.assertEqual(result["skip_reason"], "ignored by alert pattern")
        self.assertFalse(result["execution_preview"]["would_insert_alert"])
        self.assertEqual(result["execution_preview"]["matched_pattern"], "WATCH")

    def test_explicit_entry_precedes_hypothetical_word_in_trailing_commentary(self):
        from routes import discord as discord_route

        raw_text = (
            "$SPY $765 CALLS EXPIRATION 9/2/2026 $.55 Entry @everyone "
            "dealer exposure favors calls; if we see upside follow through and break out it may be explosive"
        )
        patterns = {
            "buy_patterns": ["ENTRY"],
            "sell_patterns": ["OUT"],
            "ignore_patterns": ["IF"],
            "case_sensitive": False,
        }

        parsed, metadata = discord_route._parse_alert_for_preview(raw_text, patterns)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["alert_type"], "buy")
        self.assertEqual(parsed["ticker"], "SPY")
        self.assertEqual(metadata["matched_pattern_type"], "buy_patterns")
        self.assertFalse(metadata["ignored"])

        ignored, ignored_metadata = discord_route._parse_alert_for_preview(
            "IF $SPY $765 CALLS EXPIRATION 9/2/2026 $.55 Entry",
            patterns,
        )
        self.assertIsNone(ignored)
        self.assertEqual(ignored_metadata["matched_pattern_type"], "ignore_patterns")

    def test_parse_preview_rejects_invalid_pattern_overrides(self):
        from fastapi import HTTPException
        from routes import discord as discord_route

        discord_route.set_db(FakePreviewDb({}))

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                discord_route.preview_discord_alert(
                    {
                        "raw_text": "BTO SPY 500C 6/21 @ 1.25",
                        "pattern_overrides": {
                            "buy_patterns": [""],
                        },
                    }
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("Pattern cannot be empty", caught.exception.detail)

    def test_parse_preview_rejects_invalid_ticker_pattern_override(self):
        from fastapi import HTTPException
        from routes import discord as discord_route

        discord_route.set_db(FakePreviewDb({}))

        with self.assertRaises(HTTPException) as caught:
            asyncio.run(
                discord_route.preview_discord_alert(
                    {
                        "raw_text": "BTO SPY 500C 6/21 @ 1.25",
                        "pattern_overrides": {
                            "ticker_pattern": r"\$((A+)+)\b",
                        },
                    }
                )
            )

        self.assertEqual(caught.exception.status_code, 400)
        self.assertIn("unsafe nested quantifier", caught.exception.detail)

    def test_parse_preview_warns_when_buy_action_is_assumed(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": True,
                "default_quantity": 1,
                "max_position_size": 1000.0,
                "source_overrides": {},
            }
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "SPY 500C 6/21 @ 1.25",
                    "source_key": "unknown-alerts",
                }
            )
        )

        self.assertEqual(result["parsed"]["alert_type"], "buy")
        self.assertEqual(result["parser_metadata"]["confidence"], "low")
        self.assertEqual(result["confidence"], "low")
        self.assertIn(
            "No explicit action keyword matched; parser assumed buy.",
            result["warnings"],
        )
        self.assertIn(
            "No source override matched; default source policy used.",
            result["warnings"],
        )

    def test_parse_preview_warns_when_auto_trading_disabled(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": False,
                "simulation_mode": True,
                "source_overrides": {},
            }
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "BTO SPY 500C 6/21 @ 1.25",
                    "source_key": "alerts",
                }
            )
        )

        self.assertFalse(result["execution_preview"]["would_request_trade"])
        self.assertEqual(result["execution_preview"]["reason"], "auto trading disabled")
        self.assertEqual(result["parser_metadata"]["confidence"], "medium")
        self.assertIn(
            "Auto trading is disabled; preview will not request a trade.",
            result["warnings"],
        )

    def test_parse_preview_parses_string_trading_flags_without_truthy_fallback(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": "false",
                "simulation_mode": "false",
                "default_quantity": 1,
                "max_position_size": 1000.0,
                "source_overrides": {},
            }
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "BTO SPY 500C 6/21 @ 1.25",
                    "source_key": "alerts",
                }
            )
        )

        self.assertFalse(result["execution_preview"]["would_request_trade"])
        self.assertEqual(result["execution_preview"]["reason"], "auto trading disabled")
        self.assertFalse(result["execution_preview"]["auto_trading_enabled"])

    def test_parse_preview_ignores_removed_manual_confirmation_requirement(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "source_overrides": {
                    "alerts": {
                        "require_manual_confirm": True,
                    }
                },
            }
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "BTO SPY 500C 6/21 @ 1.25",
                    "source_key": "alerts",
                }
            )
        )

        self.assertTrue(result["execution_preview"]["would_insert_alert"])
        self.assertTrue(result["execution_preview"]["would_request_trade"])
        self.assertIsNone(result["execution_preview"]["reason"])
        self.assertNotIn("Source requires manual confirmation before trade execution.", result["warnings"])

    def test_parse_preview_ignores_removed_paper_shadow_setting(self):
        from routes import discord as discord_route

        fake_db = FakePreviewDb(
            {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "source_overrides": {
                    "alerts": {
                        "paper_shadow": True,
                    }
                },
            }
        )
        discord_route.set_db(fake_db)

        result = asyncio.run(
            discord_route.preview_discord_alert(
                {
                    "raw_text": "BTO SPY 500C 6/21 @ 1.25",
                    "source_key": "alerts",
                }
            )
        )

        self.assertTrue(result["execution_preview"]["would_request_trade"])
        self.assertNotIn("would_create_paper_shadow", result["execution_preview"])
        self.assertNotIn("Paper-shadow recording is enabled for this source.", result["warnings"])


if __name__ == "__main__":
    unittest.main()
