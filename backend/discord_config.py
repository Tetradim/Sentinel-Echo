"""
Discord Alert Pattern Configuration
Make alert parsing customizable per community
"""
import os
import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# ============= ANALYST FORMAT SUPPORT =============

def _import_analyst_formats():
    """Lazy import of analyst formats"""
    try:
        from analyst_formats import auto_parse, detect_format, get_available_formats
        return auto_parse, detect_format, get_available_formats
    except ImportError:
        return None, None, None

_auto_parse, _detect_format, _get_formats = _import_analyst_formats()


# Legacy wrapper functions
def parse_alert_with_analyst(message: str) -> Optional[dict]:
    """Parse using analyst formats"""
    if _auto_parse:
        result = _auto_parse(message)
        if result:
            return result.to_dict()
    return None


def detect_analyst_format(message: str) -> str:
    """Detect which analyst format"""
    if _detect_format:
        return _detect_format(message)
    return "default"


def list_analyst_formats() -> List[dict]:
    """List available formats"""
    if _get_formats:
        return _get_formats()
    return [{"id": "default", "name": "Default"}]


@dataclass
class AlertPatternConfig:
    """Configuration for Discord alert parsing"""
    
    # ============= BUY PATTERNS =============
    # Keywords that trigger a BUY alert
    buy_keywords: List[str] = field(default_factory=lambda: [
        "BUY", "BUYING", "BOUGHT", "ENTRY", "ENTERING", 
        "LONG", "GOING LONG", "BTO", "OPENING", "NEW POSITION"
    ])
    
    # ============= SELL PATTERNS =============
    # Keywords that trigger a SELL alert
    sell_keywords: List[str] = field(default_factory=lambda: [
        "SELL", "SELLING", "SOLD", "EXIT", "EXITING", 
        "CLOSE", "CLOSING", "STC", "TRIM", "TAKE PROFIT"
    ])
    
    # ============= AVERAGE DOWN PATTERNS =============
    # Keywords that trigger averaging down
    avg_down_keywords: List[str] = field(default_factory=lambda: [
        "AVERAGE DOWN", "AVG DOWN", "AVERAGING", "ADD TO", "DOUBLE DOWN"
    ])
    
    # ============= IGNORE PATTERNS =============
    # Keywords that should be ignored
    ignore_keywords: List[str] = field(default_factory=lambda: [
        "WATCHLIST", "WATCHING", "MIGHT", "MAYBE", "CONSIDERING", 
        "PAPER", "DEMO", "IF", "WOULD"
    ])
    
    # ============= TICKER FORMAT =============
    # Regex pattern for extracting ticker
    ticker_pattern: str = r'\$([A-Z]{1,5})\b'
    
    # ============= STRIKE FORMAT =============
    # Regex patterns for strike price
    strike_patterns: List[str] = field(default_factory=lambda: [
        r'\$?(\d+(?:\.\d+)?)\s*(CALLS?|PUTS?)',
        r'\$?(\d+(?:\.\d+)?)(C|P)\b',
    ])
    
    # ============= EXPIRATION FORMAT =============
    # Regex patterns for expiration
    expiration_patterns: List[str] = field(default_factory=lambda: [
        r'EXP(?:IRATION)?:?\s*(\d{1,2}/\d{1,2}/?\d{0,4})',
        r'EXP\s*(\d{1,2}/\d{1,2}/\d{2,4})',
    ])
    
    # ============= PRICE FORMAT =============
    # Regex patterns for entry price
    price_patterns: List[str] = field(default_factory=lambda: [
        r'\$?([\d.]+)\s*ENTRY',
        r'ENTRY:?\s*\$?([\d.]+)',
        r'@\s*\$?([\d.]+)',
        r'\$\.([\d]+)',  # Just $.29 format
    ])
    
    # ============= REQUIREMENTS =============
    # Whether ticker prefix ($) is required
    require_ticker_prefix: bool = True
    require_expiration: bool = True
    require_price: bool = True
    
    # ============= FILTERS =============
    # Only listen to specific users (empty = all)
    listen_to_users: List[str] = field(default_factory=list)
    
    # Ignore specific users
    ignore_users: List[str] = field(default_factory=list)
    
    # Only listen to specific channels (empty = all)
    listen_to_channels: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            'buy_keywords': self.buy_keywords,
            'sell_keywords': self.sell_keywords,
            'avg_down_keywords': self.avg_down_keywords,
            'ignore_keywords': self.ignore_keywords,
            'ticker_pattern': self.ticker_pattern,
            'strike_patterns': self.strike_patterns,
            'expiration_patterns': self.expiration_patterns,
            'price_patterns': self.price_patterns,
            'require_ticker_prefix': self.require_ticker_prefix,
            'require_expiration': self.require_expiration,
            'require_price': self.require_price,
            'listen_to_users': self.listen_to_users,
            'ignore_users': self.ignore_users,
            'listen_to_channels': self.listen_to_channels,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AlertPatternConfig':
        """Create from saved config"""
        config = cls()
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config


class DiscordListenerConfig:
    """Discord listener configuration for a community"""
    
    def __init__(self, community_id: str):
        self.community_id = community_id
        self.name = f"Community {community_id}"
        self.enabled = True
        self.created_at = datetime.now()
        
        # Channel configuration
        self.channel_ids: List[str] = []
        
        # Bot token for this community
        self.bot_token: str = ""
        
        # Alert patterns
        self.patterns = AlertPatternConfig()
        
        # Notification settings
        self.notify_on_trade: bool = True
        self.notify_channel_ids: List[str] = []
        
        # Auto-trading
        self.auto_trade_enabled: bool = False
        self.simulation_mode: bool = False
        
        # Broker config for this community
        self.broker_type: str = "IBKR"
        self.broker_settings: Dict = {}
    
    def to_dict(self) -> dict:
        return {
            'community_id': self.community_id,
            'name': self.name,
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat(),
            'channel_ids': self.channel_ids,
            'bot_token': self.bot_token,
            'patterns': self.patterns.to_dict(),
            'notify_on_trade': self.notify_on_trade,
            'notify_channel_ids': self.notify_channel_ids,
            'auto_trade_enabled': self.auto_trade_enabled,
            'simulation_mode': self.simulation_mode,
            'broker_type': self.broker_type,
            'broker_settings': self.broker_settings,
        }
    
    @classmethod
    def from_dict(cls, community_id: str, data: dict) -> 'DiscordListenerConfig':
        """Create from saved config"""
        config = cls(community_id)
        for key, value in data.items():
            if key == 'patterns':
                config.patterns = AlertPatternConfig.from_dict(value)
            elif hasattr(config, key):
                setattr(config, key, value)
        return config


class MultiCommunityManager:
    """Manage multiple Discord communities"""
    
    def __init__(self):
        self._communities: Dict[str, DiscordListenerConfig] = {}
        self._active_community: Optional[str] = None
    
    def add_community(self, community_id: str, config: DiscordListenerConfig) -> None:
        self._communities[community_id] = config
        logger.info(f"[MultiCommunity] Added community: {community_id}")
    
    def get_community(self, community_id: str) -> Optional[DiscordListenerConfig]:
        return self._communities.get(community_id)
    
    def remove_community(self, community_id: str) -> bool:
        if community_id in self._communities:
            del self._communities[community_id]
            logger.info(f"[MultiCommunity] Removed community: {community_id}")
            return True
        return False
    
    def list_communities(self) -> List[dict]:
        return [
            {**c.to_dict(), 'community_id': cid}
            for cid, c in self._communities.items()
        ]
    
    def set_active(self, community_id: str) -> bool:
        if community_id in self._communities:
            self._active_community = community_id
            return True
        return False
    
    def get_active(self) -> Optional[DiscordListenerConfig]:
        if self._active_community:
            return self._communities.get(self._active_community)
        return None
    
    def update_patterns(self, community_id: str, patterns: AlertPatternConfig) -> bool:
        if community_id in self._communities:
            self._communities[community_id].patterns = patterns
            return True
        return False


# Global manager
_manager: Optional[MultiCommunityManager] = None


def get_community_manager() -> MultiCommunityManager:
    global _manager
    if _manager is None:
        _manager = MultiCommunityManager()
    return _manager


# ============= PARSING WITH CUSTOM PATTERNS =============

def parse_alert_with_config(
    message: str,
    config: AlertPatternConfig
) -> Optional[dict]:
    """
    Parse alert using custom patterns from config
    """
    message_upper = message.upper()
    
    # Check ignore patterns
    for ignore in config.ignore_keywords:
        if ignore.upper() in message_upper:
            return None
    
    # Detect alert type
    alert_type = _detect_alert_type(message_upper, config)
    if not alert_type:
        return None
    
    # Parse components
    result = {
        'alert_type': alert_type,
        'ticker': None,
        'strike': None,
        'option_type': None,
        'expiration': None,
        'entry_price': None,
    }
    
    # Extract ticker
    ticker_match = re.search(config.ticker_pattern, message_upper)
    if ticker_match:
        result['ticker'] = ticker_match.group(1)
    
    # Extract strike & option type
    for pattern in config.strike_patterns:
        match = re.search(pattern, message_upper)
        if match:
            result['strike'] = float(match.group(1))
            opt_type = match.group(2).upper()
            result['option_type'] = 'CALL' if 'C' in opt_type else 'PUT'
            break
    
    # Extract expiration
    for pattern in config.expiration_patterns:
        match = re.search(pattern, message_upper)
        if match:
            result['expiration'] = match.group(1)
            break
    
    # Extract price
    for pattern in config.price_patterns:
        match = re.search(pattern, message_upper)
        if match:
            price_str = match.group(1)
            if '.' not in price_str and len(price_str) <= 2:
                result['entry_price'] = float(f"0.{price_str}")
            else:
                result['entry_price'] = float(price_str)
            break
    
    # Validate
    if config.require_ticker_prefix and not result['ticker']:
        return None
    if config.require_expiration and not result['expiration']:
        return None
    if config.require_price and not result['entry_price']:
        return None
    
    if result['ticker'] and result['strike'] and result['option_type']:
        return result
    
    return None


def _detect_alert_type(message: str, config: AlertPatternConfig) -> Optional[str]:
    """Detect alert type from message using config patterns"""
    
    # Check buy keywords
    for kw in config.buy_keywords:
        if kw.upper() in message:
            return 'buy'
    
    # Check sell keywords
    for kw in config.sell_keywords:
        if kw.upper() in message:
            return 'sell'
    
    # Check avg down keywords
    for kw in config.avg_down_keywords:
        if kw.upper() in message:
            return 'average_down'
    
    return None


# ============= DEFAULT COMMUNITY PRESETS =============

COMMUNITY_PRESETS = {
    "default": {
        "name": "Default",
        "buy_keywords": ["BUY", "ENTRY", "LONG"],
        "sell_keywords": ["SELL", "EXIT", "CLOSE"],
        "avg_down_keywords": ["AVERAGE DOWN", "AVG DOWN"],
        "require_ticker_prefix": True,
    },
    "aggressive": {
        "name": "Aggressive Trading",
        "buy_keywords": ["BUY", "ENTRY", "LONG", "BTO", "SCALP", "LOTTO"],
        "sell_keywords": ["SELL", "EXIT", "CLOSE", "STC", "STC HALF", "TRIM"],
        "avg_down_keywords": ["AVERAGE DOWN", "AVG DOWN", "ADD", "DOUBLE"],
        "require_ticker_prefix": False,
    },
    "swing": {
        "name": "Swing Trading",
        "buy_keywords": ["BUY", "LONG", "SWING", "POSITION"],
        "sell_keywords": ["SELL", "CLOSE", "TAKE PROFIT", "TARGET HIT"],
        "avg_down_keywords": ["AVERAGE DOWN", "ADD TO POSITION"],
        "require_ticker_prefix": True,
    },
    "theta": {
        "name": "Theta Gang",
        "buy_keywords": ["SELL", "SELL PUT", "SELL CALL", "SHORT"],
        "sell_keywords": ["BUY TO CLOSE", "EXPIRE", "TAKE ASSIGNED"],
        "avg_down_keywords": ["ROLL", "EXTEND"],
        "require_ticker_prefix": True,
    },
    "momentum": {
        "name": "Momentum",
        "buy_keywords": ["BUY", "MOMENTUM", "BREAKOUT", "NEW HIGH"],
        "sell_keywords": ["SELL", "REVERSAL", "STOP", "TRAIL"],
        "avg_down_keywords": ["AVERAGE DOWN", "DIP BUY"],
        "require_ticker_prefix": True,
    },
}


def get_preset(preset_name: str) -> AlertPatternConfig:
    """Get a community preset"""
    if preset_name not in COMMUNITY_PRESETS:
        preset_name = "default"
    
    preset = COMMUNITY_PRESETS[preset_name]
    config = AlertPatternConfig()
    config.buy_keywords = preset.get('buy_keywords', config.buy_keywords)
    config.sell_keywords = preset.get('sell_keywords', config.sell_keywords)
    config.avg_down_keywords = preset.get('avg_down_keywords', config.avg_down_keywords)
    config.require_ticker_prefix = preset.get('require_ticker_prefix', True)
    
    return config
