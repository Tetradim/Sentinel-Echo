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


def message(content, *, channel_id="123", channel_name="alerts", author_name="MikeInvesting"):
    return types.SimpleNamespace(
        content=content,
        embeds=[],
        author=types.SimpleNamespace(
            id="analyst",
            name=author_name,
            display_name=author_name,
            global_name=author_name,
        ),
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
        self.assertEqual(result.trade_request_reason, "auto trading enabled")
        self.assertEqual(result.alert_id, deps.alerts[0].id)
        self.assertEqual(deps.alerts[0].ticker, "SPY")
        self.assertEqual(deps.trades[0][1]["ticker"], "SPY")

    def test_missing_auto_trading_setting_defaults_to_trade_request(self):
        from discord_ingestion import handle_discord_message

        deps = FakeDeps({"source_overrides": {}})

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
        self.assertEqual(result.trade_request_reason, "auto trading enabled")
        self.assertEqual(deps.trades[0][1]["ticker"], "SPY")

    def test_disabled_source_records_rejection_with_source_and_author(self):
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
        self.assertTrue(result.alert_inserted)
        self.assertFalse(result.trade_requested)
        self.assertEqual(result.trade_request_reason, "source disabled")
        self.assertEqual(deps.alerts[0].ticker, "SPY")
        self.assertEqual(deps.alerts[0].channel_id, "123")
        self.assertEqual(deps.alerts[0].channel_name, "alerts")
        self.assertEqual(deps.alerts[0].author_id, "analyst")
        self.assertEqual(deps.alerts[0].author_name, "MikeInvesting")
        self.assertEqual(deps.alerts[0].source_name, "alerts")
        self.assertEqual(deps.alerts[0].skip_reason, "source disabled")
        self.assertEqual(deps.alerts[0].trade_result, "skipped: source disabled")
        self.assertTrue(deps.alerts[0].processed)
        self.assertFalse(deps.alerts[0].trade_executed)
        self.assertEqual(deps.trades, [])

    def test_sell_alert_listener_can_be_disabled_without_losing_partial_exit_context(self):
        from discord_ingestion import handle_discord_message

        deps = FakeDeps(
            {
                "auto_trading_enabled": True,
                "sell_alert_listening_enabled": False,
                "source_overrides": {},
            }
        )

        result = asyncio.run(
            handle_discord_message(
                message("SOLD 80% SPY $738 CALLS HERE AT $.59 FILL 80%"),
                channel_ids=["123"],
                deps=deps,
                bot_user=types.SimpleNamespace(id="bot"),
            )
        )

        self.assertEqual(result.skip_reason, "sell alert listening disabled")
        self.assertTrue(result.alert_inserted)
        self.assertFalse(result.trade_requested)
        self.assertEqual(result.trade_request_reason, "sell alert listening disabled")
        self.assertEqual(deps.trades, [])
        self.assertEqual(deps.alerts[0].alert_type, "sell")
        self.assertEqual(deps.alerts[0].sell_percentage, 80.0)
        self.assertEqual(deps.alerts[0].entry_price, 0.59)
        self.assertEqual(deps.alerts[0].exit_trigger, "sell_alert")
        self.assertEqual(deps.alerts[0].skip_reason, "sell alert listening disabled")
        self.assertEqual(deps.alerts[0].trade_result, "skipped: sell alert listening disabled")

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
        self.assertEqual(result.trade_request_reason, "auto trading disabled")
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
        self.assertEqual(result.trade_request_reason, "auto trading disabled")
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
        self.assertEqual(result.trade_request_reason, "manual confirmation required")
        self.assertEqual(deps.alerts[0].ticker, "SPY")
        self.assertEqual(deps.trades, [])


if __name__ == "__main__":
    unittest.main()
