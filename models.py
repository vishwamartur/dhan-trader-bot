"""
Data models for Bank Nifty Scalping Bot.
Defines core data structures used throughout the application.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, List, Dict, Any


class Signal(Enum):
    """Trading signal types."""
    BUY_CE = auto()  # Buy Call Option
    BUY_PE = auto()  # Buy Put Option
    EXIT = auto()    # Exit current position
    HOLD = auto()    # No action


class OrderStatus(Enum):
    """Order status types."""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OptionType(Enum):
    """Option contract types."""
    CALL = "CALL"
    PUT = "PUT"


@dataclass
class Tick:
    """Single market tick data."""
    security_id: str
    ltp: float
    timestamp: datetime
    volume: Optional[int] = None
    oi: Optional[int] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    
    
@dataclass
class Candle:
    """OHLCV candle data."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp,
            'Open': self.open,
            'High': self.high,
            'Low': self.low,
            'Close': self.close,
            'Volume': self.volume
        }


@dataclass
class IndicatorValues:
    """Calculated indicator values for a candle."""
    ema_9: float
    rsi: float
    vwap: float
    close: float
    timestamp: datetime


@dataclass
class OptionContract:
    """Option contract details."""
    security_id: str
    symbol: str
    strike: float
    option_type: OptionType
    expiry: datetime
    ltp: Optional[float] = None
    oi: Optional[int] = None
    iv: Optional[float] = None  # Implied Volatility


@dataclass
class Position:
    """Open position details."""
    security_id: str
    symbol: str
    option_type: OptionType
    strike: float
    quantity: int
    entry_price: float
    entry_time: datetime
    order_id: str
    stop_loss: float
    target: float
    current_price: Optional[float] = None
    pnl: float = 0.0
    
    def update_pnl(self, current_price: float) -> float:
        """Update and return current P&L."""
        self.current_price = current_price
        self.pnl = (current_price - self.entry_price) * self.quantity
        return self.pnl
    
    def should_exit_sl(self, current_price: float) -> bool:
        """Check if stop loss is hit."""
        return current_price <= self.stop_loss
    
    def should_exit_target(self, current_price: float) -> bool:
        """Check if target is hit."""
        return current_price >= self.target


@dataclass
class OrderRequest:
    """Order request details."""
    security_id: str
    exchange_segment: str
    transaction_type: str  # BUY or SELL
    quantity: int
    order_type: str  # LIMIT or MARKET
    price: float
    product_type: str  # INTRA or CNC
    validity: str = "DAY"
    trigger_price: Optional[float] = None
    disclosed_quantity: Optional[int] = None
    correlation_id: Optional[str] = None


@dataclass
class OrderResponse:
    """Order response from API."""
    order_id: str
    status: OrderStatus
    security_id: str
    quantity: int
    price: float
    filled_quantity: int = 0
    average_price: float = 0.0
    message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass 
class TradeStats:
    """Daily trading statistics."""
    date: datetime
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    orders_placed: int = 0
    
    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100
