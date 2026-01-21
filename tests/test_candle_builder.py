"""
Tests for candle builder module.
"""
import pytest
import asyncio
from datetime import datetime
from candle_builder import CandleBuilder
from models import Tick, Candle


class TestCandleBuilder:
    """Test cases for CandleBuilder class."""

    @pytest.fixture
    def candle_builder(self):
        """Create a CandleBuilder instance."""
        return CandleBuilder(timeframe_seconds=60)

    @pytest.fixture
    def sample_tick(self):
        """Create a sample tick."""
        return Tick(
            security_id="25",
            ltp=45000.0,
            timestamp=datetime.now(),
            volume=100
        )

    def test_initialization(self, candle_builder):
        """Test candle builder initialization."""
        assert candle_builder.timeframe_seconds == 60
        assert candle_builder.candle_count == 0

    @pytest.mark.asyncio
    async def test_process_tick(self, candle_builder, sample_tick):
        """Test processing a single tick."""
        result = await candle_builder.process_tick(sample_tick)
        # First tick shouldn't complete a candle
        assert candle_builder.current_candle is not None

    @pytest.mark.asyncio
    async def test_multiple_ticks(self, candle_builder):
        """Test processing multiple ticks."""
        base_time = datetime.now()
        
        for i in range(5):
            tick = Tick(
                security_id="25",
                ltp=45000.0 + i * 10,
                timestamp=base_time,
                volume=100
            )
            await candle_builder.process_tick(tick)
        
        current = candle_builder.current_candle
        assert current is not None
        assert current.high >= current.low

    def test_reset(self, candle_builder):
        """Test resetting the candle builder."""
        candle_builder.reset()
        assert candle_builder.current_candle is None
        assert candle_builder.candle_count == 0
