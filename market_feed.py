"""
Market Feed Handler for Bank Nifty Scalping Bot.
Manages WebSocket connection to Dhan for real-time market data.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from dhanhq import MarketFeed

from config import get_dhan_context, INDEX_SECURITY_ID
from models import Tick
from utils import async_retry, logger


@dataclass
class FeedConfig:
    """Market feed configuration."""

    version: str = "v2"


class MarketFeedHandler:
    """
    Handles WebSocket connection to Dhan Market Feed.
    Produces tick data into an async queue for processing.
    """

    def __init__(self, tick_queue: asyncio.Queue, config: Optional[FeedConfig] = None):
        """
        Initialize the market feed handler.

        Args:
            tick_queue: Async queue to push tick data into
            config: Feed configuration (uses defaults if not provided)
        """
        self.config = config or FeedConfig()
        self.tick_queue = tick_queue
        self.feed: Optional[MarketFeed] = None
        self._dhan_context = None
        self._running = False
        self._connected = False
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

        # Subscribed instruments
        self.instruments: list[tuple] = []

    def add_instrument(
        self,
        security_id: str,
        exchange: int = MarketFeed.NSE,
        mode: int = MarketFeed.Full,
    ):
        """
        Add an instrument to subscribe.

        Args:
            security_id: Dhan security ID
            exchange: Exchange code (default: NSE)
            mode: Subscription mode (Ticker, Quote, Full)
        """
        self.instruments.append((exchange, security_id, mode))
        logger.info(f"Added instrument: {security_id} on exchange {exchange}")

    def add_index(self, security_id: str = INDEX_SECURITY_ID):
        """Add Bank Nifty index for subscription."""
        # Index is on IDX segment
        self.instruments.append((MarketFeed.IDX, security_id, MarketFeed.Full))
        logger.info(f"Added index: {security_id}")

    def add_option(self, security_id: str):
        """Add an option contract for subscription."""
        self.instruments.append((MarketFeed.NSE_FNO, security_id, MarketFeed.Full))
        logger.info(f"Added option: {security_id}")

    async def _process_message(self, message: dict) -> None:
        """
        Process incoming WebSocket message.

        Args:
            message: Raw message from WebSocket
        """
        try:
            # Parse the message based on Dhan's format
            if not message:
                return

            # Extract tick data
            # Note: Actual field names depend on Dhan's WebSocket response format
            tick = Tick(
                security_id=str(message.get("security_id", "")),
                ltp=float(message.get("LTP", message.get("ltp", 0))),
                timestamp=datetime.now(),
                volume=message.get("volume"),
                oi=message.get("oi"),
                bid=message.get("bid"),
                ask=message.get("ask"),
            )

            # Put tick into queue for processing
            await self.tick_queue.put(tick)

        except Exception as e:
            logger.error(f"Error processing message: {e}")

    @async_retry(max_retries=5, delay=2.0, backoff=2.0)
    async def connect(self) -> None:
        """Establish WebSocket connection."""
        if not self.instruments:
            raise ValueError("No instruments added. Call add_instrument() first.")

        logger.info(
            f"Connecting to Dhan Market Feed with {len(self.instruments)} instruments..."
        )

        try:
            self._dhan_context = get_dhan_context()
            self.feed = MarketFeed(
                self._dhan_context,
                self.instruments,
                version=self.config.version,
            )
            self._connected = True
            self._reconnect_delay = 1.0  # Reset delay on successful connection
            logger.info("[OK] Connected to Dhan Market Feed")

        except Exception as e:
            self._connected = False
            logger.error(f"Failed to connect to Market Feed: {e}")
            raise

    async def start(self) -> None:
        """Start receiving market data."""
        if not self._connected:
            await self.connect()

        self._running = True
        logger.info("🚀 Starting market data stream...")

        try:
            while self._running:
                try:
                    # Run the feed (this is blocking in the library)
                    # We wrap it to make it work with async
                    self.feed.run_forever()

                    # Get data from feed
                    response = self.feed.get_data()

                    if response:
                        await self._process_message(response)

                    # Small yield to prevent CPU hogging
                    await asyncio.sleep(0.001)

                except Exception as e:
                    logger.error(f"Feed error: {e}")
                    if self._running:
                        await self._handle_reconnect()

        except asyncio.CancelledError:
            logger.info("Market feed task cancelled")
            raise
        finally:
            await self.stop()

    async def _handle_reconnect(self) -> None:
        """Handle reconnection with exponential backoff."""
        self._connected = False

        logger.warning(f"Reconnecting in {self._reconnect_delay:.1f}s...")
        await asyncio.sleep(self._reconnect_delay)

        # Exponential backoff
        self._reconnect_delay = min(
            self._reconnect_delay * 2, self._max_reconnect_delay
        )

        try:
            await self.connect()
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")

    async def stop(self) -> None:
        """Stop the market feed."""
        self._running = False

        if self.feed:
            try:
                self.feed.disconnect()
                logger.info("Disconnected from Market Feed")
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")

        self._connected = False

    async def subscribe(self, instruments: list[tuple]) -> None:
        """
        Subscribe to additional instruments while connected.

        Args:
            instruments: List of (exchange, security_id, mode) tuples
        """
        if not self._connected or not self.feed:
            raise RuntimeError("Not connected. Call connect() first.")

        try:
            self.feed.subscribe_symbols(instruments)
            self.instruments.extend(instruments)
            logger.info(f"Subscribed to {len(instruments)} additional instruments")
        except Exception as e:
            logger.error(f"Failed to subscribe: {e}")
            raise

    async def unsubscribe(self, instruments: list[tuple]) -> None:
        """
        Unsubscribe from instruments.

        Args:
            instruments: List of (exchange, security_id, mode) tuples
        """
        if not self._connected or not self.feed:
            return

        try:
            self.feed.unsubscribe_symbols(instruments)
            # Remove from tracked instruments
            for inst in instruments:
                if inst in self.instruments:
                    self.instruments.remove(inst)
            logger.info(f"Unsubscribed from {len(instruments)} instruments")
        except Exception as e:
            logger.error(f"Failed to unsubscribe: {e}")

    @property
    def is_connected(self) -> bool:
        """Check if connected to market feed."""
        return self._connected

    @property
    def is_running(self) -> bool:
        """Check if feed is actively running."""
        return self._running


class MockMarketFeed(MarketFeedHandler):
    """
    Mock market feed for paper trading and testing.
    Generates simulated tick data.
    """

    def __init__(self, tick_queue: asyncio.Queue, base_price: float = 48000.0):
        super().__init__(tick_queue)
        self.base_price = base_price
        self._price = base_price

    async def connect(self) -> None:
        """Simulate connection."""
        logger.info("📋 Connected to Mock Market Feed (Paper Trading Mode)")
        self._connected = True

    async def start(self) -> None:
        """Generate simulated ticks."""
        self._running = True
        logger.info("🚀 Starting simulated market data...")

        import random

        try:
            while self._running:
                # Simulate price movement (random walk)
                change = random.uniform(-10, 10)
                self._price += change

                tick = Tick(
                    security_id=INDEX_SECURITY_ID,
                    ltp=self._price,
                    timestamp=datetime.now(),
                    volume=random.randint(100, 1000),
                )

                await self.tick_queue.put(tick)

                # Simulate tick frequency (~10 ticks per second)
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            raise
        finally:
            self._running = False
