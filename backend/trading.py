"""
Enhanced Trading Logic
- Price buffer calculation
- Trailing stop management
- Bracket orders (profit target + stop loss)
- Position tracking
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PositionStatus(Enum):
    OPEN = "open"
    CLOSED = "closed"
    STOPPED = "stopped"
    TAKEN_PROFIT = "taken_profit"


@dataclass
class PriceBuffer:
    """Price buffer configuration for orders"""
    percentage: float = 0.03  # Default 3% buffer
    absolute: float = 0.0   # Absolute buffer (cents)
    use_percentage: bool = True
    
    def apply(self, price: float) -> float:
        """Apply buffer to get limit price"""
        if self.use_percentage:
            # Buffer means we pay LESS (buy) or get MORE (sell)
            # For buying: limit = entry * (1 - buffer%)
            # For selling: limit = entry * (1 + buffer%)
            return round(price * (1 - self.percentage / 100), 2)
        else:
            return round(price - self.absolute / 100, 2)


@dataclass
class BracketOrder:
    """
    Bracket order with profit target and stop loss
    
    Example:
        Buy 1 call at $1.00
        - Profit target: $1.50 (50% gain)
        - Stop loss: $0.70 (30% loss)
        
        The bot will manage this position and automatically
        close when either condition is met
    """
    # Entry settings
    entry_price: float
    quantity: int
    
    # Profit target (take profit)
    profit_target_price: Optional[float] = None
    profit_target_percentage: float = 50.0  # 50% profit by default
    
    # Stop loss
    stop_loss_price: Optional[float] = None
    stop_loss_percentage: float = 30.0  # 30% loss by default
    
    # Trailing stop (moves with price)
    use_trailing_stop: bool = False
    trailing_percentage: float = 25.0  # 25% trailing
    
    # Activation
    profit_activated: bool = False
    stop_activated: bool = False
    
    def __post_init__(self):
        """Calculate prices if not set"""
        if self.profit_target_price is None and self.profit_target_percentage:
            self.profit_target_price = round(
                self.entry_price * (1 + self.profit_target_percentage / 100), 2
            )
        
        if self.stop_loss_price is None and self.stop_loss_percentage:
            self.stop_loss_price = round(
                self.entry_price * (1 - self.stop_loss_percentage / 100), 2
            )
    
    def should_take_profit(self, current_price: float) -> bool:
        """Check if profit target is met"""
        if self.profit_activated:
            return False
        if self.profit_target_price and current_price >= self.profit_target_price:
            self.profit_activated = True
            return True
        return False
    
    def should_stop_loss(self, current_price: float) -> bool:
        """Check if stop loss is triggered"""
        if self.stop_activated:
            return False
        if self.stop_loss_price and current_price <= self.stop_loss_price:
            self.stop_activated = True
            return True
        return False
    
    def should_trailing_stop(self, current_price: float, peak_price: float) -> bool:
        """Check if trailing stop is triggered"""
        if not self.use_trailing_stop or self.stop_activated:
            return False
        
        # Calculate trailing stop price
        trailing_stop = peak_price * (1 - self.trailing_percentage / 100)
        
        if current_price <= trailing_stop:
            self.stop_activated = True
            return True
        return False
    
    def to_dict(self) -> dict:
        return {
            'entry_price': self.entry_price,
            'quantity': self.quantity,
            'profit_target_price': self.profit_target_price,
            'profit_target_percentage': self.profit_target_percentage,
            'stop_loss_price': self.stop_loss_price,
            'stop_loss_percentage': self.stop_loss_percentage,
            'use_trailing_stop': self.use_trailing_stop,
            'trailing_percentage': self.trailing_percentage,
        }


@dataclass
class Position:
    """Represents an open position"""
    id: str
    ticker: str
    strike: float
    option_type: str  # CALL or PUT
    expiration: str
    quantity: int
    entry_price: float
    contract_multiplier: float = 100.0
    filled_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Bracket order
    bracket: Optional[BracketOrder] = None
    
    # Status
    status: PositionStatus = PositionStatus.OPEN
    
    # Tracking
    peak_price: float = 0.0
    current_price: float = 0.0
    
    def update_price(self, price: float) -> bool:
        """
        Update current price and check if we should exit
        Returns True if position should be closed
        """
        self.current_price = price
        
        # Update peak
        if price > self.peak_price:
            self.peak_price = price
        
        # Check bracket conditions
        if self.bracket:
            if self.bracket.should_take_profit(price):
                self.status = PositionStatus.TAKEN_PROFIT
                logger.info(f"[Position {self.id}] Profit target hit: ${price} >= ${self.bracket.profit_target_price}")
                return True
            
            if self.bracket.should_trailing_stop(price, self.peak_price):
                self.status = PositionStatus.STOPPED
                logger.info(f"[Position {self.id}] Trailing stop hit: ${price} < ${self.peak_price * (1 - self.bracket.trailing_percentage / 100):.2f}")
                return True
            
            if self.bracket.should_stop_loss(price):
                self.status = PositionStatus.STOPPED
                logger.info(f"[Position {self.id}] Stop loss hit: ${price} <= ${self.bracket.stop_loss_price}")
                return True
        
        return False
    
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'ticker': self.ticker,
            'strike': self.strike,
            'option_type': self.option_type,
            'expiration': self.expiration,
            'quantity': self.quantity,
            'entry_price': self.entry_price,
            'contract_multiplier': self.contract_multiplier,
            'filled_at': self.filled_at.isoformat(),
            'status': self.status.value,
            'peak_price': self.peak_price,
            'current_price': self.current_price,
            'bracket': self.bracket.to_dict() if self.bracket else None,
            'unrealized_pnl': self.calculate_pnl(),
        }
    
    def calculate_pnl(self) -> float:
        """Calculate unrealized P&L"""
        if self.current_price and self.quantity:
            return (self.current_price - self.entry_price) * self.quantity * self.contract_multiplier
        return 0.0


class PositionManager:
    """
    Manages all positions and handles:
    - Opening new positions
    - Updating prices
    - Checking exit conditions
    - Closing positions
    """
    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self._callbacks: List[callable] = []
    
    def add_position(self, position: Position) -> None:
        """Add a new position"""
        self.positions[position.id] = position
        logger.info(f"[PositionManager] Opened position {position.id}: {position.ticker} ${position.strike} {position.option_type}")
    
    def close_position(self, position_id: str, reason: str = "manual") -> Optional[Position]:
        """Close a position"""
        if position_id in self.positions:
            pos = self.positions[position_id]
            pos.status = PositionStatus.CLOSED
            logger.info(f"[PositionManager] Closed position {position_id}: {reason}")
            del self.positions[position_id]
            return pos
        return None
    
    def get_position(self, position_id: str) -> Optional[Position]:
        """Get a position by ID"""
        return self.positions.get(position_id)
    
    def get_open_positions(self, ticker: str = None) -> List[Position]:
        """Get all open positions, optionally filtered by ticker"""
        positions = [p for p in self.positions.values() if p.status == PositionStatus.OPEN]
        if ticker:
            positions = [p for p in positions if p.ticker.upper() == ticker.upper()]
        return positions
    
    def get_ticker_positions(self, ticker: str) -> List[Position]:
        """Get all positions for a specific ticker"""
        return self.get_open_positions(ticker)
    
    async def check_all_positions(self, price_service) -> List[Position]:
        """
        Check all positions for exit conditions
        Returns list of positions that should be closed
        """
        to_close = []
        
        for position in list(self.positions.values()):
            if position.status != PositionStatus.OPEN:
                continue
            
            try:
                # Get current price
                price = await price_service.get_price(
                    position.ticker,
                    position.strike,
                    position.option_type,
                    position.expiration
                )
                
                if price and position.update_price(price):
                    to_close.append(position)
                    
            except Exception as e:
                logger.error(f"[PositionManager] Error checking position {position.id}: {e}")
        
        return to_close
    
    def register_exit_callback(self, callback: callable) -> None:
        """Register callback for position exits"""
        self._callbacks.append(callback)
    
    async def notify_exit(self, position: Position, reason: str) -> None:
        """Notify callbacks of position exit"""
        for callback in self._callbacks:
            try:
                await callback(position, reason)
            except Exception as e:
                logger.error(f"[PositionManager] Callback error: {e}")


class DefaultPositionManager:
    """Default position manager with optional database-backed storage."""
    
    def __init__(self, db=None):
        self._db = db
        self._positions: Dict[str, Dict] = {}
    
    async def open_position(
        self,
        position_id: str,
        ticker: str,
        strike: float,
        option_type: str,
        expiration: str,
        quantity: int,
        entry_price: float,
        profit_target: float = None,
        stop_loss: float = None,
        trailing_stop: bool = False,
    ) -> Dict:
        """Open a new position"""
        position = {
            'id': position_id,
            'ticker': ticker,
            'strike': strike,
            'option_type': option_type,
            'expiration': expiration,
            'quantity': quantity,
            'entry_price': entry_price,
            'filled_at': datetime.now(timezone.utc).isoformat(),
            'status': 'open',
            'peak_price': entry_price,
            'profit_target': profit_target,
            'stop_loss': stop_loss,
            'trailing_stop': trailing_stop,
            'trailing_percentage': 25.0 if trailing_stop else None,
        }

        if self._db is not None:
            await self._db.insert_position(position)
        else:
            self._positions[position_id] = position
        logger.info(f"[DefaultPositionManager] Opened position {position_id}")
        
        return position
    
    async def close_position(self, position_id: str, reason: str) -> Optional[Dict]:
        """Close a position"""
        if self._db is not None:
            pos = await self._db.get_position_by_id(position_id)
            if not pos:
                return None
            updates = {
                'status': reason,
                'closed_at': datetime.now(timezone.utc).isoformat(),
            }
            await self._db.update_position(position_id, {'$set': updates})
            pos.update(updates)
            logger.info(f"[DefaultPositionManager] Closed position {position_id}: {reason}")
            return pos

        if position_id in self._positions:
            pos = self._positions[position_id]
            pos['status'] = reason
            pos['closed_at'] = datetime.now(timezone.utc).isoformat()
            del self._positions[position_id]
            logger.info(f"[DefaultPositionManager] Closed position {position_id}: {reason}")
            return pos
        return None
    
    async def get_positions(self, status: str = None) -> List[Dict]:
        """Get positions"""
        if self._db is not None:
            return await self._db.get_positions(status)
        if status:
            return [p for p in self._positions.values() if p.get('status') == status]
        return list(self._positions.values())


def calculate_buffered_price(entry_price: float, buffer_percentage: float = 3.0) -> float:
    """
    Calculate buffered price for order
    
    The buffer is a safety margin - we want to get filled at 
    a price better than the alert price
    
    For BUY orders: limit price = entry * (1 - buffer%)
    This gives us 3% buffer by default
    
    Args:
        entry_price: The alert price from Discord
        buffer_percentage: Buffer % (default 3%)
    
    Returns:
        Buffered limit price
    """
    if entry_price <= 0:
        logger.warning(f"[Trading] Invalid entry price: {entry_price}, using 0.01")
        return 0.01
    
    buffered = entry_price * (1 - buffer_percentage / 100)
    return round(max(buffered, 0.01), 2)


def calculate_profit_target(entry_price: float, target_percentage: float = 50.0) -> float:
    """Calculate profit target price"""
    return round(entry_price * (1 + target_percentage / 100), 2)


def calculate_stop_loss(entry_price: float, stop_percentage: float = 30.0) -> float:
    """Calculate stop loss price"""
    return round(entry_price * (1 - stop_percentage / 100), 2)


def calculate_trailing_stop(peak_price: float, trailing_percentage: float = 25.0) -> float:
    """Calculate trailing stop price"""
    return round(peak_price * (1 - trailing_percentage / 100), 2)
