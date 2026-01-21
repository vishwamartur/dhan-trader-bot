"""
Utility functions for Bank Nifty Scalping Bot.
Includes expiry calculation, throttling, logging, and helper functions.
"""

import asyncio
import functools
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from config import LOG_FILE, LOG_LEVEL

# =============================================================================
# LOGGING SETUP
# =============================================================================


class SafeStreamHandler(logging.StreamHandler):
    """Stream handler that safely encodes Unicode for Windows console."""

    def emit(self, record):
        try:
            msg = self.format(record)
            # Replace Unicode characters that Windows console can't handle
            safe_msg = msg.encode("ascii", "replace").decode("ascii")
            stream = self.stream
            stream.write(safe_msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


def setup_logging() -> logging.Logger:
    """Configure and return the main logger."""
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(LOG_FILE)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Configure logger
    logger = logging.getLogger("scalping_bot")
    logger.setLevel(getattr(logging, LOG_LEVEL))

    # File handler (with UTF-8 encoding for full emoji support in logs)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    # Console handler (safe for Windows)
    console_handler = SafeStreamHandler()
    console_handler.setLevel(getattr(logging, LOG_LEVEL))

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


# Global logger instance
logger = setup_logging()


# =============================================================================
# EXPIRY DATE CALCULATION
# =============================================================================


def get_next_weekly_expiry(reference_date: Optional[datetime] = None) -> datetime:
    """
    Calculate the next weekly expiry date (Thursday) for Bank Nifty.

    Args:
        reference_date: Date to calculate from (default: today)

    Returns:
        datetime: Next Thursday expiry date
    """
    if reference_date is None:
        reference_date = datetime.now()

    # Thursday is weekday 3 (Monday=0, Thursday=3)
    days_until_thursday = (3 - reference_date.weekday()) % 7

    # If today is Thursday after market hours, get next week's expiry
    if days_until_thursday == 0 and reference_date.hour >= 15:
        days_until_thursday = 7

    expiry_date = reference_date + timedelta(days=days_until_thursday)

    # Return date at market close time
    return expiry_date.replace(hour=15, minute=30, second=0, microsecond=0)


def get_expiry_string(expiry_date: Optional[datetime] = None) -> str:
    """
    Get expiry date in API format (YYYY-MM-DD).

    Args:
        expiry_date: Expiry datetime (default: next weekly expiry)

    Returns:
        str: Formatted expiry string
    """
    if expiry_date is None:
        expiry_date = get_next_weekly_expiry()

    return expiry_date.strftime("%Y-%m-%d")


def get_monthly_expiry(reference_date: Optional[datetime] = None) -> datetime:
    """
    Calculate the monthly expiry (last Thursday of the month).

    Args:
        reference_date: Date to calculate from (default: today)

    Returns:
        datetime: Monthly expiry date
    """
    if reference_date is None:
        reference_date = datetime.now()

    # Get last day of current month
    if reference_date.month == 12:
        next_month = reference_date.replace(
            year=reference_date.year + 1, month=1, day=1
        )
    else:
        next_month = reference_date.replace(month=reference_date.month + 1, day=1)

    last_day = next_month - timedelta(days=1)

    # Find last Thursday
    days_since_thursday = (last_day.weekday() - 3) % 7
    last_thursday = last_day - timedelta(days=days_since_thursday)

    return last_thursday.replace(hour=15, minute=30, second=0, microsecond=0)


# =============================================================================
# THROTTLING & RATE LIMITING
# =============================================================================


class Throttle:
    """
    Rate limiter to prevent exceeding API limits.
    Thread-safe implementation using asyncio locks.
    """

    def __init__(self, max_calls: int, period_seconds: float):
        """
        Initialize throttle.

        Args:
            max_calls: Maximum number of calls allowed
            period_seconds: Time period for the limit
        """
        self.max_calls = max_calls
        self.period = period_seconds
        self.calls: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """
        Acquire permission to make a call.
        Blocks if rate limit would be exceeded.

        Returns:
            bool: True if call is allowed
        """
        async with self._lock:
            now = time.time()

            # Remove calls outside the window
            self.calls = [t for t in self.calls if now - t < self.period]

            if len(self.calls) >= self.max_calls:
                # Calculate wait time
                oldest_call = min(self.calls)
                wait_time = self.period - (now - oldest_call)
                if wait_time > 0:
                    logger.debug(f"Throttle: waiting {wait_time:.3f}s")
                    await asyncio.sleep(wait_time)

            self.calls.append(time.time())
            return True

    def reset(self):
        """Reset the throttle."""
        self.calls = []


class SLUpdateThrottle:
    """
    Special throttle for Stop Loss updates to prevent excessive modifications.
    Only allows update if price moved enough AND enough time has passed.
    """

    def __init__(self, min_points: float, min_interval: float):
        """
        Args:
            min_points: Minimum price movement required
            min_interval: Minimum seconds between updates
        """
        self.min_points = min_points
        self.min_interval = min_interval
        self.last_update_time: float = 0
        self.last_update_price: float = 0

    def should_update(self, current_price: float, new_sl_price: float) -> bool:
        """
        Check if SL update should be allowed.

        Args:
            current_price: Current market price
            new_sl_price: Proposed new stop loss price

        Returns:
            bool: True if update should proceed
        """
        now = time.time()

        # Check time interval
        if now - self.last_update_time < self.min_interval:
            return False

        # Check price movement
        price_diff = abs(new_sl_price - self.last_update_price)
        if self.last_update_price > 0 and price_diff < self.min_points:
            return False

        return True

    def mark_updated(self, sl_price: float):
        """Mark that an update was made."""
        self.last_update_time = time.time()
        self.last_update_price = sl_price


# =============================================================================
# RETRY DECORATOR
# =============================================================================


def async_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator for async functions with exponential backoff retry.

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"{func.__name__} attempt {attempt + 1} failed: {e}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {e}"
                        )

            raise last_exception

        return wrapper

    return decorator


# =============================================================================
# MARKET HOURS UTILITIES
# =============================================================================


def is_market_hours(check_time: Optional[datetime] = None) -> bool:
    """
    Check if given time is within market hours.

    Args:
        check_time: Time to check (default: now)

    Returns:
        bool: True if within market hours
    """
    if check_time is None:
        check_time = datetime.now()

    # Check if weekday (Monday=0, Friday=4)
    if check_time.weekday() > 4:
        return False

    # Import here to avoid circular import
    from config import (
        MARKET_CLOSE_HOUR,
        MARKET_CLOSE_MINUTE,
        MARKET_OPEN_HOUR,
        MARKET_OPEN_MINUTE,
    )

    market_open = check_time.replace(
        hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0
    )
    market_close = check_time.replace(
        hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0, microsecond=0
    )

    return market_open <= check_time <= market_close


def time_to_market_open() -> Optional[timedelta]:
    """
    Calculate time remaining until market opens.

    Returns:
        timedelta or None if market is open
    """
    now = datetime.now()

    if is_market_hours(now):
        return None

    from config import MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE

    # Calculate next market open
    next_open = now.replace(
        hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0
    )

    # If past today's open, move to next trading day
    if now >= next_open:
        next_open += timedelta(days=1)

    # Skip weekends
    while next_open.weekday() > 4:
        next_open += timedelta(days=1)

    return next_open - now


# =============================================================================
# ATM STRIKE CALCULATION
# =============================================================================


def calculate_atm_strike(spot_price: float, strike_interval: int = 100) -> int:
    """
    Calculate At-The-Money strike price.

    Args:
        spot_price: Current spot price of the index
        strike_interval: Strike price interval (100 for Bank Nifty)

    Returns:
        int: ATM strike price
    """
    return round(spot_price / strike_interval) * strike_interval


def get_strike_range(
    atm_strike: int, num_strikes: int = 5, interval: int = 100
) -> list[int]:
    """
    Get a range of strikes around ATM.

    Args:
        atm_strike: ATM strike price
        num_strikes: Number of strikes on each side
        interval: Strike interval

    Returns:
        list: List of strike prices
    """
    strikes = []
    for i in range(-num_strikes, num_strikes + 1):
        strikes.append(atm_strike + (i * interval))
    return strikes
