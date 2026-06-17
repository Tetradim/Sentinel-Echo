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
                        "paper_only": True,
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
        self.assertTrue(result["source_config"]["paper_only"])
        self.assertTrue(result["execution_preview"]["would_request_trade"])
        self.assertTrue(result["execution_preview"]["simulation_mode"])
        self.assertEqual(result["execution_preview"]["quantity"], 1)
        self.assertEqual(result["execution_preview"]["uncapped_quantity"], 2)
        self.assertEqual(result["execution_preview"]["max_contracts"], 1)
        self.assertIn(
            "Source max_contracts capped quantity from 2 to 1.",
            result["warnings"],
        )
        self.assertEqual(fake_db.updated_settings, [])
        self.assertEqual(fake_db.updated_patterns, [])

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

    def test_parse_preview_reports_manual_confirmation_requirement(self):
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
        self.assertFalse(result["execution_preview"]["would_request_trade"])
        self.assertEqual(result["execution_preview"]["reason"], "manual confirmation required")
        self.assertIn(
            "Source requires manual confirmation before trade execution.",
            result["warnings"],
        )

    def test_parse_preview_reports_paper_shadow_for_live_source(self):
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
        self.assertTrue(result["execution_preview"]["would_create_paper_shadow"])
        self.assertIn(
            "Paper-shadow recording is enabled for this source.",
            result["warnings"],
        )


if __name__ == "__main__":
    unittest.main()
