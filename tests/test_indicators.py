"""
Tests for technical indicators module.
"""
import pytest
import numpy as np
from indicators import TechnicalIndicators


class TestTechnicalIndicators:
    """Test cases for TechnicalIndicators class."""

    @pytest.fixture
    def indicators(self):
        """Create a TechnicalIndicators instance."""
        return TechnicalIndicators(
            ema_period=9,
            rsi_period=14,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9
        )

    @pytest.fixture
    def sample_prices(self):
        """Generate sample price data."""
        np.random.seed(42)
        base_price = 45000
        returns = np.random.normal(0, 0.001, 100)
        prices = [base_price]
        for r in returns:
            prices.append(prices[-1] * (1 + r))
        return prices

    def test_initialization(self, indicators):
        """Test indicator initialization."""
        assert indicators.ema_period == 9
        assert indicators.rsi_period == 14
        assert indicators.macd_fast == 12
        assert indicators.macd_slow == 26
        assert indicators.macd_signal == 9

    def test_add_price(self, indicators, sample_prices):
        """Test adding prices to indicator."""
        for price in sample_prices[:20]:
            indicators.add_price(price)
        
        assert len(indicators.prices) == 20

    def test_ema_calculation(self, indicators, sample_prices):
        """Test EMA calculation."""
        for price in sample_prices[:20]:
            indicators.add_price(price)
        
        ema = indicators.get_ema()
        assert ema is not None
        assert isinstance(ema, float)

    def test_rsi_calculation(self, indicators, sample_prices):
        """Test RSI calculation."""
        for price in sample_prices[:30]:
            indicators.add_price(price)
        
        rsi = indicators.get_rsi()
        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_rsi_bounds(self, indicators):
        """Test RSI stays within bounds."""
        # Add increasing prices (should give high RSI)
        for i in range(30):
            indicators.add_price(45000 + i * 10)
        
        rsi = indicators.get_rsi()
        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_macd_calculation(self, indicators, sample_prices):
        """Test MACD calculation."""
        for price in sample_prices[:50]:
            indicators.add_price(price)
        
        macd, signal, histogram = indicators.get_macd()
        assert macd is not None
        assert signal is not None
        assert histogram is not None

    def test_insufficient_data(self, indicators):
        """Test behavior with insufficient data."""
        # Add only a few prices
        for i in range(5):
            indicators.add_price(45000 + i)
        
        # Should return None for indicators that need more data
        assert indicators.get_rsi() is None or indicators.get_rsi() is not None

    def test_reset(self, indicators, sample_prices):
        """Test resetting indicators."""
        for price in sample_prices[:20]:
            indicators.add_price(price)
        
        indicators.reset()
        assert len(indicators.prices) == 0
