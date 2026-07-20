import asyncio
import pathlib
import sys
import types
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class ContextualContractResolutionTests(unittest.TestCase):
    def test_contextual_readd_requires_position_resolution(self):
        from contextual_contract_resolution import parse_contextual_entry

        parsed = parse_contextual_entry(
            "RE-ADDING THE INITIAL QQQ $726C ALERT @ $.35"
        )

        self.assertEqual(parsed["ticker"], "QQQ")
        self.assertEqual(parsed["strike"], 726.0)
        self.assertEqual(parsed["option_type"], "CALL")
        self.assertEqual(parsed["entry_price"], 0.35)
        self.assertIsNone(parsed["expiration"])
        self.assertTrue(parsed["_requires_position_context"])

    def test_unique_position_expiration_is_applied_before_trade(self):
        from discord_ingestion import DiscordIngestionDeps, handle_discord_message

        alerts = []
        trades = []

        async def process_trade(alert, parsed):
            trades.append((alert, parsed))

        async def resolve_context(parsed, *, include_simulated):
            self.assertFalse(include_simulated)
            return {"expiration": "7/24/2026", "position_ids": ["pos-1"]}

        deps = DiscordIngestionDeps(
            load_settings=lambda: {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "source_overrides": {},
            },
            insert_alert=alerts.append,
            process_trade=process_trade,
            update_status=lambda *_: None,
            resolve_contract_context=resolve_context,
        )
        message = types.SimpleNamespace(
            content="RE-ADDING THE INITIAL QQQ $726C ALERT @ $.35",
            embeds=[],
            author=types.SimpleNamespace(id="analyst"),
            channel=types.SimpleNamespace(id="123", name="alerts"),
            created_at=None,
        )

        result = asyncio.run(
            handle_discord_message(
                message,
                channel_ids=["123"],
                deps=deps,
                bot_user=types.SimpleNamespace(id="bot"),
            )
        )

        self.assertTrue(result.alert_inserted)
        self.assertTrue(result.trade_requested)
        self.assertEqual(alerts[0].expiration, "7/24/2026")
        self.assertEqual(trades[0][1]["expiration"], "7/24/2026")
        self.assertEqual(trades[0][1]["_context_position_ids"], ["pos-1"])

    def test_ambiguous_position_context_blocks_before_persistence(self):
        from discord_ingestion import DiscordIngestionDeps, handle_discord_message

        alerts = []
        trades = []

        deps = DiscordIngestionDeps(
            load_settings=lambda: {
                "auto_trading_enabled": True,
                "simulation_mode": False,
                "source_overrides": {},
            },
            insert_alert=alerts.append,
            process_trade=lambda alert, parsed: trades.append((alert, parsed)),
            update_status=lambda *_: None,
            resolve_contract_context=lambda parsed, **_: {
                "reason": "matching open positions span multiple expirations"
            },
        )
        message = types.SimpleNamespace(
            content="RE-ADDING THE INITIAL QQQ $726C ALERT @ $.35",
            embeds=[],
            author=types.SimpleNamespace(id="analyst"),
            channel=types.SimpleNamespace(id="123", name="alerts"),
            created_at=None,
        )

        result = asyncio.run(
            handle_discord_message(
                message,
                channel_ids=["123"],
                deps=deps,
                bot_user=types.SimpleNamespace(id="bot"),
            )
        )

        self.assertIn("multiple expirations", result.skip_reason)
        self.assertFalse(result.alert_inserted)
        self.assertFalse(result.trade_requested)
        self.assertEqual(alerts, [])
        self.assertEqual(trades, [])

    def test_watch_notice_does_not_use_context_fallback(self):
        from contextual_contract_resolution import parse_contextual_entry

        self.assertIsNone(
            parse_contextual_entry(
                "RE-ADDING QQQ $726C ON WATCH - ENTRY NOT VALID YET @ $.35"
            )
        )


if __name__ == "__main__":
    unittest.main()
