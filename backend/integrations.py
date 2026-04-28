"""
External Integrations
- TradingView webhooks
- Slack notifications
- Telegram bot
"""
import os
import logging
import hmac
import hashlib
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

# Configuration
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL', '')
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN', '')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
TRADINGVIEW_WEBHOOK_SECRET = os.environ.get('TRADINGVIEW_WEBHOOK_SECRET', '')


# ========================
# TradingView Integration
# ========================

class TradingViewWebhook:
    """TradingView webhook handler"""
    
    @staticmethod
    def verify_signature(payload: str, signature: str) -> bool:
        """Verify TradingView webhook signature"""
        if not TRADINGVIEW_WEBHOOK_SECRET:
            return True
        
        expected = hmac.new(
            TRADINGVIEW_WEBHOOK_SECRET.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected, signature)
    
    @staticmethod
    def parse_alert(alert_data: Dict) -> Dict:
        """Parse TradingView alert into trade format
        
        Expected TradingView alert format:
        {
            "ticker": "AAPL",
            "action": "buy|sell",
            "price": 150.00,
            "quantity": 100,
            "strategy": "my_strategy"
        }
        """
        ticker = alert_data.get('ticker', '')
        action = alert_data.get('action', '').lower()
        
        return {
            'ticker': ticker.upper() if ticker else '',
            'option_type': 'CALL' if action == 'buy' else 'PUT',
            'strike': alert_data.get('price', 0),
            'quantity': alert_data.get('quantity', 10),
            'alert_type': 'BTO' if action == 'buy' else 'STO',
            'source': 'tradingview',
            'strategy': alert_data.get('strategy', 'default'),
            'raw_data': alert_data
        }


# ========================
# Slack Integration
# ========================

class SlackNotifier:
    """Slack notifications"""
    
    def __init__(self):
        self.webhook_url = SLACK_WEBHOOK_URL
        self.bot_token = SLACK_BOT_TOKEN
        self.session = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def send_webhook(self, message: str, blocks: Optional[List] = None):
        """Send simple webhook message"""
        if not self.webhook_url:
            logger.warning("Slack webhook not configured")
            return False
        
        payload = {"text": message}
        if blocks:
            payload["blocks"] = blocks
        
        try:
            session = await self._get_session()
            async with session.post(self.webhook_url, json=payload) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Slack webhook error: {e}")
            return False
    
    async def send_trade_alert(self, trade: Dict):
        """Send trade notification"""
        ticker = trade.get('ticker', '')
        pnl = trade.get('realized_pnl', 0) or 0
        pnl_emoji = ":green_circle:" if pnl >= 0 else ":red_circle:"
        
        message = f"{pnl_emoji} *{trade.get('alert_type', 'TRADE')}*: {ticker} {trade.get('strike')}{trade.get('option_type', '')}"
        if pnl != 0:
            message += f"\nP&L: ${pnl:,.2f}"
        
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "Trade Executed"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Ticker:*\n{ticker}"},
                    {"type": "mrkdwn", "text": f"*Action:*\n{trade.get('alert_type', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Strike:*\n{trade.get('strike')}"},
                    {"type": "mrkdwn", "text": f"*Type:*\n{trade.get('option_type', '')}"}
                ]
            }
        ]
        
        if pnl != 0:
            blocks[1]["fields"].append(
                {"type": "mrkdwn", "text": f"*P&L:*\n${pnl:,.2f}"}
            )
        
        return await self.send_webhook(message, blocks)
    
    async def send_daily_report(self, report: Dict):
        """Send daily report"""
        message = f":chart: *Daily Report*\nTotal P&L: ${report.get('total_pnl', 0):,.2f}"
        
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "Daily Report"}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Total Trades:*\n{report.get('total_trades', 0)}"},
                    {"type": "mrkdwn", "text": f"*Win Rate:*\n{report.get('win_rate', 0):.1f}%"},
                    {"type": "mrkdwn", "text": f"*P&L:*\n${report.get('total_pnl', 0):,.2f}"},
                    {"type": "mrkdwn", "text": f"*Wins:*\n{report.get('wins', 0)}"}
                ]
            }
        ]
        
        return await self.send_webhook(message, blocks)
    
    async def send_alert_received(self, alert: Dict):
        """Send alert received notification"""
        message = f":bell: *Alert*: {alert.get('ticker')} {alert.get('strike')}{alert.get('option_type', '')}"
        
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": "New Alert Received"}},
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Ticker:*\n{alert.get('ticker')}"},
                    {"type": "mrkdwn", "text": f"*Type:*\n{alert.get('alert_type')}"},
                    {"type": "mrkdwn", "text": f"*Strike:*\n{alert.get('strike')}"},
                    {"type": "mrkdwn", "text": f"*Option:*\n{alert.get('option_type', '')}"}
                ]
            }
        ]
        
        return await self.send_webhook(message, blocks)
    
    async def send_risk_warning(self, message: str, details: Dict):
        """Send risk warning"""
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": ":warning: Risk Warning"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": message}}
        ]
        
        return await self.send_webhook(message, blocks)
    
    async def close(self):
        """Close session"""
        if self.session:
            await self.session.close()


# ========================
# Telegram Integration
# ========================

class TelegramNotifier:
    """Telegram bot notifications"""
    
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.session = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def _send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send message via Telegram API"""
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram not configured")
            return False
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        try:
            session = await self._get_session()
            async with session.post(url, json=payload) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False
    
    async def send_trade_alert(self, trade: Dict):
        """Send trade notification"""
        ticker = trade.get('ticker', '')
        pnl = trade.get('realized_pnl', 0) or 0
        pnl_str = f"\nP&L: ${pnl:,.2f}" if pnl != 0 else ""
        
        message = f"🔔 *Trade Executed*\n\n" \
                f"Ticker: *{ticker}*\n" \
                f"Action: {trade.get('alert_type', 'N/A')}\n" \
                f"Strike: {trade.get('strike')}\n" \
                f"Type: {trade.get('option_type', '')}\n" \
                f"{pnl_str}"
        
        return await self._send_message(message)
    
    async def send_daily_report(self, report: Dict):
        """Send daily report"""
        message = f"📊 *Daily Report*\n\n" \
                f"Total Trades: {report.get('total_trades', 0)}\n" \
                f"Win Rate: {report.get('win_rate', 0):.1f}%\n" \
                f"P&L: ${report.get('total_pnl', 0):,.2f}\n" \
                f"Wins: {report.get('wins', 0)}"
        
        return await self._send_message(message)
    
    async def send_alert_received(self, alert: Dict):
        """Send alert received notification"""
        message = f"🔔 *New Alert*\n\n" \
                f"Ticker: *{alert.get('ticker')}*\n" \
                f"Action: {alert.get('alert_type')}\n" \
                f"Strike: {alert.get('strike')}\n" \
                f"Type: {alert.get('option_type', '')}"
        
        return await self._send_message(message)
    
    async def send_risk_warning(self, message: str):
        """Send risk warning"""
        warning = f"⚠️ *Risk Warning*\n\n{message}"
        return await self._send_message(warning)
    
    async def send_status(self, status: Dict):
        """Send bot status"""
        message = f"🤖 *Bot Status*\n\n" \
                f"Discord: {'✅' if status.get('discord_connected') else '❌'}\n" \
                f"Broker: {'✅' if status.get('broker_connected') else '❌'}\n" \
                f"Auto-Trading: {'✅' if status.get('auto_trading_enabled') else '❌'}"
        
        return await self._send_message(message)
    
    async def close(self):
        """Close session"""
        if self.session:
            await self.session.close()


# ========================
# Notification Dispatcher
# ========================

class NotificationDispatcher:
    """Dispatch notifications to all configured channels"""
    
    def __init__(self):
        self.slack = SlackNotifier() if SLACK_WEBHOOK_URL else None
        self.telegram = TelegramNotifier() if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID else None
    
    async def notify_trade(self, trade: Dict):
        """Notify trade executed"""
        if self.slack:
            await self.slack.send_trade_alert(trade)
        if self.telegram:
            await self.telegram.send_trade_alert(trade)
    
    async def notify_alert(self, alert: Dict):
        """Notify new alert"""
        if self.slack:
            await self.slack.send_alert_received(alert)
        if self.telegram:
            await self.telegram.send_alert_received(alert)
    
    async def notify_daily_report(self, report: Dict):
        """Notify daily report"""
        if self.slack:
            await self.slack.send_daily_report(report)
        if self.telegram:
            await self.telegram.send_daily_report(report)
    
    async def notify_risk(self, message: str, details: Dict = None):
        """Notify risk warning"""
        if self.slack:
            await self.slack.send_risk_warning(message, details or {})
        if self.telegram:
            await self.telegram.send_risk_warning(message)
    
    async def notify_status(self, status: Dict):
        """Notify status update"""
        if self.telegram:
            await self.telegram.send_status(status)
    
    async def close(self):
        """Close all sessions"""
        if self.slack:
            await self.slack.close()
        if self.telegram:
            await self.telegram.close()


# Global dispatcher
notifier = NotificationDispatcher()


# Export
__all__ = [
    'TradingViewWebhook',
    'SlackNotifier', 
    'TelegramNotifier',
    'NotificationDispatcher',
    'notifier'
]