"""
Tests for technical indicators module.
"""

import numpy as np

from indicators import calculate_atr, calculate_ema, calculate_rsi


class TestEMA:
    """Test cases for EMA calculation."""

    def test_ema_basic(self):
        """Test basic EMA calculation."""
        prices = np.array([44.0, 44.5, 45.0, 45.5, 46.0, 46.5, 47.0, 47.5, 48.0, 48.5])
        ema = calculate_ema(prices, period=5)

        # First valid EMA should be at index 4 (period - 1)
        assert not np.isnan(ema[4])
        # Earlier values should be NaN
        assert np.isnan(ema[0])

    def test_ema_with_insufficient_data(self):
        """Test EMA with insufficient data."""
        prices = np.array([44.0, 44.5, 45.0])
        ema = calculate_ema(prices, period=9)

        # All should be NaN since we have fewer prices than the period
        assert np.all(np.isnan(ema))

    def test_ema_trending_up(self):
        """Test EMA on upward trending data."""
        prices = np.array([float(i) for i in range(1, 21)])
        ema = calculate_ema(prices, period=5)

        # EMA should be less than the latest price in uptrend
        assert ema[-1] < prices[-1]


class TestRSI:
    """Test cases for RSI calculation."""

    def test_rsi_basic(self):
        """Test basic RSI calculation."""
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(50)) + 100
        rsi = calculate_rsi(prices, period=14)

        # RSI should be between 0 and 100
        valid_rsi = rsi[~np.isnan(rsi)]
        assert np.all(valid_rsi >= 0)
        assert np.all(valid_rsi <= 100)

    def test_rsi_overbought(self):
        """Test RSI with consistently rising prices (should be high)."""
        prices = np.array([float(i) for i in range(1, 31)])
        rsi = calculate_rsi(prices, period=14)

        # RSI should be high (overbought) for consistent uptrend
        valid_rsi = rsi[~np.isnan(rsi)]
        assert len(valid_rsi) > 0
        assert valid_rsi[-1] > 50  # Should be above neutral

    def test_rsi_oversold(self):
        """Test RSI with consistently falling prices (should be low)."""
        prices = np.array([float(30 - i) for i in range(30)])
        rsi = calculate_rsi(prices, period=14)

        # RSI should be low (oversold) for consistent downtrend
        valid_rsi = rsi[~np.isnan(rsi)]
        assert len(valid_rsi) > 0
        assert valid_rsi[-1] < 50  # Should be below neutral


class TestATR:
    """Test cases for ATR calculation."""

    def test_atr_basic(self):
        """Test basic ATR calculation."""
        np.random.seed(42)
        base = np.cumsum(np.random.randn(50)) + 100
        high = base + np.abs(np.random.randn(50))
        low = base - np.abs(np.random.randn(50))
        close = base

        atr = calculate_atr(high, low, close, period=14)

        # ATR should be positive where valid
        valid_atr = atr[~np.isnan(atr)]
        assert np.all(valid_atr > 0)

    def test_atr_high_volatility(self):
        """Test ATR with high volatility data."""
        # Create high volatility data
        high = np.array([110.0, 115.0, 120.0, 125.0, 130.0] * 4)
        low = np.array([90.0, 85.0, 80.0, 75.0, 70.0] * 4)
        close = np.array([100.0, 100.0, 100.0, 100.0, 100.0] * 4)

        atr = calculate_atr(high, low, close, period=5)

        # ATR should be relatively high due to large ranges
        valid_atr = atr[~np.isnan(atr)]
        if len(valid_atr) > 0:
            assert valid_atr[-1] > 10  # High volatility
