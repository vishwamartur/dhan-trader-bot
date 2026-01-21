"""
Configuration module for Bank Nifty High-Frequency Scalping Bot.
Store sensitive credentials and strategy parameters here.
"""

import os
from dataclasses import dataclass

# typing imports removed - not needed

# =============================================================================
# API CREDENTIALS
# =============================================================================
# Get from environment variables for security, or set directly for testing
CLIENT_ID = os.getenv("DHAN_CLIENT_ID", "YOUR_CLIENT_ID")
ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN", "YOUR_ACCESS_TOKEN")

# =============================================================================
# TRADING MODE
# =============================================================================
PAPER_TRADING = True  # Set to False for live trading

# =============================================================================
# INDEX CONFIGURATION
# =============================================================================
INDEX_SYMBOL = "NIFTY BANK"
INDEX_SECURITY_ID = "25"  # Bank Nifty security ID (verify from Dhan Scrip Master)
INDEX_EXCHANGE_SEGMENT = "IDX_I"  # Index segment for option chain

# =============================================================================
# POSITION SIZING
# =============================================================================
LOT_SIZE = 15  # Bank Nifty lot size
NUM_LOTS = 2  # Number of lots to trade
QUANTITY = LOT_SIZE * NUM_LOTS  # Total quantity per trade

# =============================================================================
# TIMEFRAME SETTINGS
# =============================================================================
CANDLE_TIMEFRAME_SECONDS = 60  # 1-minute candles
MIN_CANDLES_FOR_INDICATORS = 15  # Minimum candles needed before trading

# =============================================================================
# INDICATOR PARAMETERS
# =============================================================================
EMA_PERIOD = 9
RSI_PERIOD = 14
RSI_OVERBOUGHT = 60  # Long signal threshold
RSI_OVERSOLD = 40  # Short signal threshold

# =============================================================================
# RISK MANAGEMENT
# =============================================================================
STOP_LOSS_POINTS = 20.0  # Stop loss in points
TARGET_POINTS = 40.0  # Target profit in points
SLIPPAGE_BUFFER = 5.0  # Points above LTP for marketable limit orders
MAX_DAILY_LOSS = 5000.0  # Maximum loss per day (INR)
MAX_POSITIONS = 1  # Maximum concurrent positions

# =============================================================================
# RATE LIMITING
# =============================================================================
MAX_ORDERS_PER_SECOND = 25  # Dhan API limit
ORDER_THROTTLE_SECONDS = 0.05  # Minimum time between orders (1/20 sec)
SL_UPDATE_MIN_POINTS = 5.0  # Minimum price move before updating SL
SL_UPDATE_MIN_INTERVAL = 2.0  # Minimum seconds between SL updates

# =============================================================================
# TRADING HOURS
# =============================================================================
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30

# Skip first N minutes after market open (high volatility)
SKIP_MINUTES_AFTER_OPEN = 5

# =============================================================================
# LOGGING
# =============================================================================
LOG_LEVEL = "INFO"
LOG_FILE = "logs/trading.log"

# =============================================================================
# EXCHANGE SEGMENTS (for reference)
# =============================================================================
EXCHANGE_NSE = "NSE"
EXCHANGE_NSE_FNO = "NSE_FNO"
EXCHANGE_IDX = "IDX_I"


@dataclass
class TradingConfig:
    """Encapsulated trading configuration."""

    client_id: str = CLIENT_ID
    access_token: str = ACCESS_TOKEN
    paper_trading: bool = PAPER_TRADING
    index_symbol: str = INDEX_SYMBOL
    index_security_id: str = INDEX_SECURITY_ID
    quantity: int = QUANTITY
    stop_loss_points: float = STOP_LOSS_POINTS
    target_points: float = TARGET_POINTS
    slippage_buffer: float = SLIPPAGE_BUFFER

    def validate(self) -> bool:
        """Validate configuration before trading."""
        if self.client_id == "YOUR_CLIENT_ID":
            raise ValueError(
                "Please set DHAN_CLIENT_ID environment variable or update config.py"
            )
        if self.access_token == "YOUR_ACCESS_TOKEN":
            raise ValueError(
                "Please set DHAN_ACCESS_TOKEN environment variable or update config.py"
            )
        return True


# Global config instance
config = TradingConfig()
