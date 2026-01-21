"""
Tests for data models.
"""
import pytest
from datetime import datetime
from models import Tick, Candle, Signal, SignalType


class TestTick:
    """Test cases for Tick model."""

    def test_tick_creation(self):
        """Test creating a Tick instance."""
        tick = Tick(
            security_id="25",
            ltp=45000.0,
            timestamp=datetime.now(),
            volume=100
        )
        assert tick.security_id == "25"
        assert tick.ltp == 45000.0
        assert tick.volume == 100

    def test_tick_default_values(self):
        """Test Tick with default values."""
        tick = Tick(
            security_id="25",
            ltp=45000.0,
            timestamp=datetime.now()
        )
        assert tick.security_id == "25"
        assert tick.ltp == 45000.0


class TestCandle:
    """Test cases for Candle model."""

    def test_candle_creation(self):
        """Test creating a Candle instance."""
        now = datetime.now()
        candle = Candle(
            open=45000.0,
            high=45100.0,
            low=44900.0,
            close=45050.0,
            volume=1000,
            timestamp=now
        )
        assert candle.open == 45000.0
        assert candle.high == 45100.0
        assert candle.low == 44900.0
        assert candle.close == 45050.0
        assert candle.volume == 1000

    def test_candle_is_bullish(self):
        """Test bullish candle detection."""
        candle = Candle(
            open=45000.0,
            high=45100.0,
            low=44900.0,
            close=45050.0,
            volume=1000,
            timestamp=datetime.now()
        )
        assert candle.close > candle.open  # Bullish

    def test_candle_is_bearish(self):
        """Test bearish candle detection."""
        candle = Candle(
            open=45050.0,
            high=45100.0,
            low=44900.0,
            close=44950.0,
            volume=1000,
            timestamp=datetime.now()
        )
        assert candle.close < candle.open  # Bearish


class TestSignal:
    """Test cases for Signal model."""

    def test_long_signal(self):
        """Test creating a LONG signal."""
        signal = Signal(
            signal_type=SignalType.LONG,
            strength=0.8,
            timestamp=datetime.now()
        )
        assert signal.signal_type == SignalType.LONG
        assert signal.strength == 0.8

    def test_short_signal(self):
        """Test creating a SHORT signal."""
        signal = Signal(
            signal_type=SignalType.SHORT,
            strength=0.7,
            timestamp=datetime.now()
        )
        assert signal.signal_type == SignalType.SHORT
        assert signal.strength == 0.7

    def test_exit_signal(self):
        """Test creating an EXIT signal."""
        signal = Signal(
            signal_type=SignalType.EXIT,
            strength=1.0,
            timestamp=datetime.now()
        )
        assert signal.signal_type == SignalType.EXIT
