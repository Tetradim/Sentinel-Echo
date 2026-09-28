"""
Enhanced Data Models for Trading Bot
Includes all models for trading, positions, settings
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


class BrokerType(str, Enum):
    IBKR = "IBKR"
    ALPACA = "ALPACA"
    TD_AMERITRADE = "TD_AMERITRADE"
    TRADIER = "TRADIER"
    WEBULL = "WEBULL"
    ROBINHOOD = "ROBINHOOD"
    TRADESTATION = "TRADESTATION"
    THINKORSWIM = "THINKORSWIM"
    WEALTHSIMPLE = "WEALTHSIMPLE"


class OptionType(str, Enum):
    CALL = "CALL"
    PUT = "PUT"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class AlertType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    AVERAGE_DOWN = "average_down"
    CLOSE = "close"
    TRIM = "trim"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    STOPPED = "stopped"
    TAKEN_PROFIT = "taken_profit"
    EXPIRED = "expired"


# ============= BROKER CONFIG =============

class BrokerConfig(BaseModel):
    """Broker configuration"""
    id: Optional[str] = None
    name: str = "My Broker"
    broker_type: BrokerType = BrokerType.IBKR
    
    # Connection settings
    gateway_url: str = "https://localhost:5000"
    api_key: str = ""
    api_secret: str = ""
    account_id: str = ""
    
    # IBKR specific
    ibkr_account_id: str = ""
    
    # Alpaca specific
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_paper: bool = False
    
    # Tradier specific
    tradier_account_id: str = ""
    tradier_access_token: str = ""
    
    # TD Ameritrade
    tda_account_id: str = ""
    tda_refresh_token: str = ""
    tda_client_id: str = ""
    
    # Schwab/ThinkOrSwim
    tos_consumer_key: str = ""
    tos_refresh_token: str = ""
    
    # Robinhood
    robin_username: str = ""
    robin_password: str = ""
    
    # Wealthsimple
    ws_email: str = ""
    ws_password: str = ""
    ws_otp_code: str = ""
    
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============= TRADING SETTINGS =============

class TradingSettings(BaseModel):
    """Trading configuration"""
    id: str = "main"
    
    # Order settings
    default_quantity: int = 1
    max_position_size: float = 1000.0
    max_positions_per_ticker: int = 3
    
    # Price buffer (safety margin)
    price_buffer_percentage: float = 3.0  # 3% buffer
    use_price_buffer: bool = True
    
    # Bracket orders
    enable_bracket_orders: bool = True
    default_profit_target: float = 50.0  # 50% profit
    default_stop_loss: float = 30.0  # 30% loss
    
    # Trailing stop
    enable_trailing_stop: bool = True
    default_trailing_percentage: float = 25.0  # 25% trailing
    
    # Auto-trading
    auto_trading_enabled: bool = True
    simulation_mode: bool = False
    
    # Risk
    max_open_positions: int = 10
    max_daily_loss: float = 500.0
    
    # Execution
    order_timeout_seconds: int = 30
    retry_filled_check: bool = True
    retry_interval_seconds: int = 2
    
    # Notifications
    notify_on_trade: bool = True
    notify_on_error: bool = True
    
    # Updated
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


# ============= DISCORD SETTINGS =============

class DiscordSettings(BaseModel):
    """Discord bot configuration"""
    id: str = "main"
    
    # Bot settings
    bot_token: str = ""
    channel_ids: List[str] = []
    
    # Alert parsing
    required_ticker_prefix: bool = True  # $TICKER required
    parse_expiration: bool = True
    parse_entry_price: bool = True
    
    # Alert types to process
    buy_alerts_enabled: bool = True
    sell_alerts_enabled: bool = True
    avg_down_enabled: bool = True
    
    # Mentions
    mention_on_trade: bool = True  # Mention user on trade
    mention_on_error: bool = True
    
    # Filtering
    ignored_users: List[str] = []
    
    # Updated
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============= ALERTS =============

class Alert(BaseModel):
    """Parsed alert from Discord"""
    id: str = Field(default_factory=lambda: f"alert_{datetime.utcnow().timestamp()}")
    
    # Parsed data
    ticker: str
    strike: float
    option_type: str  # CALL or PUT
    expiration: str
    entry_price: float
    
    # Alert type
    alert_type: str = AlertType.BUY.value
    
    # Additional
    sell_percentage: Optional[float] = None
    
    # Metadata
    raw_message: str = ""
    channel_name: str = ""
    user_name: str = ""
    message_id: str = ""
    received_at: datetime = Field(default_factory=datetime.utcnow)
    processed: bool = False
    trade_executed: bool = False
    trade_result: Optional[str] = None
    
    class Config:
        use_enum_values = True


# ============= ORDERS =============

class Order(BaseModel):
    """Broker order"""
    id: str = Field(default_factory=lambda: f"order_{datetime.utcnow().timestamp()}")
    alert_id: str = ""
    
    # Order details
    ticker: str
    strike: float
    option_type: str
    expiration: str
    side: str = OrderSide.BUY.value
    quantity: int = 1
    order_type: str = OrderType.LIMIT.value
    
    # Pricing (with buffer applied)
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    
    # Original alert price
    alert_price: float = 0.0
    buffer_applied: float = 0.0
    
    # Status
    status: str = "pending"  # pending, submitted, filled, cancelled, expired
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    filled_price: Optional[float] = None
    filled_quantity: int = 0
    
    # Broker info
    broker_order_id: str = ""
    broker_error: Optional[str] = None
    
    class Config:
        use_enum_values = True


# ============= POSITIONS =============

class Position(BaseModel):
    """Open position"""
    id: str = Field(default_factory=lambda: f"pos_{datetime.utcnow().timestamp()}")
    order_id: str = ""
    alert_id: str = ""
    
    # Position details
    ticker: str
    strike: float
    option_type: str
    expiration: str
    quantity: int
    
    # Entry
    entry_price: float
    entry_buffer: float = 0.0
    filled_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Bracket order
    profit_target: Optional[float] = None
    stop_loss: Optional[float] = None
    trailing_stop_enabled: bool = False
    trailing_percentage: float = 25.0
    
    # Tracking
    current_price: float = 0.0
    peak_price: float = 0.0
    
    # Status
    status: str = PositionStatus.OPEN.value
    closed_at: Optional[datetime] = None
    close_reason: str = ""
    realized_pnl: float = 0.0
    
    # Updated
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True
    
    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized P&L"""
        if self.current_price:
            return (self.current_price - self.entry_price) * self.quantity * 100
        return 0.0


# ============= FILLED ALERT =============

class FilledAlert(BaseModel):
    """Track filled trade alerts for history"""
    id: str = Field(default_factory=lambda: f"filled_{datetime.utcnow().timestamp()}")
    
    # Alert info
    alert_id: str
    ticker: str
    strike: float
    option_type: str
    expiration: str
    alert_type: str
    alert_price: float
    
    # Order info
    order_id: str = ""
    broker_order_id: str = ""
    
    # Fill info
    quantity: int
    filled_price: float
    buffer_saved: float = 0.0
    
    # Position
    position_id: str = ""
    
    # Times
    received_at: datetime = Field(default_factory=datetime.utcnow)
    filled_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


# ============= BOT STATUS =============

class BotStatus(BaseModel):
    """Bot runtime status"""
    # Discord
    discord_connected: bool = False
    discord_channels: List[str] = []
    
    # Broker
    broker_connected: bool = False
    broker_name: str = ""
    
    # Trading
    auto_trading_enabled: bool = True
    simulation_mode: bool = False
    
    # Statistics
    alerts_processed: int = 0
    trades_executed: int = 0
    trades_failed: int = 0
    
    # Positions
    open_positions: int = 0
    
    # Runtime
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_alert_time: Optional[datetime] = None
    
    class Config:
        use_enum_values = True


# ============= API RESPONSE MODELS =============

class TradeRequest(BaseModel):
    """Request to execute a trade"""
    ticker: str
    strike: float
    option_type: str = OptionType.CALL.value
    expiration: str
    quantity: int = 1
    side: str = OrderSide.BUY.value
    
    # Pricing
    entry_price: float
    use_buffer: bool = True
    buffer_percentage: float = 3.0
    
    # Bracket
    profit_target: Optional[float] = None
    stop_loss: Optional[float] = None
    use_trailing_stop: bool = False
    trailing_percentage: float = 25.0
    
    # Execution
    broker_id: Optional[str] = None
    simulation: bool = False


class TradeResponse(BaseModel):
    """Response from trade execution"""
    success: bool
    message: str
    order_id: Optional[str] = None
    position_id: Optional[str] = None
    filled_price: Optional[float] = None
    buffer_saved: Optional[float] = None
    
    class Config:
        use_enum_values = True


class StatusResponse(BaseModel):
    """Status response"""
    status: str
    discord_connected: bool
    broker_connected: bool
    auto_trading: bool
    simulation: bool
    open_positions: int
    alerts_processed: int
    trades_executed: int
    uptime_seconds: int
