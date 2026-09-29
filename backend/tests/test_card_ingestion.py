import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from card_ingestion import prepare_card
from database.abstraction import SQLiteDatabase
from discord_ingestion import DiscordIngestionDeps, handle_discord_message
from structured_alert_cards import parse_card
from test_structured_alert_cards import (
    ENTRY,
    EDIT,
    TRIM,
    CLOSE,
    MONEY_GLITCH_ENTRY,
    MONEY_GLITCH_TRIM,
    MONEY_GLITCH_CLOSE,
)


class CardIngestionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'test.db')
        self.db = SQLiteDatabase(self.path)
        self.settings = {'auto_trading_enabled': True, 'active_broker': 'alpaca'}
        self.requests = []

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def ingest(self, text, message_id='entry', channel_id='aq'):
        async def process(alert, parsed):
            self.requests.append((alert, parsed))
        return await handle_discord_message(
            SimpleNamespace(id=message_id, content=text, embeds=[], channel=SimpleNamespace(id=channel_id, name=channel_id), author=SimpleNamespace(id='analyst')),
            channel_ids=[],
            deps=DiscordIngestionDeps(load_settings=lambda: self.settings,
                insert_alert=lambda alert: self.db.insert_alert(alert.model_dump(mode='json')),
                process_trade=process, update_status=lambda *args: None, card_database=self.db),
        )

    async def position(self, alert_id, position_id='position', expiry='09/03/26'):
        await self.db.insert_position({'id': position_id, 'alert_id': alert_id, 'ticker': 'NVDA', 'strike': 230,
            'option_type': 'CALL', 'expiration': expiry, 'broker': 'alpaca', 'quantity': 4, 'remaining_quantity': 4,
            'entry_price': 0.85, 'current_price': 1.19, 'status': 'open'})

    async def test_edit_and_update_trim_once_across_restart(self):
        entry = await self.ingest(ENTRY)
        await self.position(entry.alert_id)
        edit = await self.ingest(EDIT)
        self.assertTrue(edit.trade_requested)
        self.assertEqual(edit.parsed['expiration'], '09/03/26')
        self.db = SQLiteDatabase(self.path)
        duplicate = await self.ingest(TRIM, 'separate-update')
        self.assertEqual(duplicate.skip_reason, 'duplicate card action')
        self.assertEqual(len(self.requests), 2)
        self.assertEqual(self.requests[1][1]['sell_percentage'], 75)

    async def test_standalone_update_then_edit_also_trim_once(self):
        entry = await self.ingest(ENTRY)
        await self.position(entry.alert_id)
        await self.ingest(TRIM, 'separate-update')
        result = await self.ingest(EDIT)
        self.assertEqual(result.skip_reason, 'duplicate card action')
        self.assertEqual(len(self.requests), 2)

    async def test_old_edited_entry_without_position_never_buys(self):
        result = await self.ingest(EDIT)
        self.assertFalse(result.trade_requested)
        self.assertIn('no matching source position', result.skip_reason)
        self.assertEqual(self.requests, [])

    async def test_missing_expiry_does_not_cross_channel_or_guess_among_expiries(self):
        entry = await self.ingest(ENTRY)
        await self.position(entry.alert_id)
        result = await self.ingest(TRIM, 'trim', 'other')
        self.assertIn('no matching source position', result.skip_reason)
        await self.position(entry.alert_id, 'other-expiry', '09/04/26')
        result = await self.ingest(TRIM, 'trim')
        self.assertIn('multiple source positions', result.skip_reason)
        self.assertEqual(len(self.requests), 1)

    async def test_new_entry_cycle_does_not_inherit_previous_trim_dedupe(self):
        entry = await self.ingest(ENTRY)
        await self.position(entry.alert_id)
        await self.ingest(TRIM, 'trim1')
        await self.db.update_position('position', {'$set': {'status': 'closed', 'remaining_quantity': 0}})
        entry2 = await self.ingest(ENTRY, 'second-entry')
        await self.position(entry2.alert_id, 'position2')
        result = await self.ingest(TRIM, 'trim2')
        self.assertTrue(result.trade_requested)
        self.assertEqual(len(self.requests), 4)

    async def test_concurrent_claims_persist_one_action_and_disabled_does_not_claim(self):
        self.settings['auto_trading_enabled'] = False
        self.assertFalse((await self.ingest(ENTRY)).trade_requested)
        self.settings['auto_trading_enabled'] = True
        results = await asyncio.gather(self.ingest(ENTRY), self.ingest(ENTRY))
        self.assertEqual(sum(result.trade_requested for result in results), 1)
        self.assertEqual(len(self.requests), 1)

    async def test_comment_never_calls_trade_even_when_it_says_sell(self):
        result = await self.ingest(TRIM.replace('Trimmed 3/4', 'Comment'))
        self.assertFalse(result.trade_requested)

    async def test_full_close_resolves_position_and_uses_execution_quote(self):
        entry = await self.ingest(ENTRY)
        await self.position(entry.alert_id)
        result = await self.ingest(CLOSE.replace('QQQ $712 Puts', 'NVDA $230 Calls'), 'close')
        self.assertTrue(result.trade_requested)
        self.assertEqual(result.parsed['sell_percentage'], 100)
        self.assertIsNone(result.parsed['entry_price'])
        self.assertEqual(result.parsed['_card']['position_id'], 'position')

    async def test_card_exit_plans_only_target_resolved_position(self):
        from trade_lifecycle import build_exit_plans
        entry = await self.ingest(ENTRY)
        await self.position(entry.alert_id)
        parsed, reason = await prepare_card(self.db, parse_card(TRIM).parsed, 'aq', 'trim', self.settings)
        self.assertEqual(reason, '')
        positions = await self.db.get_positions('open')
        positions.append({**positions[0], 'id': 'unrelated-source-position'})
        plans = build_exit_plans(positions, parsed)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]['quantity'], 3)

    async def test_money_glitch_trim_updates_source_stop_even_when_trim_execution_is_disabled(self):
        self.settings.update({
            'trim_alert_listening_enabled': True,
            'source_overrides': {
                'homebrew': {'trim_alert_listening_enabled': False},
            },
        })
        entry = await self.ingest(MONEY_GLITCH_ENTRY, 'homebrew-card', 'homebrew')
        await self.db.insert_position({
            'id': 'homebrew-position',
            'alert_id': entry.alert_id,
            'ticker': 'SPY',
            'strike': 775,
            'option_type': 'CALL',
            'expiration': '09/21/26',
            'broker': 'alpaca',
            'quantity': 2,
            'remaining_quantity': 2,
            'entry_price': 0.34,
            'current_price': 0.37,
            'status': 'open',
        })

        result = await self.ingest(MONEY_GLITCH_TRIM, 'homebrew-card', 'homebrew')
        position = await self.db.get_position_by_id('homebrew-position')

        self.assertFalse(result.trade_requested)
        self.assertEqual(result.skip_reason, 'trim alert listening disabled for source')
        self.assertEqual(position['source_reported_stop_price'], 0.34)
        self.assertTrue(position['source_reported_break_even_stop'])

    async def test_money_glitch_close_edit_targets_existing_card_position(self):
        self.settings['source_overrides'] = {'homebrew': {'trim_alert_listening_enabled': False}}
        entry = await self.ingest(MONEY_GLITCH_ENTRY, 'homebrew-card', 'homebrew')
        await self.db.insert_position({
            'id': 'homebrew-position',
            'alert_id': entry.alert_id,
            'ticker': 'SPY',
            'strike': 775,
            'option_type': 'CALL',
            'expiration': '09/21/26',
            'broker': 'alpaca',
            'quantity': 2,
            'remaining_quantity': 2,
            'entry_price': 0.34,
            'current_price': 0.42,
            'status': 'open',
        })

        result = await self.ingest(MONEY_GLITCH_CLOSE, 'homebrew-card', 'homebrew')

        self.assertTrue(result.trade_requested)
        self.assertEqual(result.parsed['alert_type'], 'close')
        self.assertEqual(result.parsed['exit_trigger'], 'source_card_close')
        self.assertEqual(result.parsed['_card']['position_id'], 'homebrew-position')
