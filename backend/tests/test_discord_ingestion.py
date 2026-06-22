import asyncio
import pathlib
import sys
import types
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeDeps:
    def __init__(self, settings):
        self.settings = settings
        self.alerts = []
        self.trades = []
        self.status_updates = []

    def load_settings(self):
        return self.settings

    def insert_alert(self, alert):
        self.alerts.append(alert)

    async def process_trade(self, alert, parsed):
        self.trades.append((alert, parsed))

    def update_status(self, key, value):
        self.status_updates.append((key, value))


def message(content, *, channel_id="123", channel_name="alerts"):
    return types.SimpleNamespace(
        content=content,
        embeds=[],
        author=types.SimpleNamespace(id="analyst"),
        channel=types.SimpleNamespace(id=channel_id, name=channel_name),
    )


class DiscordIngestionTests(unittest.TestCase):
    def test_parsed_alert_is_inserted_and_traded_when_settings_enable_autotrading(self):
        from discord_ingestion import handle_discord_message

        deps = FakeDeps({"auto_trading_enabled": True, "source_overrides": {}})

        result = asyncio.run(
            handle_discord_message(
                message("BTO SPY 500C 6/21 @ 1.25"),
                channel_ids=["123"],
                deps=deps,
                bot_user=types.SimpleNamespace(id="bot"),
            )
        )

        self.assertTrue(result.alert_inserted)
        self.assertTrue(result.trade_requested)
        self.assertEqual(deps.alerts[0].ticker, "SPY")
        self.assertEqual(deps.trades[0][1]["ticker"], "SPY")

    def test_disabled_source_skips_before_insert_or_trade(self):
        from discord_ingestion import handle_discord_message

        deps = FakeDeps(
            {
                "auto_trading_enabled": True,
                "source_overrides": {"alerts": {"enabled": False}},
            }
        )

        result = asyncio.run(
            handle_discord_message(
                message("BTO SPY 500C 6/21 @ 1.25"),
                channel_ids=["123"],
                deps=deps,
                bot_user=types.SimpleNamespace(id="bot"),
            )
        )

        self.assertEqual(result.skip_reason, "source disabled")
        self.assertEqual(deps.alerts, [])
        self.assertEqual(deps.trades, [])

    def test_persisted_settings_not_bot_status_control_trading_request(self):
        from discord_ingestion import handle_discord_message

        deps = FakeDeps({"auto_trading_enabled": False, "source_overrides": {}})

        result = asyncio.run(
            handle_discord_message(
                message("BTO SPY 500C 6/21 @ 1.25"),
                channel_ids=["123"],
                deps=deps,
                bot_user=types.SimpleNamespace(id="bot"),
            )
        )

        self.assertTrue(result.alert_inserted)
        self.assertFalse(result.trade_requested)
        self.assertEqual(deps.trades, [])

    def test_string_false_auto_trading_does_not_request_trade(self):
        from discord_ingestion import handle_discord_message

        deps = FakeDeps({"auto_trading_enabled": "false", "source_overrides": {}})

        result = asyncio.run(
            handle_discord_message(
                message("BTO SPY 500C 6/21 @ 1.25"),
                channel_ids=["123"],
                deps=deps,
                bot_user=types.SimpleNamespace(id="bot"),
            )
        )

        self.assertTrue(result.alert_inserted)
        self.assertFalse(result.trade_requested)
        self.assertEqual(deps.trades, [])

    def test_manual_confirmation_source_inserts_alert_without_trade_request(self):
        from discord_ingestion import handle_discord_message

        deps = FakeDeps(
            {
                "auto_trading_enabled": True,
                "source_overrides": {"alerts": {"require_manual_confirm": True}},
            }
        )

        result = asyncio.run(
            handle_discord_message(
                message("BTO SPY 500C 6/21 @ 1.25"),
                channel_ids=["123"],
                deps=deps,
                bot_user=types.SimpleNamespace(id="bot"),
            )
        )

        self.assertTrue(result.alert_inserted)
        self.assertFalse(result.trade_requested)
        self.assertEqual(result.skip_reason, "manual confirmation required")
        self.assertEqual(deps.alerts[0].ticker, "SPY")
        self.assertEqual(deps.trades, [])


if __name__ == "__main__":
    unittest.main()
