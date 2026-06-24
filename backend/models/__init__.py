from pydantic import BaseModel, Field, SecretStr
from typing import List, Dict, Optional, Annotated
from datetime import datetime, timezone
from enum import Enum
import uuid


class BrokerType(str, Enum):
    IBKR = "ibkr"
    ALPACA = "alpaca"
    TD_AMERITRADE = "td_ameritrade"
    TRADIER = "tradier"
    WEBULL = "webull"
    ROBINHOOD = "robinhood"
    TRADESTATION = "tradestation"
    THINKORSWIM = "thinkorswim"
    WEALTHSIMPLE = "wealthsimple"


class BrokerConfig(BaseModel):
    broker_type: BrokerType
    enabled: bool = False
    api_key: SecretStr = SecretStr("")
    api_secret: SecretStr = SecretStr("")
    gateway_url: str = "https://localhost:5000"
    account_id: str = ""
    base_url: str = "https://paper-api.alpaca.markets"
    refresh_token: SecretStr = SecretStr("")
    client_id: str = ""
    access_token: SecretStr = SecretStr("")
    device_id: str = ""
    trade_token: SecretStr = SecretStr("")
    username: str = ""
    password: SecretStr = SecretStr("")
    mfa_code: SecretStr = SecretStr("")
    ts_client_id: str = ""
    ts_client_secret: str = ""
    ts_redirect_uri: str = "http://localhost:3000/callback"
    ts_refresh_token: str = ""
    tos_consumer_key: str = ""
    tos_redirect_uri: str = "http://localhost:3000/callback"
    tos_refresh_token: str = ""
    tos_account_id: str = ""
    ws_email: str = ""
    ws_password: str = ""
    ws_otp_code: str = ""
    nickname: str = ""  # Optional nickname for this broker config
    model_config = {"extra": "ignore"}


# Profile system for multiple accounts
class BrokerSettings(BaseModel):
    """Per-broker risk management settings"""
    # Broker identification
    broker_id: str = ""
    enabled: bool = False  # Whether this broker is active in the profile
    
    # Trading mode
    auto_trading_enabled: bool = True
    alerts_only: bool = False  # If true, only receive alerts, no auto-execution
    
    # Premium Buffer
    premium_buffer_enabled: bool = False
    premium_buffer_amount: float = 10.0  # cents
    
    # Averaging Down
    averaging_down_enabled: bool = False
    price_drop_threshold: float = 10.0
    buy_percentage: float = 25.0
    max_average_downs: int = 3
    
    # Take Profit
    take_profit_enabled: bool = False
    take_profit_percentage: float = 50.0
    bracket_order_enabled: bool = False
    
    # Stop Loss
    stop_loss_enabled: bool = False
    stop_loss_percentage: float = 25.0
    stop_loss_order_type: str = "market"  # "market" or "limit"
    
    # Trailing Stop
    trailing_stop_enabled: bool = False
    trailing_stop_type: str = "percent"  # "percent" or "premium"
    trailing_stop_percent: float = 10.0
    trailing_stop_cents: float = 50.0
    
    # Auto Shutdown
    auto_shutdown_enabled: bool = False
    max_consecutive_losses: int = 3
    max_daily_losses: int = 5
    max_daily_loss_amount: float = 500.0


# Keep ProfileSettings for backwards compatibility
class ProfileSettings(BaseModel):
    """Per-profile risk management settings (deprecated, use BrokerSettings)"""
    auto_trading_enabled: bool = True
    alerts_only: bool = False
    premium_buffer_enabled: bool = False
    premium_buffer_amount: float = 10.0
    averaging_down_enabled: bool = False
    price_drop_threshold: float = 10.0
    buy_percentage: float = 25.0
    max_average_downs: int = 3
    take_profit_enabled: bool = False
    take_profit_percentage: float = 50.0
    bracket_order_enabled: bool = False
    stop_loss_enabled: bool = False
    stop_loss_percentage: float = 25.0
    stop_loss_order_type: str = "market"
    trailing_stop_enabled: bool = False
    trailing_stop_type: str = "percent"
    trailing_stop_percent: float = 10.0
    trailing_stop_cents: float = 50.0
    auto_shutdown_enabled: bool = False
    max_consecutive_losses: int = 3
    max_daily_losses: int = 5
    max_daily_loss_amount: float = 500.0


class Profile(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Default Profile"
    description: str = ""
    active_brokers: List[str] = []  # List of broker_type values that are active
    broker_settings: Dict[str, BrokerSettings] = {}  # Per-broker settings keyed by broker_id
    settings: ProfileSettings = Field(default_factory=ProfileSettings)  # Legacy fallback
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_active: bool = False


class ProfileCreate(BaseModel):
    name: str
    description: str = ""


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    active_brokers: Optional[List[str]] = None


class BrokerSettingsUpdate(BaseModel):
    """Update per-broker settings"""
    enabled: Optional[bool] = None
    auto_trading_enabled: Optional[bool] = None
    alerts_only: Optional[bool] = None
    premium_buffer_enabled: Optional[bool] = None
    premium_buffer_amount: Optional[float] = None
    averaging_down_enabled: Optional[bool] = None
    price_drop_threshold: Optional[float] = None
    buy_percentage: Optional[float] = None
    max_average_downs: Optional[int] = None
    take_profit_enabled: Optional[bool] = None
    take_profit_percentage: Optional[float] = None
    bracket_order_enabled: Optional[bool] = None
    stop_loss_enabled: Optional[bool] = None
    stop_loss_percentage: Optional[float] = None
    stop_loss_order_type: Optional[str] = None
    trailing_stop_enabled: Optional[bool] = None
    trailing_stop_type: Optional[str] = None
    trailing_stop_percent: Optional[float] = None
    trailing_stop_cents: Optional[float] = None
    auto_shutdown_enabled: Optional[bool] = None
    max_consecutive_losses: Optional[int] = None
    max_daily_losses: Optional[int] = None
    max_daily_loss_amount: Optional[float] = None


class ProfileSettingsUpdate(BaseModel):
    """Update per-profile settings"""
    auto_trading_enabled: Optional[bool] = None
    alerts_only: Optional[bool] = None
    premium_buffer_enabled: Optional[bool] = None
    premium_buffer_amount: Optional[float] = None
    averaging_down_enabled: Optional[bool] = None
    price_drop_threshold: Optional[float] = None
    buy_percentage: Optional[float] = None
    max_average_downs: Optional[int] = None
    take_profit_enabled: Optional[bool] = None
    take_profit_percentage: Optional[float] = None
    bracket_order_enabled: Optional[bool] = None
    stop_loss_enabled: Optional[bool] = None
    stop_loss_percentage: Optional[float] = None
    stop_loss_order_type: Optional[str] = None
    trailing_stop_enabled: Optional[bool] = None
    trailing_stop_type: Optional[str] = None
    trailing_stop_percent: Optional[float] = None
    trailing_stop_cents: Optional[float] = None
    auto_shutdown_enabled: Optional[bool] = None
    max_consecutive_losses: Optional[int] = None
    max_daily_losses: Optional[int] = None
    max_daily_loss_amount: Optional[float] = None


class Alert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticker: str
    strike: float
    option_type: str
    expiration: str
    entry_price: float
    alert_type: str = "buy"
    sell_percentage: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    processed: bool = False
    trade_executed: bool = False
    trade_result: Optional[str] = None
    raw_message: Optional[str] = None


class Trade(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    alert_id: Optional[str] = None
    ticker: str = Field(min_length=1, max_length=10)
    strike: float = Field(gt=0)
    option_type: str
    expiration: str
    entry_price: float = Field(gt=0)
    exit_price: Optional[float] = Field(default=None, gt=0)
    current_price: Optional[float] = Field(default=None, gt=0)
    quantity: int = Field(default=1, ge=1)
    side: str = "BUY"
    status: str = "pending"
    broker: str = "ibkr"
    order_id: Optional[str] = None
    executed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    simulated: bool = True
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0


class Position(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ticker: str = Field(min_length=1, max_length=10)
    strike: float = Field(gt=0)
    option_type: str
    expiration: str
    entry_price: float = Field(gt=0)
    current_price: Optional[float] = Field(default=None, gt=0)
    original_quantity: int = Field(default=1, ge=1)
    remaining_quantity: int = Field(default=1, ge=0)
    total_cost: float = 0.0
    broker: str = "ibkr"
    status: str = "open"
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    simulated: bool = True
    trade_ids: List[str] = []
    average_down_count: int = 0
    initial_entry_price: Optional[float] = None
    highest_price: Optional[float] = None


class OperatorEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    category: str = Field(min_length=1, max_length=50)
    action: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=240)
    severity: str = "info"
    details: Dict[str, object] = Field(default_factory=dict)


class Settings(BaseModel):
    id: str = "main_settings"
    discord_token: str = ""
    discord_channel_ids: List[str] = []
    source_overrides: Dict[str, dict] = {}
    chrome_bridge_require_source_override: bool = True
    active_broker: BrokerType = BrokerType.IBKR
    broker_configs: Dict[str, BrokerConfig] = {}
    auto_trading_enabled: bool = True
    premium_buffer_enabled: bool = False
    premium_buffer_amount: float = 10.0  # Buffer in cents (e.g., 10 = $0.10)
    default_quantity: int = 1
    simulation_mode: bool = True
    max_position_size: float = 1000.0
    risk_per_trade: float = 1.0
    max_drawdown_percent: float = 20.0
    max_positions_per_ticker: int = 3
    max_positions_per_sector: int = 3
    averaging_down_enabled: bool = False
    averaging_down_threshold: float = 10.0
    averaging_down_percentage: float = 25.0
    averaging_down_max_buys: int = 3
    take_profit_enabled: bool = False
    take_profit_percentage: float = 50.0
    bracket_order_enabled: bool = False
    stop_loss_enabled: bool = False
    stop_loss_percentage: float = 25.0
    stop_loss_order_type: str = "market"  # "market" or "limit"
    trailing_stop_enabled: bool = False
    trailing_stop_type: str = "percent"
    trailing_stop_percent: float = 10.0
    trailing_stop_cents: float = 50.0
    trailing_hours: float = 4.0
    # Auto shutdown settings
    auto_shutdown_enabled: bool = False
    max_consecutive_losses: int = 3
    max_daily_losses: int = 5
    max_daily_loss_amount: float = 500.0
    # Tracking
    consecutive_losses: int = 0
    daily_losses: int = 0
    daily_loss_amount: float = 0.0
    last_loss_reset_date: str = ""
    shutdown_triggered: bool = False
    shutdown_reason: str = ""
    model_config = {"extra": "ignore"}


class SettingsUpdate(BaseModel):
    discord_token: Optional[str] = None
    discord_channel_ids: Optional[List[str]] = None
    source_overrides: Optional[Dict[str, dict]] = None
    chrome_bridge_require_source_override: Optional[bool] = None
    active_broker: Optional[BrokerType] = None
    broker_configs: Optional[Dict[str, dict]] = None
    auto_trading_enabled: Optional[bool] = None
    default_quantity: Optional[int] = Field(default=None, ge=1)
    simulation_mode: Optional[bool] = None
    max_position_size: Optional[float] = Field(default=None, gt=0)
    risk_per_trade: Optional[float] = Field(default=None, gt=0)
    max_drawdown_percent: Optional[float] = Field(default=None, gt=0)
    max_positions_per_ticker: Optional[int] = Field(default=None, ge=0)
    max_positions_per_sector: Optional[int] = Field(default=None, ge=0)
    averaging_down_enabled: Optional[bool] = None
    averaging_down_threshold: Optional[float] = Field(default=None, ge=0)
    averaging_down_percentage: Optional[float] = Field(default=None, ge=0)
    averaging_down_max_buys: Optional[int] = Field(default=None, ge=0)
    take_profit_enabled: Optional[bool] = None
    take_profit_percentage: Optional[float] = Field(default=None, gt=0)
    stop_loss_enabled: Optional[bool] = None
    stop_loss_percentage: Optional[float] = Field(default=None, gt=0)
    trailing_stop_enabled: Optional[bool] = None
    trailing_stop_type: Optional[str] = None
    trailing_stop_percent: Optional[float] = Field(default=None, gt=0)
    trailing_stop_cents: Optional[float] = Field(default=None, gt=0)
    trailing_hours: Optional[float] = Field(default=None, gt=0)


class BrokerInfo(BaseModel):
    id: str
    name: str
    description: str
    supports_options: bool
    requires_gateway: bool
    config_fields: List[dict]


class AveragingDownSettingsUpdate(BaseModel):
    averaging_down_enabled: Optional[bool] = None
    averaging_down_threshold: Optional[float] = Field(default=None, ge=0)
    averaging_down_percentage: Optional[float] = Field(default=None, ge=0)
    averaging_down_max_buys: Optional[int] = Field(default=None, ge=0)


class RiskManagementSettingsUpdate(BaseModel):
    take_profit_enabled: Optional[bool] = None
    take_profit_percentage: Optional[float] = Field(default=None, gt=0)
    bracket_order_enabled: Optional[bool] = None
    stop_loss_enabled: Optional[bool] = None
    stop_loss_percentage: Optional[float] = Field(default=None, gt=0)
    stop_loss_order_type: Optional[str] = None


class TrailingStopSettingsUpdate(BaseModel):
    trailing_stop_enabled: Optional[bool] = None
    trailing_stop_type: Optional[str] = None
    trailing_stop_percent: Optional[float] = Field(default=None, gt=0)
    trailing_stop_cents: Optional[float] = Field(default=None, gt=0)


class AutoShutdownSettingsUpdate(BaseModel):
    auto_shutdown_enabled: Optional[bool] = None
    max_consecutive_losses: Optional[int] = None
    max_daily_losses: Optional[int] = None
    max_daily_loss_amount: Optional[float] = None



# Discord Alert Patterns - Customizable keywords for parsing alerts
class DiscordAlertPatterns(BaseModel):
    """Customizable patterns for parsing Discord alerts"""
    # Buy patterns - any of these trigger a buy
    buy_patterns: List[str] = [
        "BUY", "BUYING", "BOUGHT", "ENTRY", "ENTERING", "LONG", "GOING LONG",
        "BTO", "BUY TO OPEN", "OPENING", "NEW POSITION", "SCALP", "LOTTO"
    ]
    
    # Sell patterns - any of these trigger a sell
    sell_patterns: List[str] = [
        "SELL", "SELLING", "SOLD", "EXIT", "EXITING", "CLOSE", "CLOSING",
        "STC", "SELL TO CLOSE", "TRIM", "TRIMMING", "OUT", "PROFIT", "TAKING PROFIT"
    ]
    
    # Partial sell patterns - these trigger partial sells
    partial_sell_patterns: List[str] = [
        "SELL HALF", "HALF OUT", "50%", "TRIM HALF", "PARTIAL",
        "SELL 25%", "SELL 50%", "SELL 75%", "QUARTER OUT"
    ]
    
    # Average down patterns - trigger averaging down
    average_down_patterns: List[str] = [
        "AVERAGE DOWN", "AVG DOWN", "AVERAGING", "ADD TO", "ADDING",
        "DOUBLE DOWN", "LOWERING AVERAGE", "COST BASIS"
    ]
    
    # Stop loss patterns - mentioned stop levels
    stop_loss_patterns: List[str] = [
        "STOP", "SL", "STOP LOSS", "STOPPED OUT", "STOP AT", "STOP @"
    ]
    
    # Take profit patterns - mentioned profit targets
    take_profit_patterns: List[str] = [
        "TARGET", "TP", "TAKE PROFIT", "PT", "PRICE TARGET", "GOAL"
    ]
    
    # Ignore patterns - messages containing these are skipped
    ignore_patterns: List[str] = [
        "WATCHLIST", "WATCHING", "MIGHT", "MAYBE", "CONSIDERING",
        "IF", "WOULD", "COULD", "POSSIBLY", "PAPER", "DEMO"
    ]
    
    # Custom ticker extraction pattern (regex)
    ticker_pattern: str = r'\$([A-Z]{1,5})\b'
    
    # Case sensitive matching
    case_sensitive: bool = False


class DiscordAlertPatternsUpdate(BaseModel):
    """Update Discord alert patterns"""
    buy_patterns: Optional[List[str]] = None
    sell_patterns: Optional[List[str]] = None
    partial_sell_patterns: Optional[List[str]] = None
    average_down_patterns: Optional[List[str]] = None
    stop_loss_patterns: Optional[List[str]] = None
    take_profit_patterns: Optional[List[str]] = None
    ignore_patterns: Optional[List[str]] = None
    ticker_pattern: Optional[str] = None
    case_sensitive: Optional[bool] = None
