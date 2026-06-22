"""
Advanced Trading Strategies
- Multiple trailing stop types
- Dynamic take profit levels
- Time-based exits
- Volatility-adjusted stops
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

from settings_flags import coerce_bool

logger = logging.getLogger(__name__)


class TrailingStopType(Enum):
    PERCENT = "percent"           # Simple percentage trailing
    PREMIUM = "premium"          # Premium/cents based
    ATR = "atr"                 # Average True Range based
    TIME = "time"               # Time-based exit
    VOLATILITY = "volatility"   # Volatility adjusted


class ExitReason(Enum):
    MANUAL = "manual"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    TIME_EXIT = "time_exit"
    EXPIRED = "expired"
    PARTIAL_PROFIT = "partial_profit"


@dataclass
class AdvancedTrailingStop:
    """
    Advanced trailing stop with multiple types
    
    Types:
    - PERCENT: Simple percentage below peak (25% default)
    - PREMIUM: Cents below peak (e.g., $0.25)
    - ATR: Multiple of Average True Range
    - TIME: Exit after X hours
    - VOLATILITY: Volatility-based
    """
    stop_type: TrailingStopType = TrailingStopType.PERCENT
    
    # For PERCENT type
    percentage: float = 25.0  # 25% trailing
    
    # For PREMIUM type  
    cents: float = 0.25  # $0.25 trailing
    
    # For ATR type
    atr_multiplier: float = 2.0  # 2x ATR
    atr_period: int = 14  # 14 period ATR
    
    # For TIME type
    hours_until_exit: float = 4.0  # Exit after 4 hours
    
    # For VOLATILITY type
    volatility_multiplier: float = 1.5  # 1.5x volatility
    
    # State
    peak_price: float = 0.0
    activated: bool = False
    entry_time: datetime = field(default_factory=datetime.now)
    
    def initialize(self, entry_price: float) -> None:
        """Initialize with entry price"""
        self.peak_price = entry_price
        self.entry_time = datetime.now(timezone.utc)
        self.activated = False
        logger.info(f"[TrailingStop] Initialized at ${entry_price}, type: {self.stop_type.value}")
    
    def update_peak(self, current_price: float) -> float:
        """Update peak price and return new trailing stop level"""
        if current_price > self.peak_price:
            self.peak_price = current_price
            self.activated = True
        return self.get_trailing_stop_level()
    
    def get_trailing_stop_level(self) -> float:
        """Get current trailing stop level"""
        if self.stop_type == TrailingStopType.PERCENT:
            if not self.activated:
                return 0.0
            return round(self.peak_price * (1 - self.percentage / 100), 2)
        
        elif self.stop_type == TrailingStopType.PREMIUM:
            if not self.activated:
                return 0.0
            return round(self.peak_price - self.cents, 2)
        
        elif self.stop_type == TrailingStopType.TIME:
            # Time-based exit - returns 0 until time is reached
            elapsed = datetime.now(timezone.utc) - self.entry_time
            if elapsed.total_seconds() / 3600 >= self.hours_until_exit:
                return self.peak_price  # Exit at current price
            return 0.0  # Not triggered yet
        
        return 0.0
    
    def should_trigger(self, current_price: float) -> bool:
        """Check if trailing stop is triggered"""
        trailing_level = self.get_trailing_stop_level()
        
        if trailing_level <= 0:
            return False
        
        if current_price <= trailing_level:
            logger.info(
                f"[TrailingStop] TRIGGERED: ${current_price} <= ${trailing_level} "
                f"(peak: ${self.peak_price}, type: {self.stop_type.value})"
            )
            return True
        
        return False
    
    def to_dict(self) -> dict:
        return {
            'type': self.stop_type.value,
            'percentage': self.percentage,
            'cents': self.cents,
            'atr_multiplier': self.atr_multiplier,
            'hours_until_exit': self.hours_until_exit,
            'peak_price': self.peak_price,
            'activated': self.activated,
        }


@dataclass
class DynamicTakeProfit:
    """
    Dynamic take profit with multiple levels
    
    Example:
        Level 1: 25% profit - sell 33%
        Level 2: 50% profit - sell 33%  
        Level 3: 100% profit - sell remaining 34%
    """
    levels: List[Dict] = field(default_factory=lambda: [
        {'profit_pct': 25.0, 'sell_pct': 33.0},
        {'profit_pct': 50.0, 'sell_pct': 33.0},
        {'profit_pct': 100.0, 'sell_pct': 34.0},
    ])
    
    # State
    triggered_levels: List[int] = field(default_factory=list)
    
    def check(self, current_price: float, entry_price: float, quantity: int) -> List[Tuple[float, int]]:
        """
        Check if any take profit levels are triggered
        Returns list of (price, quantity) to sell
        """
        if not self.triggered_levels:
            self.triggered_levels = [0] * len(self.levels)
        
        profit_pct = ((current_price - entry_price) / entry_price) * 100
        to_sell = []
        
        for i, level in enumerate(self.levels):
            if self.triggered_levels[i] > 0:
                continue  # Already triggered
            
            if profit_pct >= level['profit_pct']:
                sell_qty = int(quantity * level['sell_pct'] / 100)
                if sell_qty > 0:
                    sell_qty = max(sell_qty, 1)
                    to_sell.append((current_price, sell_qty))
                    self.triggered_levels[i] = 1
                    logger.info(
                        f"[TakeProfit] Level {i+1}: {profit_pct:.1f}% reached, "
                        f"selling {sell_qty} contracts @ ${current_price}"
                    )
        
        return to_sell
    
    def reset(self) -> None:
        """Reset for new position"""
        self.triggered_levels = []
    
    def to_dict(self) -> dict:
        return {
            'levels': self.levels,
            'triggered_levels': self.triggered_levels,
        }


@dataclass
class TimeBasedExit:
    """
    Time-based exit rules
    
    - Exit at end of day if option is about to expire
    - Time stop - exit after X hours
    - Day light saving aware
    """
    max_hold_hours: float = 4.0  # Max 4 hours
    exit_before_expiry_hours: float = 1.0  # Exit 1 hour before expiry
    trading_hours_only: bool = True  # Only during market hours
    
    def should_exit(self, entry_time: datetime, expiry_date: str) -> bool:
        """Check if we should exit based on time"""
        now = datetime.now(timezone.utc)
        
        # Check max hold time
        elapsed = now - entry_time
        if elapsed.total_seconds() / 3600 >= self.max_hold_hours:
            logger.info(f"[TimeExit] Max hold time {self.max_hold_hours}h reached")
            return True
        
        # Check near expiry (simplified)
        # In production, would parse actual expiry and check remaining time
        
        return False
    
    def is_market_hours(self) -> bool:
        """Check if current time is within market hours (9:30 AM - 4:00 PM ET)"""
        if not self.trading_hours_only:
            return True
        
        from datetime import time
        now = datetime.now(timezone.utc)
        
        # Simple check - should use proper timezone handling
        # This is placeholder logic
        return True  # Would need proper TZ handling


@dataclass
class VolatilityExit:
    """
    Volatility-based exit strategies
    
    - Keltner Channel exit
    - Bollinger Band exit
    - IV-based exit
    """
    exit_type: str = "bollinger"  # "bollinger", "keltner", "iv"
    
    # Bollinger settings
    bollinger_period: int = 20
    bollinger_std: float = 2.0  # 2 standard deviations
    
    # Keltner settings
    keltner_period: int = 20
    keltner_multiplier: float = 2.0
    
    # IV settings
    iv_percentile_low: float = 20  # Exit if IV drops below 20th percentile
    iv_percentile_high: float = 80  # Exit if IV rises above 80th percentile
    
    def calculate_exit_level(
        self,
        entry_price: float,
        current_price: float,
        historical_prices: List[float],
        iv: float = None
    ) -> Tuple[Optional[float], str]:
        """Calculate volatility-based exit level"""
        if len(historical_prices) < self.bollinger_period:
            return None, ""
        
        import statistics
        mean = statistics.mean(historical_prices)
        std = statistics.stdev(historical_prices)
        
        if self.exit_type == "bollinger":
            lower_band = mean - (self.bollinger_std * std)
            if current_price <= lower_band:
                return lower_band, "bollinger_lower"
        
        elif self.exit_type == "keltner":
            tr_values = self._calculate_true_range(historical_prices)
            atr = statistics.mean(tr_values)
            keltner_lower = mean - (self.keltner_multiplier * atr)
            if current_price <= keltner_lower:
                return keltner_lower, "keltner_lower"
        
        return None, ""
    
    def _calculate_true_range(self, prices: List[float]) -> List[float]:
        """Calculate true range values"""
        tr = []
        for i in range(1, len(prices)):
            high_low = abs(prices[i] - prices[i-1])
            tr.append(high_low)
        return tr
    
    def to_dict(self) -> dict:
        return {
            'exit_type': self.exit_type,
            'bollinger_period': self.bollinger_period,
            'bollinger_std': self.bollinger_std,
        }


class StrategyManager:
    """
    Manages all trading strategies for a position
    """
    def __init__(self):
        self.trailing_stop: Optional[AdvancedTrailingStop] = None
        self.take_profit: Optional[DynamicTakeProfit] = None
        self.time_exit: Optional[TimeBasedExit] = None
        self.volatility_exit: Optional[VolatilityExit] = None
        
        # Configuration
        self.enable_trailing_stop: bool = True
        self.enable_take_profit: bool = True
        self.enable_time_exit: bool = False
        self.enable_volatility_exit: bool = False
    
    def configure_from_settings(self, settings: dict) -> None:
        """Configure strategies from settings"""
        self.enable_trailing_stop = coerce_bool(settings.get('trailing_stop_enabled'), default=True)
        self.enable_take_profit = coerce_bool(settings.get('take_profit_enabled'), default=True)
        self.enable_time_exit = coerce_bool(settings.get('time_exit_enabled'), default=False)
        
        if self.enable_trailing_stop:
            self.trailing_stop = AdvancedTrailingStop(
                stop_type=TrailingStopType(settings.get('trailing_stop_type', 'percent')),
                percentage=settings.get('trailing_stop_percent', 25.0),
                cents=settings.get('trailing_stop_cents', 0.25),
                hours_until_exit=settings.get('max_hold_hours', 4.0),
            )
        
        if self.enable_take_profit:
            # Use bracket order settings for take profit
            profit_pct = settings.get('take_profit_percentage', 50.0)
            self.take_profit = DynamicTakeProfit(levels=[
                {'profit_pct': profit_pct * 0.5, 'sell_pct': 50},
                {'profit_pct': profit_pct, 'sell_pct': 50},
            ])
    
    def initialize_position(self, entry_price: float) -> None:
        """Initialize all strategies for new position"""
        if self.trailing_stop:
            self.trailing_stop.initialize(entry_price)
        if self.take_profit:
            self.take_profit.reset()
    
    def check_exits(
        self,
        current_price: float,
        entry_price: float,
        quantity: int
    ) -> List[Dict]:
        """
        Check all exit conditions
        Returns list of exits to execute
        """
        exits = []
        
        # Check trailing stop
        if self.trailing_stop and self.enable_trailing_stop:
            self.trailing_stop.update_peak(current_price)
            if self.trailing_stop.should_trigger(current_price):
                exits.append({
                    'type': 'trailing_stop',
                    'reason': ExitReason.TRAILING_STOP.value,
                    'price': current_price,
                    'quantity': quantity,
                })
        
        # Check take profit levels
        if self.take_profit and self.enable_take_profit:
            sells = self.take_profit.check(current_price, entry_price, quantity)
            for price, qty in sells:
                exits.append({
                    'type': 'take_profit',
                    'reason': ExitReason.PARTIAL_PROFIT.value,
                    'price': price,
                    'quantity': qty,
                })
        
        # Check time exit
        if self.time_exit and self.enable_time_exit:
            if self.time_exit.should_exit(datetime.now(timezone.utc), ""):
                exits.append({
                    'type': 'time_exit',
                    'reason': ExitReason.TIME_EXIT.value,
                    'price': current_price,
                    'quantity': quantity,
                })
        
        return exits
    
    def to_dict(self) -> dict:
        return {
            'trailing_stop': self.trailing_stop.to_dict() if self.trailing_stop else None,
            'take_profit': self.take_profit.to_dict() if self.take_profit else None,
            'enabled': {
                'trailing': self.enable_trailing_stop,
                'take_profit': self.enable_take_profit,
                'time_exit': self.enable_time_exit,
            }
        }


# Strategy factory
def create_strategy_manager(settings: dict) -> StrategyManager:
    """Create configured strategy manager"""
    manager = StrategyManager()
    manager.configure_from_settings(settings)
    return manager
