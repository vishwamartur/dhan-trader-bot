"""
Strategy Engine (AlphaEngine) for Bank Nifty Scalping Bot.
Generates trading signals based on technical indicators.
"""

import asyncio
from datetime import datetime
from typing import Awaitable, Callable, Optional

from candle_builder import CandleBuilder
from config import (
    MARKET_OPEN_HOUR,
    MARKET_OPEN_MINUTE,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    SKIP_MINUTES_AFTER_OPEN,
)
from indicators import get_latest_indicators
from models import Candle, OptionType, Signal
from utils import calculate_atm_strike, is_market_hours, logger


class AlphaEngine:
    """
    Trading strategy engine that generates signals based on:
    - EMA 9 crossover
    - VWAP position
    - RSI momentum

    Signal Logic:
    - LONG (BUY_CE): Close > EMA9 AND Close > VWAP AND RSI > 60
    - SHORT (BUY_PE): Close < EMA9 AND Close < VWAP AND RSI < 40
    """

    def __init__(
        self,
        candle_builder: CandleBuilder,
        on_signal: Optional[Callable[[Signal, float, int], Awaitable[None]]] = None,
    ):
        """
        Initialize the Alpha Engine.

        Args:
            candle_builder: CandleBuilder instance for candle data
            on_signal: Async callback when signal is generated (signal, price, strike)
        """
        self.candle_builder = candle_builder
        self.on_signal = on_signal

        # State tracking
        self._last_signal: Signal = Signal.HOLD
        self._last_signal_time: Optional[datetime] = None
        self._position_open = False
        self._current_strike: Optional[int] = None

        # Statistics
        self._signals_generated = 0
        self._long_signals = 0
        self._short_signals = 0

    def set_position_open(self, is_open: bool):
        """Update position status."""
        self._position_open = is_open
        if not is_open:
            self._current_strike = None

    def _should_skip_trading(self) -> bool:
        """Check if we should skip trading (e.g., first N minutes after open)."""
        now = datetime.now()

        # Skip if not market hours
        if not is_market_hours(now):
            return True

        # Skip first N minutes after market open
        market_open = now.replace(
            hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0
        )
        minutes_since_open = (now - market_open).total_seconds() / 60

        if minutes_since_open < SKIP_MINUTES_AFTER_OPEN:
            logger.debug(f"Skipping: {minutes_since_open:.1f} min since open")
            return True

        return False

    async def process_candle(self, candle: Candle) -> Optional[Signal]:
        """
        Process a completed candle and generate signal.

        Args:
            candle: Completed candle data

        Returns:
            Generated signal or None
        """
        # Skip if position already open
        if self._position_open:
            logger.debug("Position open, skipping signal generation")
            return None

        # Skip during volatile periods
        if self._should_skip_trading():
            return None

        # Check if we have enough candles
        if not self.candle_builder.has_enough_data:
            logger.debug(
                f"Waiting for more data: {self.candle_builder.candle_count} candles"
            )
            return None

        # Get candle dataframe
        df = self.candle_builder.get_candles_df()

        # Calculate indicators
        indicators = get_latest_indicators(df)

        if indicators is None:
            return None

        # Generate signal
        signal = self._evaluate_conditions(indicators)

        if signal != Signal.HOLD:
            self._last_signal = signal
            self._last_signal_time = datetime.now()
            self._signals_generated += 1

            if signal == Signal.BUY_CE:
                self._long_signals += 1
            elif signal == Signal.BUY_PE:
                self._short_signals += 1

            # Calculate ATM strike for the signal
            spot_price = indicators["close"]
            atm_strike = calculate_atm_strike(spot_price)

            logger.info(
                f"⚡ SIGNAL: {signal.name} | "
                f"Spot: {spot_price:.2f} | "
                f"ATM Strike: {atm_strike} | "
                f"EMA9: {indicators['ema_9']:.2f} | "
                f"RSI: {indicators['rsi']:.2f} | "
                f"VWAP: {indicators['vwap']:.2f}"
            )

            # Trigger callback
            if self.on_signal:
                await self.on_signal(signal, spot_price, atm_strike)

        return signal

    def _evaluate_conditions(self, indicators: dict) -> Signal:
        """
        Evaluate trading conditions based on indicators.

        Args:
            indicators: Dict with indicator values

        Returns:
            Trading signal
        """
        close = indicators["close"]
        ema_9 = indicators["ema_9"]
        rsi = indicators["rsi"]
        vwap = indicators["vwap"]

        # Long Condition: Close > EMA9 AND Close > VWAP AND RSI > 60
        long_condition = close > ema_9 and close > vwap and rsi > RSI_OVERBOUGHT

        # Short Condition: Close < EMA9 AND Close < VWAP AND RSI < 40
        short_condition = close < ema_9 and close < vwap and rsi < RSI_OVERSOLD

        if long_condition:
            return Signal.BUY_CE
        elif short_condition:
            return Signal.BUY_PE
        else:
            return Signal.HOLD

    def get_option_type_for_signal(self, signal: Signal) -> Optional[OptionType]:
        """Get the option type (CALL/PUT) for a signal."""
        if signal == Signal.BUY_CE:
            return OptionType.CALL
        elif signal == Signal.BUY_PE:
            return OptionType.PUT
        return None

    @property
    def stats(self) -> dict:
        """Get strategy statistics."""
        return {
            "signals_generated": self._signals_generated,
            "long_signals": self._long_signals,
            "short_signals": self._short_signals,
            "last_signal": self._last_signal.name if self._last_signal else None,
            "last_signal_time": self._last_signal_time,
        }


class SignalProcessor:
    """
    Async processor that consumes candles and generates signals.
    Runs as a separate coroutine in the event loop.
    """

    def __init__(
        self,
        candle_queue: asyncio.Queue,
        signal_queue: asyncio.Queue,
        candle_builder: CandleBuilder,
    ):
        """
        Initialize signal processor.

        Args:
            candle_queue: Queue receiving completed candles
            signal_queue: Queue to push generated signals
            candle_builder: CandleBuilder instance
        """
        self.candle_queue = candle_queue
        self.signal_queue = signal_queue
        self.alpha_engine = AlphaEngine(candle_builder)
        self._running = False

    async def start(self):
        """Start processing candles."""
        self._running = True
        logger.info("🧠 Signal processor started")

        try:
            while self._running:
                try:
                    # Wait for candle with timeout
                    candle = await asyncio.wait_for(
                        self.candle_queue.get(), timeout=1.0
                    )

                    # Process candle
                    signal = await self.alpha_engine.process_candle(candle)

                    if signal and signal != Signal.HOLD:
                        # Get additional info for the signal
                        spot_price = candle.close
                        atm_strike = calculate_atm_strike(spot_price)
                        option_type = self.alpha_engine.get_option_type_for_signal(
                            signal
                        )

                        # Push to signal queue
                        await self.signal_queue.put(
                            {
                                "signal": signal,
                                "spot_price": spot_price,
                                "atm_strike": atm_strike,
                                "option_type": option_type,
                                "timestamp": datetime.now(),
                            }
                        )

                    self.candle_queue.task_done()

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error processing candle: {e}")

        except asyncio.CancelledError:
            logger.info("Signal processor cancelled")
            raise
        finally:
            self._running = False

    async def stop(self):
        """Stop the processor."""
        self._running = False

    def set_position_open(self, is_open: bool):
        """Update position status in alpha engine."""
        self.alpha_engine.set_position_open(is_open)
