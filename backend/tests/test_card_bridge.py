import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_chrome_bridge
from test_structured_alert_cards import ENTRY, EDIT, TRIM, CLOSE


class CardDb(test_chrome_bridge.FakeChromeBridgeDb):
    async def get_alert_by_id(self, alert_id):
        return next((alert for alert in self.alerts if alert['id'] == alert_id), None)

    async def insert_card_alert(self, alert):
        if await self.get_alert_by_id(alert['id']):
            return False
        await self.insert_alert(alert)
        return True


class CardBridgeTests(unittest.TestCase):
    setUp = test_chrome_bridge.ChromeBridgeRouteTests.setUp
    tearDown = test_chrome_bridge.ChromeBridgeRouteTests.tearDown

    def test_embed_entry_edit_and_separate_update_have_one_buy_and_one_trim(self):
        from routes import discord as route
        db = CardDb({'auto_trading_enabled': True, 'active_broker': 'alpaca', 'source_overrides': {'aq': {}}})
        route.set_db(db)
        requests = []

        async def process(alert, parsed):
            requests.append(parsed)
            if parsed['alert_type'] == 'buy':
                db.positions.append({'id': 'pos', 'alert_id': alert.id, 'status': 'open', 'ticker': 'NVDA',
                    'strike': 230, 'option_type': 'CALL', 'expiration': '09/03/26', 'quantity': 4,
                    'remaining_quantity': 4, 'entry_price': .85, 'current_price': 1.19, 'broker': 'alpaca'})

        async def send(text, message_id):
            payload = route.ChromeBridgeMessage(event_id=message_id, channel_id='aq', author_name='AQTrades',
                content='@AQ Trades', embeds=[route.ChromeBridgeEmbed(description=text)],
                timestampIso=datetime.now(timezone.utc).isoformat())
            return await route.ingest_chrome_bridge_message(payload, SimpleNamespace(client=SimpleNamespace(host='127.0.0.1')))

        async def run():
            self.assertTrue((await send(ENTRY, 'entry'))['trade_requested'])
            self.assertTrue((await send(EDIT, 'entry'))['trade_requested'])
            duplicate = await send(TRIM, 'trim-update')
            self.assertEqual(duplicate['skip_reason'], 'duplicate card action')
            self.assertFalse(duplicate['trade_requested'])
            comment = await send(TRIM.replace('Trimmed 3/4', 'Comment'), 'comment')
            self.assertFalse(comment['trade_requested'])
            self.assertIn('comment', comment['skip_reason'])
            close = await send(CLOSE.replace('QQQ $712 Puts', 'NVDA $230 Calls'), 'close')
            self.assertTrue(close['trade_requested'])
            self.assertEqual(close['parsed']['alert_type'], 'close')
            self.assertEqual([p['alert_type'] for p in requests], ['buy', 'trim', 'close'])

        with patch.dict('sys.modules', {'server': SimpleNamespace(process_trade=process)}):
            asyncio.run(run())

    def test_comments_and_invalid_cards_cannot_reach_context_buy_or_sell_fallback(self):
        from routes import discord as route
        route.set_db(CardDb({'auto_trading_enabled': True, 'source_overrides': {'aq': {}}}))

        async def run():
            for index, text in enumerate((ENTRY.replace('Sep 03, 2026', 'unknown'), TRIM.replace('Trimmed 3/4', 'Comment'))):
                payload = route.ChromeBridgeMessage(event_id=str(index), channel_id='aq', content=text)
                result = await route.ingest_chrome_bridge_message(payload, SimpleNamespace(client=SimpleNamespace(host='127.0.0.1')))
                self.assertFalse(result['trade_requested'])
                self.assertTrue(result['parser_metadata']['card_recognized'])

        with patch.object(route, '_infer_single_channel_position_sell', side_effect=AssertionError('unexpected sell inference')), \
             patch.object(route, '_infer_recent_channel_contract_buy', side_effect=AssertionError('unexpected buy inference')):
            asyncio.run(run())
