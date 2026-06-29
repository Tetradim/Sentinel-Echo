"""
Analyst Format Parser
Pre-built parsing patterns for 20+ different analyst formats
Based on DiscordAlertsTrader patterns

Supports formats for:
- EnhancedMarket
- Vader
- SwingTrader
- ThetaGang
- Momentum
- And many more...

Each format has custom patterns for parsing BTO/STC/PT/SL signals
"""
import os
import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Types of trading signals"""
    BTO = "BTO"  # Buy To Open
    STC = "STC"  # Sell To Close
    STO = "STO"   # Sell To Open (short)
    BTC = "BTC"   # Buy To Close (cover)
    AVG = "AVG"   # Average down
    PT = "PT"    # Profit target
    SL = "SL"    # Stop loss
    TRAIL = "TRAIL"  # Trailing stop
    ROLL = "ROLL"  # Roll position
    UNKNOWN = "UNKNOWN"


@dataclass
class ParsedSignal:
    """A parsed trading signal"""
    signal_type: SignalType = SignalType.UNKNOWN
    ticker: str = ""
    strike: float = 0.0
    option_type: str = "CALL"  # CALL or PUT
    expiration: str = ""
    quantity: int = 1
    price: float = 0.0
    side: str = "BUY"  # BUY or SELL
    
    # Exit signals
    profit_target: Optional[float] = None
    stop_loss: Optional[float] = None
    trailing_stop: Optional[float] = None
    
    # Raw message
    raw_message: str = ""
    analyst: str = ""
    
    def to_dict(self) -> dict:
        return {
            'signal_type': self.signal_type.value,
            'ticker': self.ticker,
            'strike': self.strike,
            'option_type': self.option_type,
            'expiration': self.expiration,
            'quantity': self.quantity,
            'price': self.price,
            'side': self.side,
            'profit_target': self.profit_target,
            'stop_loss': self.stop_loss,
            'trailing_stop': self.trailing_stop,
            'analyst': self.analyst,
        }


class AnalystFormat:
    """
    Format parser for a specific analyst
    Each analyst has their own message format
    """
    
    def __init__(
        self,
        name: str,
        # Buy signals
        bto_patterns: List[str] = None,
        # Sell signals
        stc_patterns: List[str] = None,
        # Ticker extraction
        ticker_pattern: str = r'\$?([A-Z]{1,5})\b',
        # Strike extraction (with option type)
        strike_patterns: List[str] = None,
        # Price extraction
        price_patterns: List[str] = None,
        # Expiration extraction
        expiration_patterns: List[str] = None,
        # Quantity patterns
        quantity_patterns: List[str] = None,
        # Keywords to identify this format
        identifiers: List[str] = None,
    ):
        self.name = name
        self.bto_patterns = bto_patterns or []
        self.stc_patterns = stc_patterns or []
        self.ticker_pattern = ticker_pattern
        self.strike_patterns = strike_patterns or [
            r'\$(\d+)\s*(CALLS?|PUTS?)',
            r'(\d+)(C|P)\b',
            r'Strike[:\s]*(\d+)',
        ]
        self.price_patterns = price_patterns or [
            r'\$?([\d.]+)\s*(?:ENTRY|PRICE|AT|@)',
            r'Entry[:\s]*\$?([\d.]+)',
            r'@\s*\$?([\d.]+)',
        ]
        self.expiration_patterns = expiration_patterns or [
            r'EXP(?:iration)?[:\s]*(\d{1,2}/\d{1,2}/?\d{0,4})',
            r'(\d{1,2}/\d{1,2}/\d{2,4})',
        ]
        self.quantity_patterns = quantity_patterns or [
            r'(\d+)\s*contracts?',
            r'(\d+)x',
            r'x(\d+)',
            r'Qty[:\s]*(\d+)',
        ]
        self.identifiers = identifiers or []
    
    def parse(self, message: str) -> Optional[ParsedSignal]:
        """Parse a message and return a signal"""
        msg_upper = message.upper()
        
        # Check if this format matches
        if self.identifiers:
            if not any(kw.upper() in msg_upper for kw in self.identifiers):
                return None
        
        # Detect signal type
        signal_type = self._detect_signal_type(msg_upper)
        if signal_type == SignalType.UNKNOWN:
            return None
        
        # Extract components
        signal = ParsedSignal(
            signal_type=signal_type,
            raw_message=message,
            analyst=self.name,
        )
        
        # Ticker
        ticker_match = re.search(self.ticker_pattern, msg_upper)
        if ticker_match:
            signal.ticker = ticker_match.group(1)
        
        # Strike & Option Type
        for pattern in self.strike_patterns:
            match = re.search(pattern, msg_upper)
            if match:
                signal.strike = float(match.group(1))
                opt = match.group(2).upper()
                signal.option_type = 'CALL' if 'C' in opt else 'PUT'
                break
        
        # Expiration
        for pattern in self.expiration_patterns:
            match = re.search(pattern, msg_upper)
            if match:
                signal.expiration = match.group(1)
                break
        
        # Price
        for pattern in self.price_patterns:
            match = re.search(pattern, msg_upper)
            if match:
                price_str = match.group(1)
                if '.' in price_str:
                    signal.price = float(price_str)
                else:
                    # Handle $.29 format
                    signal.price = float(f"0.{price_str}")
                break
        
        # Quantity
        for pattern in self.quantity_patterns:
            match = re.search(pattern, msg_upper)
            if match:
                signal.quantity = int(match.group(1))
                break
        
        if signal.ticker and signal.strike > 0:
            return signal
        
        return None
    
    def _detect_signal_type(self, message: str) -> SignalType:
        """Detect the type of signal"""
        # BTO patterns
        for pattern in self.bto_patterns:
            if pattern.upper() in message:
                return SignalType.BTO
        
        # STC patterns
        for pattern in self.stc_patterns:
            if pattern.upper() in message:
                return SignalType.STC
        
        return SignalType.UNKNOWN


# ============= ANALYST FORMATS =============

# Collection of all analyst formats
ANALYST_FORMATS: Dict[str, AnalystFormat] = {}


def _register_formats():
    """Register all analyst formats"""
    
    # Format 1: Default/Standard
    ANALYST_FORMATS["default"] = AnalystFormat(
        name="Default",
        bto_patterns=["BTO", "BUY", "ENTRY", "LONG", "OPEN"],
        stc_patterns=["STC", "SELL", "EXIT", "CLOSE", "COVER"],
        identifiers=["$"],
        ticker_pattern=r'\$([A-Z]{1,5})\b',
        strike_patterns=[r'\$(\d+)\s*(CALLS?|PUTS?)', r'(\d+)(C|P)\b'],
        price_patterns=[r'\$([\d.]+)', r'@\s*\$?([\d.]+)'],
    )
    
    # Format 2: EnhancedMarket style
    ANALYST_FORMATS["enhancedmarket"] = AnalystFormat(
        name="EnhancedMarket",
        bto_patterns=["BTO", "NEW ENTRY", "OPENING POSITION"],
        stc_patterns=["STC", "CLOSING POSITION", "TAKE PROFIT"],
        identifiers=["BTO", "STC"],
        strike_patterns=[r'(\d+)\s*(CALL|PUT)'],
        price_patterns=[r'@[\s$]*([\d.]+)'],
    )
    
    # Format 3: Vader style
    ANALYST_FORMATS["vader"] = AnalystFormat(
        name="Vader",
        bto_patterns=["OPEN", "LONG", "CALL", "PUT"],
        stc_patterns=["CLOSE", "EXIT"],
        identifiers=["VADER", "ANALYST"],
        strike_patterns=[r'(\d+)[CP]\b'],
        price_patterns=[r'entry:?\s*\$?([\d.]+)', r'price:?\s*\$?([\d.]+)'],
    )
    
    # Format 4: SwingTrader style
    ANALYST_FORMATS["swingtrader"] = AnalystFormat(
        name="SwingTrader",
        bto_patterns=["SWING", "LONG POSITION", "BUY"],
        stc_patterns=["EXIT SWING", "TAKE PROFIT", "STOP"],
        identifiers=["SWING"],
        ticker_pattern=r'([A-Z]{2,5})\b',
        strike_patterns=[r'strike:? (\d+)'],
    )
    
    # Format 5: ThetaGang style
    ANALYST_FORMATS["thetagang"] = AnalystFormat(
        name="ThetaGang",
        bto_patterns=["SELL PUT", "SELL CALL", "SELL CSP", "SELL CC"],
        stc_patterns=["BUY TO CLOSE", "EXPIRE WORTHLESS"],
        identifiers=["THETA", "SELL PUT", "SELL CALL"],
        strike_patterns=[r'(\d+)[CP]', r'(\d+)\s*(CALL|PUT)'],
    )
    
    # Format 6: Momentum style
    ANALYST_FORMATS["momentum"] = AnalystFormat(
        name="Momentum",
        bto_patterns=["MOMENTUM", "BREAKOUT", "NEW HIGH"],
        stc_patterns=["REVERSAL", "STOP HIT"],
        identifiers=["MOMENTUM"],
        price_patterns=[r'@[\s$]*([\d.]+)'],
    )
    
    # Format 7: Standard Alerts (BTO/STC style)
    ANALYST_FORMATS["standard"] = AnalystFormat(
        name="Standard Alerts",
        bto_patterns=["BTO", "BUY TO OPEN"],
        stc_patterns=["STC", "SELL TO CLOSE"],
        identifiers=["BTO", "STC"],
        strike_patterns=[r'(\d+)\s*(?:C|P)\b'],
        price_patterns=[r'@\s*\$?([\d.]+)'],
    )
    
    # Format 8: Simple Buy/Sell
    ANALYST_FORMATS["simple"] = AnalystFormat(
        name="Simple",
        bto_patterns=["BUY", "BOUGHT", "GOING LONG"],
        stc_patterns=["SELL", "SOLD", "CLOSING"],
        identifiers=["BUY", "SELL"],
        strike_patterns=[r'\$(\d+)'],
    )
    
    # Format 9: Live Trading Room
    ANALYST_FORMATS["livetraidng"] = AnalystFormat(
        name="LiveTrading",
        bto_patterns=["GET IN", "TAKE TRADE", "ENTRY"],
        stc_patterns=["GET OUT", "CLOSE TRADE", "TAKE PROFIT"],
        identifiers=["ENTRY", "EXIT"],
        strike_patterns=[r'(\d+)\s*(?:CALL|PUT)'],
    )
    
    # Format 10: The Whotrade
    ANALYST_FORMATS["whotrade"] = AnalystFormat(
        name="WhoTrade",
        bto_patterns=["NEW PICK", "CALL", "PUT"],
        stc_patterns=["CLOSE", "SOLD"],
        identifiers=["PICK"],
        strike_patterns=[r'(\d+)[CP]'],
        price_patterns=[r'\$\.?([\d.]+)'],
    )
    
    # Format 11: StockWhale
    ANALYST_FORMATS["stockwhale"] = AnalystFormat(
        name="StockWhale",
        bto_patterns=["WHALE", "PICK", "ALERT"],
        stc_patterns=["CLOSED", "TAKEN"],
        identifiers=["WHALE"],
        price_patterns=[r'@?\$?([\d.]+)'],
    )
    
    # Format 12: GammaScalper
    ANALYST_FORMATS["gammascaler"] = AnalystFormat(
        name="GammaScaler",
        bto_patterns=["SCALP", "GAMMA", "PLAY"],
        stc_patterns=["TAKEN", "FLATTEN"],
        identifiers=["GAMMA", "SCALP"],
        strike_patterns=[r'(\d+)'],
    )
    
    # Format 13: Bullish Bearish
    ANALYST_FORMATS["bullishbearish"] = AnalystFormat(
        name="BullishBearish",
        bto_patterns=["BULLISH", "BEARISH", "PLAY"],
        stc_patterns=["FLATTEN", "CLOSED"],
        identifiers=["BULL", "BEAR"],
        strike_patterns=[r'(\d+)'],
    )
    
    # Format 14: Option Flow
    ANALYST_FORMATS["optionflow"] = AnalystFormat(
        name="OptionFlow",
        bto_patterns=["FLOW", "ORDER", "FILLED"],
        stc_patterns=["CLOSED", "EXIT"],
        identifiers=["FLOW"],
        price_patterns=[r'filled.?at.?\$?([\d.]+)'],
    )
    
    # Format 15: Trade Ideas
    ANALYST_FORMATS["tradeideas"] = AnalystFormat(
        name="TradeIdeas",
        bto_patterns=["IDEA", "TRADE", "SIGNAL"],
        stc_patterns=["CLOSED IDEA"],
        identifiers=["IDEA"],
        strike_patterns=[r'(\d+)'],
    )
    
    # Format 16: Day Trade Alerts
    ANALYST_FORMATS["daytrade"] = AnalystFormat(
        name="DayTrade",
        bto_patterns=["DAY TRADE", "SCALP", "MORNING"],
        stc_patterns=["TAKEN", "SCALPED"],
        identifiers=["DAY", "SCALP"],
        strike_patterns=[r'(\d+)'],
    )
    
    # Format 17: Swing Alert
    ANALYST_FORMATS["swingalert"] = AnalystFormat(
        name="SwingAlert",
        bto_patterns=["NEW SWING", "POSSITION"],
        stc_patterns=["SWING CLOSED"],
        identifiers=["SWING"],
        strike_patterns=[r'(\d+)'],
    )
    
    # Format 18: Crypto Alerts
    ANALYST_FORMATS["crypto"] = AnalystFormat(
        name="Crypto",
        bto_patterns=["LONG", "BUY BTC", "BUY ETH"],
        stc_patterns=["SELL", "CLOSE LONG"],
        identifiers=["BTC", "ETH"],
        strike_patterns=[r'(\d+)'],
    )
    
    # Format 19: Penny Stock
    ANALYST_FORMATS["pennystock"] = AnalystFormat(
        name="PennyStock",
        bto_patterns=["PENNY", "LOW FLOAT"],
        stc_patterns=["TAKEN", "SOLD"],
        identifiers=["PENNY"],
        strike_patterns=[r'(\d+\.?\d*)'],
    )
    
    # Format 20: Earnings Play
    ANALYST_FORMATS["earnings"] = AnalystFormat(
        name="Earnings",
        bto_patterns=["EARNINGS", "ER PLAY", "MOVE"],
        stc_patterns=["POST ER", "TAKEN"],
        identifiers=["EARNINGS", "ER"],
        strike_patterns=[r'(\d+)'],
    )
    
    # Format 21: Iron Condor / Theta
    ANALYST_FORMATS["ironcondor"] = AnalystFormat(
        name="IronCondor",
        bto_patterns=["IRON CONDOR", "SHORT STRADDLE", "SHORT STRANGLE"],
        stc_patterns=["EXPIRE", "ROLL", "TAKE DELTA"],
        identifiers=["IRON", "STRADDLE"],
    )

    # ============= ADDITIONAL STRATEGIES (from OctoBot/Nautilus) =============

    # Format 22: Grid Trading
    ANALYST_FORMATS["grid"] = AnalystFormat(
        name="Grid Trading",
        bto_patterns=["GRID BUY", "GRID LEVEL"],
        stc_patterns=["GRID SELL", "CLOSE GRID"],
        identifiers=["GRID"],
    )

    # Format 23: DCA
    ANALYST_FORMATS["dca"] = AnalystFormat(
        name="DCA",
        bto_patterns=["DCA", "AVERAGE DOWN", "ACCUMULATE"],
        stc_patterns=["CLOSE", "TAKE PROFIT"],
        identifiers=["DCA", "AVERAGE"],
    )

    # Format 24: Scalp
    ANALYST_FORMATS["scalp"] = AnalystFormat(
        name="Scalp",
        bto_patterns=["SCALP", "QUICK", "MOMENTUM"],
        stc_patterns=["TAKEN", "QUICK EXIT"],
        identifiers=["SCALP"],
    )

    # Format 25: Swing
    ANALYST_FORMATS["swingtrade"] = AnalystFormat(
        name="Swing",
        bto_patterns=["SWING", "MULTI-DAY", "MID-TERM"],
        stc_patterns=["SWING CLOSE"],
        identifiers=["SWING"],
    )

    # Format 26: Trend Following
    ANALYST_FORMATS["trend"] = AnalystFormat(
        name="Trend Following",
        bto_patterns=["TREND", "FOLLOW", "BREAKOUT"],
        stc_patterns=["TREND END", "REVERSAL"],
        identifiers=["TREND"],
    )

    # Format 27: Mean Reversion
    ANALYST_FORMATS["meanreversion"] = AnalystFormat(
        name="MeanReversion",
        bto_patterns=["MEAN", "REVERT", "OVERSOOLD"],
        stc_patterns=["MEAN REVERTED"],
        identifiers=["MEAN", "REVERT"],
    )

    # Format 28: Volatility
    ANALYST_FORMATS["volatility"] = AnalystFormat(
        name="Volatility",
        bto_patterns=["VOLATILITY", "IV CRUSH", "EARNINGS"],
        stc_patterns=["VOLATILITY PLAYED"],
        identifiers=["VOL", "IV"],
    )

    # Format 29: News
    ANALYST_FORMATS["news"] = AnalystFormat(
        name="News Trading",
        bto_patterns=["NEWS", "CATALYST", "ALERT"],
        stc_patterns=["NEWS PLAYED"],
        identifiers=["NEWS", "CATALYST"],
    )

    # Format 30: Arbitrage
    ANALYST_FORMATS["arb"] = AnalystFormat(
        name="Arbitrage",
        bto_patterns=["ARB", "SPREAD", "ARBITRAGE"],
        stc_patterns=["ARB CLOSE"],
        identifiers=["ARB", "SPREAD"],
    )

    # Format 31: China Bull
    ANALYST_FORMATS["chinabull"] = AnalystFormat(
        name="China Bull",
        bto_patterns=["买入", "做多", "开多"],
        stc_patterns=["卖出", "平仓", "止盈"],
        identifiers=["买入", "开多"],
    )
    
    # Format 32: Korean traders
    ANALYST_FORMATS["korean"] = AnalystFormat(
        name="Korean",
        bto_patterns=["매수", "лонg", "사"],
        stc_patterns=["매도", "익", "罗伯特"],
        identifiers=["매수", "매도"],
    )
    
    logger.info(f"[AnalystFormats] Registered {len(ANALYST_FORMATS)} formats")


# Initialize formats
_register_formats()


# ============= PARSING FUNCTIONS =============

def parse_with_format(message: str, format_name: str) -> Optional[ParsedSignal]:
    """Parse a message with a specific format"""
    format_parser = ANALYST_FORMATS.get(format_name)
    if format_parser:
        return format_parser.parse(message)
    return None


def _identifier_match_count(message_upper: str, format_parser: AnalystFormat) -> int:
    return sum(1 for kw in format_parser.identifiers if kw.upper() in message_upper)


def _identifier_specificity(message_upper: str, format_parser: AnalystFormat) -> int:
    matched_lengths = [
        len(kw)
        for kw in format_parser.identifiers
        if kw.upper() in message_upper
    ]
    return max(matched_lengths, default=0)


def _candidate_format_names(message: str, preferred_format: Optional[str] = None) -> List[str]:
    """Return a prioritized parse order before falling back to every format."""
    msg_upper = message.upper()
    candidates: List[str] = []

    def add_candidate(name: str) -> None:
        if name in ANALYST_FORMATS and name not in candidates:
            candidates.append(name)

    if preferred_format:
        add_candidate(preferred_format)

    scored_matches: List[Tuple[int, int, int, str]] = []
    for index, (name, format_parser) in enumerate(ANALYST_FORMATS.items()):
        if not format_parser.identifiers:
            continue
        match_count = _identifier_match_count(msg_upper, format_parser)
        if match_count > 0:
            specificity = _identifier_specificity(msg_upper, format_parser)
            scored_matches.append((-match_count, -specificity, index, name))

    for _, _, _, name in sorted(scored_matches):
        add_candidate(name)

    for name in ANALYST_FORMATS:
        add_candidate(name)

    return candidates


def auto_parse(message: str, preferred_format: Optional[str] = None) -> Optional[ParsedSignal]:
    """
    Auto-detect format and parse message.

    If a channel/source has a configured parser, try that first.  Otherwise,
    try formats whose identifiers are present before falling back to the full
    registry.  This keeps behavior compatible while avoiding the common
    worst-case scan across every analyst parser.
    """
    for name in _candidate_format_names(message, preferred_format=preferred_format):
        format_parser = ANALYST_FORMATS[name]
        signal = format_parser.parse(message)
        if signal:
            return signal
    
    return None


def detect_format(message: str) -> str:
    """Detect which format a message is using"""
    msg_upper = message.upper()
    
    best_match = "default"
    max_matches = 0
    
    for name, format_parser in ANALYST_FORMATS.items():
        if not format_parser.identifiers:
            continue

        matches = _identifier_match_count(msg_upper, format_parser)
        if matches > max_matches:
            max_matches = matches
            best_match = name
    
    return best_match


def get_available_formats() -> List[dict]:
    """Get list of all available formats"""
    return [
        {"id": name, "name": f.name, "identifiers": f.identifiers}
        for name, f in ANALYST_FORMATS.items()
    ]


# ============= BACKWARD COMPATIBILITY =============

# Legacy function names for compatibility
def parse_alert(message: str) -> Optional[dict]:
    """Legacy: Parse alert message - returns dict"""
    signal = auto_parse(message)
    if signal:
        return signal.to_dict()
    return None


def detect_alert_type(message: str) -> str:
    """Legacy: Detect alert type"""
    signal = auto_parse(message)
    if signal:
        return signal.signal_type.value
    return "UNKNOWN"


# ============= EXPORTS =============

__all__ = [
    'SignalType',
    'ParsedSignal', 
    'AnalystFormat',
    'ANALYST_FORMATS',
    'parse_with_format',
    'auto_parse',
    'detect_format',
    'get_available_formats',
    'parse_alert',
    'detect_alert_type',
]
