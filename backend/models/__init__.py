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
    take_profit_sell_percentage: float = 100.0
    bracket_order_enabled: bool = False
    break_even_enabled: bool = False
    break_even_activation_type: str = "percent"
    break_even_activation_percentage: float = 10.0
    break_even_activation_cents: float = 10.0
    
    # Stop Loss
    stop_loss_enabled: bool = False
    stop_loss_percentage: float = 25.0
    stop_loss_order_type: str = "market"  # "market" or "limit"
    
    # Trailing Stop
    trailing_stop_enabled: bool = False
    trailing_stop_type: str = "percent"  # "percent" or "premium"
    trailing_stop_percent: float = 10.0
    trailing_stop_activation_percent: float = 10.0
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
    take_profit_sell_percentage: float = 100.0
    bracket_order_enabled: bool = False
    break_even_enabled: bool = False
    break_even_activation_type: str = "percent"
    break_even_activation_percentage: float = 10.0
    break_even_activation_cents: float = 10.0
    stop_loss_enabled: bool = False
    stop_loss_percentage: float = 25.0
    stop_loss_order_type: str = "market"
    trailing_stop_enabled: bool = False
    trailing_stop_type: str = "percent"
    trailing_stop_percent: float = 10.0
    trailing_stop_activation_percent: float = 10.0
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
    take_profit_sell_percentage: Optional[float] = None
    bracket_order_enabled: Optional[bool] = None
    break_even_enabled: Optional[bool] = None
    break_even_activation_type: Optional[str] = None
    break_even_activation_percentage: Optional[float] = None
    break_even_activation_cents: Optional[float] = None
    stop_loss_enabled: Optional[bool] = None
    stop_loss_percentage: Optional[float] = None
    stop_loss_order_type: Optional[str] = None
    trailing_stop_enabled: Optional[bool] = None
    trailing_stop_type: Optional[str] = None
    trailing_stop_percent: Optional[float] = None
    trailing_stop_activation_percent: Optional[float] = None
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
    take_profit_sell_percentage: Optional[float] = None
    bracket_order_enabled: Optional[bool] = None
    break_even_enabled: Optional[bool] = None
    break_even_activation_type: Optional[str] = None
    break_even_activation_percentage: Optional[float] = None
    break_even_activation_cents: Optional[float] = None
    stop_loss_enabled: Optional[bool] = None
    stop_loss_percentage: Optional[float] = None
    stop_loss_order_type: Optional[str] = None
    trailing_stop_enabled: Optional[bool] = None
    trailing_stop_type: Optional[str] = None
    trailing_stop_percent: Optional[float] = None
    trailing_stop_activation_percent: Optional[float] = None
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
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    source_name: Optional[str] = None
    source_label: Optional[str] = None
    skip_reason: Optional[str] = None
    trade_request_reason: Optional[str] = None
    exit_trigger: Optional[str] = None
    exit_trigger_detail: Optional[str] = None
    card_action: Optional[dict] = None


class Trade(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    alert_id: Optional[str] = None
    position_id: Optional[str] = None
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
    simulated: bool = False
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    sell_percentage: Optional[float] = None
    exit_trigger: Optional[str] = None
    exit_reason: Optional[str] = None
    exit_allocation_target: Optional[str] = None
    target_remaining_quantity: Optional[int] = Field(default=None, ge=0)
    exit_runner_audit: Dict[str, object] = Field(default_factory=dict)
    entry_alignment_tier: Optional[str] = None
    entry_alignment_score: Optional[float] = None
    entry_sizing_percent: Optional[float] = None
    entry_alignment_context: Dict[str, object] = Field(default_factory=dict)
    entry_risk_profile: str = "normal"
    entry_exit_profile: str = "standard"
    max_loss_budget: Optional[float] = None
    estimated_stop_loss_percent: Optional[float] = None
    source_reported_stop_price: Optional[float] = None
    source_reported_stop_percent: Optional[float] = None
    source_reported_break_even_stop: bool = False


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
    simulated: bool = False
    trade_ids: List[str] = []
    average_down_count: int = 0
    initial_entry_price: Optional[float] = None
    highest_price: Optional[float] = None
    highest_executable_bid: Optional[float] = None
    entry_risk_profile: str = "normal"
    entry_exit_profile: str = "standard"
    max_loss_budget: Optional[float] = None
    estimated_stop_loss_percent: Optional[float] = None
    profit_stage_1_completed: bool = False
    profit_stage_1_completed_at: Optional[datetime] = None
    profit_stage_2_completed: bool = False
    profit_stage_2_completed_at: Optional[datetime] = None
    profit_floor_armed: bool = False
    profit_floor_price: Optional[float] = None
    profit_floor_armed_at: Optional[datetime] = None
    coordinated_exit_tier: Optional[str] = None
    coordinated_trailing_armed: bool = False
    coordinated_trailing_step: int = 0
    coordinated_effective_trailing_percent: Optional[float] = None
    coordinated_premium_volatility_percent: Optional[float] = None
    coordinated_trailing_floor: Optional[float] = None
    coordinated_break_even_armed: bool = False
    coordinated_break_even_floor: Optional[float] = None
    coordinated_loss_ladder_completed_steps: List[int] = []
    coordinated_loss_ladder_pending_step: Optional[int] = None
    coordinated_loss_ladder_target_quantity: int = 0
    coordinated_loss_ladder_sold_quantity: int = 0
    source_reported_stop_price: Optional[float] = None
    source_reported_stop_percent: Optional[float] = None
    source_reported_break_even_stop: bool = False
    option_bid: Optional[float] = None
    option_ask: Optional[float] = None
    option_quote_observed_at: Optional[datetime] = None
    exit_order_pending: bool = False
    exit_order_id: Optional[str] = None
    exit_reservation_token: Optional[str] = None
    exit_target_remaining_quantity: Optional[int] = None
    exit_target_trigger: Optional[str] = None
    exit_target_updated_at: Optional[datetime] = None
    post_exit_last_bid: Optional[float] = None
    post_exit_highest_bid: Optional[float] = None
    post_exit_highest_return_percent: Optional[float] = None
    post_exit_quote_observed_at: Optional[datetime] = None
    post_exit_telemetry_until: Optional[datetime] = None


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
    discord_communities: List[Dict[str, object]] = []
    discord_parser_requirements: Dict[str, object] = {}
    discord_filters: Dict[str, object] = {}
    source_overrides: Dict[str, dict] = {}
    chrome_bridge_require_source_override: bool = True
    active_broker: BrokerType = BrokerType.IBKR
    broker_configs: Dict[str, BrokerConfig] = {}
    auto_trading_enabled: bool = True
    sell_alert_listening_enabled: bool = True
    trim_alert_listening_enabled: bool = True
    premium_buffer_enabled: bool = False
    premium_buffer_amount: float = 10.0  # Buffer in cents (e.g., 10 = $0.10)
    default_quantity: int = 1
    smart_sizing_enabled: bool = True
    smart_sizing_agreement_percent: float = 100.0
    smart_sizing_mixed_percent: float = 50.0
    smart_sizing_conflict_percent: float = 25.0
    entry_slippage_sizing_enabled: bool = True
    entry_slippage_mode: str = Field(default="tiered", pattern=r"^(disabled|binary|tiered)$")
    entry_slippage_warning_percent: float = Field(default=10.0, gt=0)
    entry_slippage_severe_percent: float = Field(default=20.0, gt=0)
    entry_slippage_warning_size_percent: float = Field(default=50.0, gt=0, le=100)
    entry_slippage_severe_size_percent: float = Field(default=25.0, gt=0, le=100)
    marketable_entry_enabled: bool = True
    simulation_mode: bool = False
    max_position_size: float = 1000.0
    risk_per_trade: float = 1.0
    risk_budget_sizing_enabled: bool = True
    max_loss_per_trade: float = Field(default=100.0, gt=0)
    max_drawdown_percent: float = 20.0
    max_positions_per_ticker: int = 3
    max_positions_per_sector: int = 3
    averaging_down_enabled: bool = False
    averaging_down_threshold: float = 10.0
    averaging_down_percentage: float = 25.0
    averaging_down_max_buys: int = 3
    take_profit_enabled: bool = False
    take_profit_percentage: float = 50.0
    take_profit_sell_percentage: float = 100.0
    bracket_order_enabled: bool = False
    break_even_enabled: bool = False
    break_even_activation_type: str = "percent"
    break_even_activation_percentage: float = 10.0
    break_even_activation_cents: float = 10.0
    stop_loss_enabled: bool = False
    stop_loss_percentage: float = 25.0
    stop_loss_order_type: str = "market"  # "market" or "limit"
    trailing_stop_enabled: bool = False
    trailing_stop_type: str = "percent"
    trailing_stop_percent: float = 10.0
    trailing_stop_activation_percent: float = 10.0
    trailing_stop_cents: float = 50.0
    trailing_hours: float = 4.0
    coordinated_exit_enabled: bool = True
    coordinated_exit_quote_max_age_seconds: float = Field(default=15.0, gt=0)
    post_exit_telemetry_enabled: bool = True
    post_exit_telemetry_minutes: int = Field(default=60, ge=1, le=1440)
    coordinated_normal_stop_loss_percent: float = Field(default=35.0, gt=0, le=100)
    coordinated_high_risk_stop_loss_percent: float = Field(default=50.0, gt=0, le=100)
    coordinated_high_risk_size_percent: float = Field(default=25.0, gt=0, le=100)
    coordinated_emergency_stop_loss_percent: float = Field(default=50.0, gt=0, le=100)
    coordinated_stop_required_confirmations: int = Field(default=2, ge=1, le=10)
    coordinated_stop_confirmation_interval_seconds: float = Field(default=1.0, gt=0, le=60)
    coordinated_break_even_required_confirmations: int = Field(default=2, ge=1, le=10)
    coordinated_break_even_confirmation_interval_seconds: float = Field(default=1.0, gt=0, le=60)
    coordinated_break_even_preserve_runner: bool = True
    coordinated_runner_reserve_quantity: int = Field(default=1, ge=0, le=100)
    coordinated_profit_stage_1_percent: float = Field(default=25.0, gt=0)
    coordinated_profit_stage_1_sell_percent: float = Field(default=50.0, gt=0, le=100)
    coordinated_profit_stage_2_percent: float = Field(default=35.0, gt=0)
    coordinated_profit_stage_2_sell_percent: float = Field(default=25.0, gt=0, le=100)
    coordinated_fast_scalp_profit_stage_1_percent: float = Field(default=10.0, gt=0)
    coordinated_fast_scalp_profit_stage_2_percent: float = Field(default=20.0, gt=0)
    coordinated_swing_activation_percent: float = Field(default=30.0, gt=0)
    coordinated_swing_trailing_percent: float = Field(default=25.0, gt=0, le=100)
    coordinated_swing_break_even_activation_percent: float = Field(default=30.0, gt=0)
    coordinated_swing_profit_stage_1_percent: float = Field(default=50.0, gt=0)
    coordinated_swing_profit_stage_2_percent: float = Field(default=100.0, gt=0)
    coordinated_low_premium_threshold: float = Field(default=0.30, gt=0)
    coordinated_medium_premium_threshold: float = Field(default=1.00, gt=0)
    coordinated_low_activation_percent: float = Field(default=15.0, gt=0)
    coordinated_low_min_activation_cents: float = Field(default=3.0, gt=0)
    coordinated_low_trailing_percent: float = Field(default=15.0, gt=0, le=100)
    coordinated_low_min_trailing_cents: float = Field(default=3.0, gt=0)
    coordinated_low_break_even_activation_percent: float = Field(default=15.0, gt=0)
    coordinated_medium_activation_percent: float = Field(default=20.0, gt=0)
    coordinated_medium_trailing_percent: float = Field(default=15.0, gt=0, le=100)
    coordinated_medium_break_even_activation_percent: float = Field(default=20.0, gt=0)
    coordinated_high_activation_percent: float = Field(default=12.0, gt=0)
    coordinated_high_trailing_percent: float = Field(default=10.0, gt=0, le=100)
    coordinated_high_break_even_activation_percent: float = Field(default=12.0, gt=0)
    coordinated_progressive_trailing_enabled: bool = True
    coordinated_trailing_mode: str = Field(default="tightening", pattern=r"^(fixed|tightening|elastic)$")
    coordinated_trailing_step_gain_percent: float = Field(default=10.0, gt=0)
    coordinated_trailing_step_tighten_percent: float = Field(default=1.0, gt=0)
    coordinated_trailing_min_percent: float = Field(default=8.0, gt=0, le=100)
    coordinated_trailing_volatility_gate_percent: float = Field(default=8.0, gt=0)
    coordinated_elastic_activation_percent: float = Field(default=5.0, ge=0, le=100)
    coordinated_elastic_min_activation_cents: float = Field(default=3.0, ge=0)
    coordinated_elastic_trailing_start_percent: float = Field(default=6.0, gt=0, le=100)
    coordinated_elastic_trailing_step_gain_percent: float = Field(default=10.0, gt=0)
    coordinated_elastic_trailing_step_widen_percent: float = Field(default=1.0, gt=0)
    coordinated_elastic_trailing_max_percent: float = Field(default=10.0, gt=0, le=100)
    coordinated_trailing_spread_multiplier: float = Field(default=2.0, ge=0, le=10)
    coordinated_loss_ladder_enabled: bool = True
    coordinated_loss_ladder: List[Dict[str, object]] = Field(
        default_factory=lambda: [
            {"loss_percent": 12.0, "quantity_mode": "percent_original", "quantity": 10.0, "confirmations": 2},
            {"loss_percent": 18.0, "quantity_mode": "percent_original", "quantity": 20.0, "confirmations": 2},
            {"loss_percent": 25.0, "quantity_mode": "percent_original", "quantity": 30.0, "confirmations": 2},
            {"loss_percent": 35.0, "quantity_mode": "percent_remaining", "quantity": 100.0, "confirmations": 1},
        ]
    )
    core_runner_enabled: bool = False
    core_runner_allocation_mode: str = Field(default="greater_of", pattern=r"^(percent|fixed|greater_of)$")
    core_runner_allocation_percent: float = Field(default=20.0, ge=0, le=100)
    core_runner_fixed_contracts: int = Field(default=1, ge=0, le=1000)
    core_runner_min_contracts: int = Field(default=1, ge=0, le=1000)
    core_runner_max_contracts: int = Field(default=2, ge=0, le=1000)
    core_runner_allow_single_contract: bool = False
    core_runner_activation_mfe_percent: float = Field(default=100.0, ge=0)
    core_runner_reserve_candidates_from_profit: bool = True
    core_runner_loss_ladder_consumes_candidates: bool = True
    core_runner_protect_loss_ladder: bool = True
    core_runner_protect_hard_stop: bool = True
    core_runner_protect_break_even: bool = True
    core_runner_protect_profit_stages: bool = True
    core_runner_protect_ordinary_trailing: bool = True
    core_runner_protect_reversal_warning: bool = True
    core_runner_protect_contextual_trims: bool = True
    core_runner_confirmed_reversal_exits: bool = True
    core_runner_catastrophic_stop_percent: float = Field(default=65.0, ge=0, le=100)
    core_runner_catastrophic_confirmations: int = Field(default=2, ge=1, le=10)
    core_runner_catastrophic_confirmation_interval_seconds: float = Field(default=3.0, gt=0, le=300)
    core_runner_trailing_enabled: bool = True
    core_runner_trailing_mode: str = Field(default="tiered", pattern=r"^(fixed|tiered|underlying_confirmed)$")
    core_runner_fixed_trailing_percent: float = Field(default=35.0, gt=0, le=100)
    core_runner_trailing_tiers: List[Dict[str, float]] = Field(
        default_factory=lambda: [
            {"mfe_percent": 100.0, "trail_percent": 35.0},
            {"mfe_percent": 300.0, "trail_percent": 30.0},
            {"mfe_percent": 500.0, "trail_percent": 25.0},
            {"mfe_percent": 1000.0, "trail_percent": 20.0},
        ]
    )
    core_runner_min_trailing_cents: float = Field(default=0.0, ge=0)
    core_runner_spread_multiplier: float = Field(default=2.0, ge=0, le=10)
    core_runner_trailing_confirmations: int = Field(default=2, ge=1, le=10)
    core_runner_trailing_confirmation_interval_seconds: float = Field(default=3.0, gt=0, le=300)
    core_runner_minimum_activation_seconds: int = Field(default=0, ge=0, le=86400)
    core_runner_require_fresh_high: bool = False
    core_runner_allow_floor_to_move_down: bool = False
    core_runner_analyst_override_percent: float = Field(default=80.0, ge=0, le=100)
    core_runner_explicit_full_exit_overrides: bool = True
    core_runner_contextual_full_exit_overrides: bool = False
    core_runner_zero_dte_liquidation_enabled: bool = True
    core_runner_zero_dte_liquidation_time: str = Field(default="15:40", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    reversal_exit_enabled: bool = True
    reversal_warning_confirmations: int = Field(default=3, ge=1, le=20)
    reversal_confirmed_confirmations: int = Field(default=5, ge=2, le=20)
    reversal_warning_sell_percent: float = Field(default=25.0, gt=0, le=100)
    reversal_premium_drawdown_percent: float = Field(default=12.0, gt=0, le=100)
    reversal_reduce_min_return_percent: float = Field(default=5.0, ge=0, le=100)
    reversal_reduce_min_mfe_percent: float = Field(default=20.0, ge=0)
    adaptive_trailing_enabled: bool = True
    adaptive_trailing_min_percent: float = Field(default=8.0, gt=0, le=100)
    adaptive_trailing_max_percent: float = Field(default=35.0, gt=0, le=100)
    zero_dte_liquidation_enabled: bool = True
    zero_dte_liquidation_time: str = Field(
        default="15:40",
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    )
    fill_confirmation_timeout_seconds: int = Field(default=180, ge=30, le=3600)
    fill_background_poll_interval_seconds: int = Field(default=15, ge=5, le=300)
    exit_reprice_interval_seconds: int = Field(default=5, ge=1, le=60)
    profit_exit_reprice_interval_seconds: int = Field(default=3, ge=1, le=120)
    profit_exit_marketable_offset_cents: float = Field(default=1.0, ge=0, le=25)
    # Auto shutdown settings
    auto_shutdown_enabled: bool = False
    max_consecutive_losses: int = 3
    max_daily_losses: int = 5
    max_daily_loss_amount: float = 250.0
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
    discord_communities: Optional[List[Dict[str, object]]] = None
    discord_parser_requirements: Optional[Dict[str, object]] = None
    discord_filters: Optional[Dict[str, object]] = None
    source_overrides: Optional[Dict[str, dict]] = None
    chrome_bridge_require_source_override: Optional[bool] = None
    active_broker: Optional[BrokerType] = None
    broker_configs: Optional[Dict[str, dict]] = None
    auto_trading_enabled: Optional[bool] = None
    sell_alert_listening_enabled: Optional[bool] = None
    trim_alert_listening_enabled: Optional[bool] = None
    default_quantity: Optional[int] = Field(default=None, ge=1)
    smart_sizing_enabled: Optional[bool] = None
    smart_sizing_agreement_percent: Optional[float] = Field(default=None, gt=0, le=100)
    smart_sizing_mixed_percent: Optional[float] = Field(default=None, gt=0, le=100)
    smart_sizing_conflict_percent: Optional[float] = Field(default=None, gt=0, le=100)
    entry_slippage_sizing_enabled: Optional[bool] = None
    entry_slippage_mode: Optional[str] = Field(default=None, pattern=r"^(disabled|binary|tiered)$")
    entry_slippage_warning_percent: Optional[float] = Field(default=None, gt=0)
    entry_slippage_severe_percent: Optional[float] = Field(default=None, gt=0)
    entry_slippage_warning_size_percent: Optional[float] = Field(default=None, gt=0, le=100)
    entry_slippage_severe_size_percent: Optional[float] = Field(default=None, gt=0, le=100)
    marketable_entry_enabled: Optional[bool] = None
    simulation_mode: Optional[bool] = None
    max_position_size: Optional[float] = Field(default=None, gt=0)
    risk_per_trade: Optional[float] = Field(default=None, gt=0)
    risk_budget_sizing_enabled: Optional[bool] = None
    max_loss_per_trade: Optional[float] = Field(default=None, gt=0)
    max_drawdown_percent: Optional[float] = Field(default=None, gt=0)
    max_positions_per_ticker: Optional[int] = Field(default=None, ge=0)
    max_positions_per_sector: Optional[int] = Field(default=None, ge=0)
    averaging_down_enabled: Optional[bool] = None
    averaging_down_threshold: Optional[float] = Field(default=None, ge=0)
    averaging_down_percentage: Optional[float] = Field(default=None, ge=0)
    averaging_down_max_buys: Optional[int] = Field(default=None, ge=0)
    take_profit_enabled: Optional[bool] = None
    take_profit_percentage: Optional[float] = Field(default=None, gt=0)
    take_profit_sell_percentage: Optional[float] = Field(default=None, gt=0, le=100)
    bracket_order_enabled: Optional[bool] = None
    break_even_enabled: Optional[bool] = None
    break_even_activation_type: Optional[str] = None
    break_even_activation_percentage: Optional[float] = Field(default=None, gt=0)
    break_even_activation_cents: Optional[float] = Field(default=None, gt=0)
    stop_loss_enabled: Optional[bool] = None
    stop_loss_percentage: Optional[float] = Field(default=None, gt=0)
    trailing_stop_enabled: Optional[bool] = None
    trailing_stop_type: Optional[str] = None
    trailing_stop_percent: Optional[float] = Field(default=None, gt=0)
    trailing_stop_activation_percent: Optional[float] = Field(default=None, ge=0, le=100)
    trailing_stop_cents: Optional[float] = Field(default=None, gt=0)
    trailing_hours: Optional[float] = Field(default=None, gt=0)
    coordinated_exit_enabled: Optional[bool] = None
    coordinated_exit_quote_max_age_seconds: Optional[float] = Field(default=None, gt=0)
    post_exit_telemetry_enabled: Optional[bool] = None
    post_exit_telemetry_minutes: Optional[int] = Field(default=None, ge=1, le=1440)
    coordinated_normal_stop_loss_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_high_risk_stop_loss_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_high_risk_size_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_emergency_stop_loss_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_stop_required_confirmations: Optional[int] = Field(default=None, ge=1, le=10)
    coordinated_stop_confirmation_interval_seconds: Optional[float] = Field(default=None, gt=0, le=60)
    coordinated_break_even_required_confirmations: Optional[int] = Field(default=None, ge=1, le=10)
    coordinated_break_even_confirmation_interval_seconds: Optional[float] = Field(default=None, gt=0, le=60)
    coordinated_break_even_preserve_runner: Optional[bool] = None
    coordinated_runner_reserve_quantity: Optional[int] = Field(default=None, ge=0, le=100)
    coordinated_profit_stage_1_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_profit_stage_1_sell_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_profit_stage_2_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_profit_stage_2_sell_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_fast_scalp_profit_stage_1_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_fast_scalp_profit_stage_2_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_swing_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_swing_trailing_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_swing_break_even_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_swing_profit_stage_1_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_swing_profit_stage_2_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_low_premium_threshold: Optional[float] = Field(default=None, gt=0)
    coordinated_medium_premium_threshold: Optional[float] = Field(default=None, gt=0)
    coordinated_low_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_low_min_activation_cents: Optional[float] = Field(default=None, gt=0)
    coordinated_low_trailing_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_low_min_trailing_cents: Optional[float] = Field(default=None, gt=0)
    coordinated_low_break_even_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_medium_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_medium_trailing_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_medium_break_even_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_high_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_high_trailing_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_high_break_even_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_progressive_trailing_enabled: Optional[bool] = None
    coordinated_trailing_mode: Optional[str] = Field(default=None, pattern=r"^(fixed|tightening|elastic)$")
    coordinated_trailing_step_gain_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_trailing_step_tighten_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_trailing_min_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_trailing_volatility_gate_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_elastic_activation_percent: Optional[float] = Field(default=None, ge=0, le=100)
    coordinated_elastic_min_activation_cents: Optional[float] = Field(default=None, ge=0)
    coordinated_elastic_trailing_start_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_elastic_trailing_step_gain_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_elastic_trailing_step_widen_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_elastic_trailing_max_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_trailing_spread_multiplier: Optional[float] = Field(default=None, ge=0, le=10)
    coordinated_loss_ladder_enabled: Optional[bool] = None
    coordinated_loss_ladder: Optional[List[Dict[str, object]]] = None
    core_runner_enabled: Optional[bool] = None
    core_runner_allocation_mode: Optional[str] = Field(default=None, pattern=r"^(percent|fixed|greater_of)$")
    core_runner_allocation_percent: Optional[float] = Field(default=None, ge=0, le=100)
    core_runner_fixed_contracts: Optional[int] = Field(default=None, ge=0, le=1000)
    core_runner_min_contracts: Optional[int] = Field(default=None, ge=0, le=1000)
    core_runner_max_contracts: Optional[int] = Field(default=None, ge=0, le=1000)
    core_runner_allow_single_contract: Optional[bool] = None
    core_runner_activation_mfe_percent: Optional[float] = Field(default=None, ge=0)
    core_runner_reserve_candidates_from_profit: Optional[bool] = None
    core_runner_loss_ladder_consumes_candidates: Optional[bool] = None
    core_runner_protect_loss_ladder: Optional[bool] = None
    core_runner_protect_hard_stop: Optional[bool] = None
    core_runner_protect_break_even: Optional[bool] = None
    core_runner_protect_profit_stages: Optional[bool] = None
    core_runner_protect_ordinary_trailing: Optional[bool] = None
    core_runner_protect_reversal_warning: Optional[bool] = None
    core_runner_protect_contextual_trims: Optional[bool] = None
    core_runner_confirmed_reversal_exits: Optional[bool] = None
    core_runner_catastrophic_stop_percent: Optional[float] = Field(default=None, ge=0, le=100)
    core_runner_catastrophic_confirmations: Optional[int] = Field(default=None, ge=1, le=10)
    core_runner_catastrophic_confirmation_interval_seconds: Optional[float] = Field(default=None, gt=0, le=300)
    core_runner_trailing_enabled: Optional[bool] = None
    core_runner_trailing_mode: Optional[str] = Field(default=None, pattern=r"^(fixed|tiered|underlying_confirmed)$")
    core_runner_fixed_trailing_percent: Optional[float] = Field(default=None, gt=0, le=100)
    core_runner_trailing_tiers: Optional[List[Dict[str, float]]] = None
    core_runner_min_trailing_cents: Optional[float] = Field(default=None, ge=0)
    core_runner_spread_multiplier: Optional[float] = Field(default=None, ge=0, le=10)
    core_runner_trailing_confirmations: Optional[int] = Field(default=None, ge=1, le=10)
    core_runner_trailing_confirmation_interval_seconds: Optional[float] = Field(default=None, gt=0, le=300)
    core_runner_minimum_activation_seconds: Optional[int] = Field(default=None, ge=0, le=86400)
    core_runner_require_fresh_high: Optional[bool] = None
    core_runner_allow_floor_to_move_down: Optional[bool] = None
    core_runner_analyst_override_percent: Optional[float] = Field(default=None, ge=0, le=100)
    core_runner_explicit_full_exit_overrides: Optional[bool] = None
    core_runner_contextual_full_exit_overrides: Optional[bool] = None
    core_runner_zero_dte_liquidation_enabled: Optional[bool] = None
    core_runner_zero_dte_liquidation_time: Optional[str] = Field(default=None, pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    reversal_exit_enabled: Optional[bool] = None
    reversal_warning_confirmations: Optional[int] = Field(default=None, ge=1, le=20)
    reversal_confirmed_confirmations: Optional[int] = Field(default=None, ge=2, le=20)
    reversal_warning_sell_percent: Optional[float] = Field(default=None, gt=0, le=100)
    reversal_premium_drawdown_percent: Optional[float] = Field(default=None, gt=0, le=100)
    reversal_reduce_min_return_percent: Optional[float] = Field(default=None, ge=0, le=100)
    reversal_reduce_min_mfe_percent: Optional[float] = Field(default=None, ge=0)
    adaptive_trailing_enabled: Optional[bool] = None
    adaptive_trailing_min_percent: Optional[float] = Field(default=None, gt=0, le=100)
    adaptive_trailing_max_percent: Optional[float] = Field(default=None, gt=0, le=100)
    fill_confirmation_timeout_seconds: Optional[int] = Field(default=None, ge=30, le=3600)
    fill_background_poll_interval_seconds: Optional[int] = Field(default=None, ge=5, le=300)
    exit_reprice_interval_seconds: Optional[int] = Field(default=None, ge=1, le=60)
    profit_exit_reprice_interval_seconds: Optional[int] = Field(default=None, ge=1, le=120)
    profit_exit_marketable_offset_cents: Optional[float] = Field(default=None, ge=0, le=25)
    zero_dte_liquidation_enabled: Optional[bool] = None
    zero_dte_liquidation_time: Optional[str] = Field(
        default=None,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    )


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
    take_profit_sell_percentage: Optional[float] = Field(default=None, gt=0, le=100)
    bracket_order_enabled: Optional[bool] = None
    break_even_enabled: Optional[bool] = None
    break_even_activation_type: Optional[str] = None
    break_even_activation_percentage: Optional[float] = Field(default=None, gt=0)
    break_even_activation_cents: Optional[float] = Field(default=None, gt=0)
    stop_loss_enabled: Optional[bool] = None
    stop_loss_percentage: Optional[float] = Field(default=None, gt=0)
    stop_loss_order_type: Optional[str] = None
    risk_budget_sizing_enabled: Optional[bool] = None
    max_loss_per_trade: Optional[float] = Field(default=None, gt=0)
    coordinated_exit_enabled: Optional[bool] = None
    coordinated_exit_quote_max_age_seconds: Optional[float] = Field(default=None, gt=0)
    coordinated_normal_stop_loss_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_high_risk_stop_loss_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_high_risk_size_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_emergency_stop_loss_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_stop_required_confirmations: Optional[int] = Field(default=None, ge=1, le=10)
    coordinated_stop_confirmation_interval_seconds: Optional[float] = Field(default=None, gt=0, le=60)
    coordinated_break_even_required_confirmations: Optional[int] = Field(default=None, ge=1, le=10)
    coordinated_break_even_confirmation_interval_seconds: Optional[float] = Field(default=None, gt=0, le=60)
    coordinated_break_even_preserve_runner: Optional[bool] = None
    coordinated_runner_reserve_quantity: Optional[int] = Field(default=None, ge=0, le=100)
    coordinated_profit_stage_1_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_profit_stage_1_sell_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_profit_stage_2_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_profit_stage_2_sell_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_fast_scalp_profit_stage_1_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_fast_scalp_profit_stage_2_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_low_premium_threshold: Optional[float] = Field(default=None, gt=0)
    coordinated_medium_premium_threshold: Optional[float] = Field(default=None, gt=0)
    coordinated_low_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_low_min_activation_cents: Optional[float] = Field(default=None, gt=0)
    coordinated_low_trailing_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_low_min_trailing_cents: Optional[float] = Field(default=None, gt=0)
    coordinated_low_break_even_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_medium_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_medium_trailing_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_medium_break_even_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_high_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_high_trailing_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_high_break_even_activation_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_progressive_trailing_enabled: Optional[bool] = None
    coordinated_trailing_step_gain_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_trailing_step_tighten_percent: Optional[float] = Field(default=None, gt=0)
    coordinated_trailing_min_percent: Optional[float] = Field(default=None, gt=0, le=100)
    coordinated_trailing_volatility_gate_percent: Optional[float] = Field(default=None, gt=0)


class TrailingStopSettingsUpdate(BaseModel):
    trailing_stop_enabled: Optional[bool] = None
    trailing_stop_type: Optional[str] = None
    trailing_stop_percent: Optional[float] = Field(default=None, gt=0)
    trailing_stop_activation_percent: Optional[float] = Field(default=None, ge=0, le=100)
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
