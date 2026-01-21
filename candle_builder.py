"""
Candle Builder for Bank Nifty Scalping Bot.
Aggregates tick data into OHLCV candles.
"""

import asyncio
from collections import deque
from datetime import datetime
from typing import Callable, List, Optional

import pandas as pd

from config import CANDLE_TIMEFRAME_SECONDS, MIN_CANDLES_FOR_INDICATORS
from models import Candle, Tick
from utils import logger


class CandleBuilder:
    """
    Aggregates tick data into time-based OHLCV candles.
    Maintains a rolling window of candles for indicator calculation.
    """

    def __init__(
        self,
        timeframe_seconds: int = CANDLE_TIMEFRAME_SECONDS,
        max_candles: int = 100,
        on_candle_complete: Optional[Callable[[Candle], None]] = None,
    ):
        """
        Initialize the candle builder.

        Args:
            timeframe_seconds: Candle timeframe in seconds (default: 60 for 1-min)
            max_candles: Maximum number of candles to keep in memory
            on_candle_complete: Callback when a new candle is completed
        """
        self.timeframe_seconds = timeframe_seconds
        self.max_candles = max_candles
        self.on_candle_complete = on_candle_complete

        # Current candle being built
        self._current_candle: Optional[Candle] = None
        self._current_candle_start: Optional[datetime] = None
        self._ticks_in_candle: int = 0

        # Completed candles (using deque for efficient O(1) operations)
        self._candles: deque[Candle] = deque(maxlen=max_candles)

        # Lock for thread safety
        self._lock = asyncio.Lock()

    def _get_candle_start_time(self, timestamp: datetime) -> datetime:
        """
        Calculate the start time of the candle period for a given timestamp.

        Args:
            timestamp: Tick timestamp

        Returns:
            datetime: Start of the candle period
        """
        # Align to candle boundaries
        seconds = timestamp.second + timestamp.minute * 60 + timestamp.hour * 3600
        candle_start_seconds = (
            seconds // self.timeframe_seconds
        ) * self.timeframe_seconds

        hours = candle_start_seconds // 3600
        minutes = (candle_start_seconds % 3600) // 60
        secs = candle_start_seconds % 60

        return timestamp.replace(hour=hours, minute=minutes, second=secs, microsecond=0)

    async def process_tick(self, tick: Tick) -> Optional[Candle]:
        """
        Process a new tick and update/complete candles.

        Args:
            tick: Incoming tick data

        Returns:
            Candle if a new candle was completed, None otherwise
        """
        async with self._lock:
            candle_start = self._get_candle_start_time(tick.timestamp)
            completed_candle = None

            # Check if this tick belongs to current candle or a new one
            if self._current_candle_start is None:
                # First tick ever
                self._start_new_candle(tick, candle_start)

            elif candle_start > self._current_candle_start:
                # New candle period - complete current candle
                completed_candle = self._complete_current_candle()
                self._start_new_candle(tick, candle_start)

            else:
                # Same candle period - update current candle
                self._update_current_candle(tick)

            return completed_candle

    def _start_new_candle(self, tick: Tick, candle_start: datetime) -> None:
        """Start a new candle with the first tick."""
        self._current_candle = Candle(
            timestamp=candle_start,
            open=tick.ltp,
            high=tick.ltp,
            low=tick.ltp,
            close=tick.ltp,
            volume=tick.volume or 1,
        )
        self._current_candle_start = candle_start
        self._ticks_in_candle = 1

    def _update_current_candle(self, tick: Tick) -> None:
        """Update the current candle with a new tick."""
        if self._current_candle is None:
            return

        self._current_candle.high = max(self._current_candle.high, tick.ltp)
        self._current_candle.low = min(self._current_candle.low, tick.ltp)
        self._current_candle.close = tick.ltp
        self._current_candle.volume += tick.volume or 1
        self._ticks_in_candle += 1

    def _complete_current_candle(self) -> Optional[Candle]:
        """Complete the current candle and add to history."""
        if self._current_candle is None:
            return None

        completed = self._current_candle
        self._candles.append(completed)

        logger.debug(
            f"Candle completed: {completed.timestamp.strftime('%H:%M')} "
            f"O:{completed.open:.2f} H:{completed.high:.2f} "
            f"L:{completed.low:.2f} C:{completed.close:.2f} "
            f"V:{completed.volume} ({self._ticks_in_candle} ticks)"
        )

        # Trigger callback if set
        if self.on_candle_complete:
            try:
                self.on_candle_complete(completed)
            except Exception as e:
                logger.error(f"Candle callback error: {e}")

        return completed

    def get_candles_df(self) -> pd.DataFrame:
        """
        Get completed candles as a pandas DataFrame.

        Returns:
            DataFrame with OHLCV columns
        """
        if not self._candles:
            return pd.DataFrame(
                columns=["timestamp", "Open", "High", "Low", "Close", "Volume"]
            )

        data = [candle.to_dict() for candle in self._candles]
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        return df

    def get_latest_candles(self, n: int = 20) -> List[Candle]:
        """
        Get the latest N completed candles.

        Args:
            n: Number of candles to return

        Returns:
            List of Candle objects
        """
        return list(self._candles)[-n:]

    def get_current_candle(self) -> Optional[Candle]:
        """Get the current in-progress candle."""
        return self._current_candle

    @property
    def candle_count(self) -> int:
        """Get number of completed candles."""
        return len(self._candles)

    @property
    def has_enough_data(self) -> bool:
        """Check if we have enough candles for indicator calculation."""
        return len(self._candles) >= MIN_CANDLES_FOR_INDICATORS

    def get_latest_close(self) -> Optional[float]:
        """Get the latest closing price."""
        if self._candles:
            return self._candles[-1].close
        return None

    def clear(self) -> None:
        """Clear all candle data."""
        self._candles.clear()
        self._current_candle = None
        self._current_candle_start = None
        self._ticks_in_candle = 0
        logger.info("Candle builder cleared")


class MultiTimeframeCandleBuilder:
    """
    Manages multiple candle builders for different timeframes.
    Useful for multi-timeframe analysis.
    """

    def __init__(self, timeframes: List[int]):
        """
        Initialize with multiple timeframes.

        Args:
            timeframes: List of timeframe periods in seconds (e.g., [60, 300, 900])
        """
        self.builders: dict[int, CandleBuilder] = {}
        for tf in timeframes:
            self.builders[tf] = CandleBuilder(timeframe_seconds=tf)

    async def process_tick(self, tick: Tick) -> dict[int, Optional[Candle]]:
        """
        Process tick across all timeframes.

        Args:
            tick: Incoming tick data

        Returns:
            Dict mapping timeframe to completed candle (if any)
        """
        results = {}
        for tf, builder in self.builders.items():
            results[tf] = await builder.process_tick(tick)
        return results

    def get_builder(self, timeframe: int) -> Optional[CandleBuilder]:
        """Get the candle builder for a specific timeframe."""
        return self.builders.get(timeframe)
