import asyncio
import pathlib
import sys
import types
import unittest


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class FakeDeps:
    def __init__(self, settings, sr_pre_entry_gate=None):
        self.settings = settings
        self.alerts = []
        self.trades = []
        self.gate_calls = []
        self.status_updates = []
        self.sr_pre_entry_gate = sr_pre_entry_gate

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


class DiscordIngestionSrWatchTests(unittest.TestCase):
    def test_enabled_sr_watch_records_source_config_on_parsed_alert(self):
        from discord_ingestion import handle_discord_message

        deps = FakeDeps(
            {
                "auto_trading_enabled": False,
                "source_overrides": {"alerts": {"sr_watch_enabled": True}},
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
        self.assertTrue(result.parsed["_source_config"]["sr_watch_enabled"])
        self.assertTrue(result.parsed["_source_config"]["sr_watch_replace_orb"])

    def test_disabled_sr_watch_leaves_ingestion_path_unchanged(self):
        from discord_ingestion import handle_discord_message

        async def gate(alert, parsed, source_config):
            deps.gate_calls.append((alert, parsed, source_config))
            return {"allowed": False, "reason": "should not run"}

        deps = FakeDeps({"auto_trading_enabled": True, "source_overrides": {}}, sr_pre_entry_gate=gate)

        result = asyncio.run(
            handle_discord_message(
                message("BTO SPY 500C 6/21 @ 1.25"),
                channel_ids=["123"],
                deps=deps,
                bot_user=types.SimpleNamespace(id="bot"),
            )
        )

        self.assertTrue(result.trade_requested)
        self.assertEqual(len(deps.trades), 1)
        self.assertEqual(deps.gate_calls, [])

    def test_injected_sr_watch_gate_can_block_entry_before_trade_processing(self):
        from discord_ingestion import handle_discord_message

        async def gate(alert, parsed, source_config):
            deps.gate_calls.append((alert, parsed, source_config))
            return {"allowed": False, "reason": "support break against call"}

        deps = FakeDeps(
            {
                "auto_trading_enabled": True,
                "source_overrides": {
                    "alerts": {
                        "sr_watch_enabled": True,
                        "sr_watch_strict_gating": True,
                    }
                },
            },
            sr_pre_entry_gate=gate,
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
        self.assertEqual(result.skip_reason, "sr watch blocked: support break against call")
        self.assertEqual(deps.trades, [])
        self.assertEqual(len(deps.gate_calls), 1)


if __name__ == "__main__":
    unittest.main()
