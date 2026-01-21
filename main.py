"""
Main Application for Bank Nifty High-Frequency Scalping Bot.
Orchestrates all components with async event-driven architecture.
"""

import asyncio
import signal
import sys
from datetime import datetime

from candle_builder import CandleBuilder
from config import CANDLE_TIMEFRAME_SECONDS, INDEX_SECURITY_ID, PAPER_TRADING
from market_feed import MarketFeedHandler, MockMarketFeed
from models import Candle, Signal, Tick
from order_manager import OrderManager
from strategy import AlphaEngine
from utils import is_market_hours, logger, time_to_market_open


class ScalpingBot:
    """
    Main orchestrator for the Bank Nifty Scalping Bot.

    Architecture:
    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │  Market Feed    │───▶│  Candle Builder │───▶│  Alpha Engine   │
    │  (Producer)     │    │  (Aggregator)   │    │  (Strategy)     │
    └─────────────────┘    └─────────────────┘    └─────────────────┘
                                                           │
                                                           ▼
    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
    │  Position Mgr   │◀───│  Order Manager  │◀───│  Signal Queue   │
    │  (Risk)         │    │  (Executor)     │    │  (Consumer)     │
    └─────────────────┘    └─────────────────┘    └─────────────────┘
    """

    def __init__(self, paper_trading: bool = PAPER_TRADING):
        """
        Initialize the scalping bot.

        Args:
            paper_trading: If True, run in simulation mode
        """
        self.paper_trading = paper_trading
        self._running = False
        self._shutdown_event = asyncio.Event()

        # Initialize queues for async communication
        self.tick_queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=1000)
        self.candle_queue: asyncio.Queue[Candle] = asyncio.Queue(maxsize=100)
        self.signal_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=10)

        # Initialize components
        self.candle_builder = CandleBuilder(
            timeframe_seconds=CANDLE_TIMEFRAME_SECONDS,
            on_candle_complete=self._on_candle_complete_sync,
        )

        # Market feed (mock for paper trading)
        if paper_trading:
            self.market_feed = MockMarketFeed(self.tick_queue)
        else:
            self.market_feed = MarketFeedHandler(self.tick_queue)
            self.market_feed.add_index(INDEX_SECURITY_ID)

        # Strategy engine
        self.alpha_engine = AlphaEngine(
            candle_builder=self.candle_builder, on_signal=self._on_signal
        )

        # Order manager
        self.order_manager = OrderManager(paper_trading=paper_trading)

        # Tasks
        self._tasks: list[asyncio.Task] = []

    def _on_candle_complete_sync(self, candle: Candle) -> None:
        """Sync callback when candle completes (puts to queue)."""
        try:
            self.candle_queue.put_nowait(candle)
        except asyncio.QueueFull:
            logger.warning("Candle queue full, dropping candle")

    async def _on_signal(
        self, signal: Signal, spot_price: float, atm_strike: int
    ) -> None:
        """Async callback when signal is generated."""
        await self.signal_queue.put(
            {
                "signal": signal,
                "spot_price": spot_price,
                "atm_strike": atm_strike,
                "timestamp": datetime.now(),
            }
        )

    async def _tick_processor(self) -> None:
        """
        Consumer coroutine: Processes ticks and builds candles.
        """
        logger.info("📊 Tick processor started")

        try:
            while self._running:
                try:
                    tick = await asyncio.wait_for(self.tick_queue.get(), timeout=1.0)

                    # Process tick through candle builder
                    await self.candle_builder.process_tick(tick)

                    # If we have an open position, check exit conditions
                    if self.order_manager.has_open_position:
                        position = self.order_manager.current_position
                        if position:
                            # For simplicity, using tick LTP as proxy for option LTP
                            # In production, you'd subscribe to the option's feed
                            await self.order_manager.check_exit_conditions(tick.ltp)

                    self.tick_queue.task_done()

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Tick processor error: {e}")

        except asyncio.CancelledError:
            logger.info("Tick processor cancelled")
            raise

    async def _signal_processor(self) -> None:
        """
        Consumer coroutine: Processes completed candles and generates signals.
        """
        logger.info("🧠 Signal processor started")

        try:
            while self._running:
                try:
                    candle = await asyncio.wait_for(
                        self.candle_queue.get(), timeout=1.0
                    )

                    # Update alpha engine's position status
                    self.alpha_engine.set_position_open(
                        self.order_manager.has_open_position
                    )

                    # Process candle for signals
                    await self.alpha_engine.process_candle(candle)

                    self.candle_queue.task_done()

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Signal processor error: {e}")

        except asyncio.CancelledError:
            logger.info("Signal processor cancelled")
            raise

    async def _order_executor(self) -> None:
        """
        Consumer coroutine: Executes orders from signal queue.
        """
        logger.info("💰 Order executor started")

        try:
            while self._running:
                try:
                    signal_data = await asyncio.wait_for(
                        self.signal_queue.get(), timeout=1.0
                    )

                    signal = signal_data["signal"]
                    spot_price = signal_data["spot_price"]
                    atm_strike = signal_data["atm_strike"]

                    # Execute the signal
                    position = await self.order_manager.execute_signal(
                        signal, spot_price, atm_strike
                    )

                    if position:
                        logger.info(f"Position opened: {position.symbol}")

                    self.signal_queue.task_done()

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Order executor error: {e}")

        except asyncio.CancelledError:
            logger.info("Order executor cancelled")
            raise

    async def _heartbeat(self) -> None:
        """
        Periodic heartbeat for monitoring and maintenance.
        """
        logger.info("💓 Heartbeat started")

        try:
            while self._running:
                await asyncio.sleep(60)  # Every minute

                # Log status
                stats = self.order_manager.daily_stats
                logger.info(
                    f"📈 Status: "
                    f"Candles: {self.candle_builder.candle_count} | "
                    f"Trades: {stats.total_trades} | "
                    f"P&L: {stats.total_pnl:+.2f} | "
                    f"Orders: {stats.orders_placed}"
                )

                # Check if market is still open
                if not is_market_hours():
                    logger.info("Market closed. Shutting down...")
                    await self.shutdown()

        except asyncio.CancelledError:
            raise

    async def start(self) -> None:
        """Start the scalping bot."""
        logger.info("=" * 60)
        logger.info("🚀 BANK NIFTY SCALPING BOT STARTING")
        logger.info(
            f"   Mode: {'PAPER TRADING' if self.paper_trading else 'LIVE TRADING'}"
        )
        logger.info("=" * 60)

        # Check market hours
        if not is_market_hours():
            time_to_open = time_to_market_open()
            if time_to_open:
                logger.info(f"Market closed. Opening in: {time_to_open}")
                logger.info("Waiting for market to open...")
                # In production, you might want to wait here
                # await asyncio.sleep(time_to_open.total_seconds())

        self._running = True

        # Start all coroutines
        self._tasks = [
            asyncio.create_task(self.market_feed.start(), name="market_feed"),
            asyncio.create_task(self._tick_processor(), name="tick_processor"),
            asyncio.create_task(self._signal_processor(), name="signal_processor"),
            asyncio.create_task(self._order_executor(), name="order_executor"),
            asyncio.create_task(self._heartbeat(), name="heartbeat"),
        ]

        # Wait for shutdown signal
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Gracefully shutdown the bot."""
        logger.info("🛑 Initiating shutdown...")

        self._running = False

        # Close any open positions
        if self.order_manager.has_open_position:
            logger.info("Closing open positions...")
            await self.order_manager.close_all_positions("SHUTDOWN")

        # Stop market feed
        await self.market_feed.stop()

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Log final stats
        stats = self.order_manager.daily_stats
        logger.info("=" * 60)
        logger.info("📊 FINAL SESSION STATISTICS")
        logger.info(f"   Total Trades: {stats.total_trades}")
        logger.info(f"   Winning: {stats.winning_trades}")
        logger.info(f"   Losing: {stats.losing_trades}")
        logger.info(f"   Win Rate: {stats.win_rate:.1f}%")
        logger.info(f"   Total P&L: {stats.total_pnl:+.2f}")
        logger.info(f"   Orders Placed: {stats.orders_placed}")
        logger.info("=" * 60)
        logger.info("Bot shutdown complete.")

        self._shutdown_event.set()

    def request_shutdown(self) -> None:
        """Request async shutdown (can be called from signal handler)."""
        self._shutdown_event.set()


def setup_signal_handlers(bot: ScalpingBot) -> None:
    """Setup OS signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        bot.request_shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def test_connection() -> bool:
    """Test API connection before starting."""
    try:
        from dhanhq import dhanhq

        from config import ACCESS_TOKEN, CLIENT_ID

        dhan = dhanhq(CLIENT_ID, ACCESS_TOKEN)

        # Try to fetch fund limits as a test
        result = dhan.get_fund_limits()

        if result and "status" in result:
            logger.info("✅ API connection successful")
            return True
        else:
            logger.error(f"API test failed: {result}")
            return False

    except Exception as e:
        logger.error(f"API connection test failed: {e}")
        return False


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Bank Nifty Scalping Bot")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run in live trading mode (default: paper trading)",
    )
    parser.add_argument(
        "--test-connection", action="store_true", help="Test API connection and exit"
    )

    args = parser.parse_args()

    # Test connection mode
    if args.test_connection:
        success = await test_connection()
        sys.exit(0 if success else 1)

    # Determine trading mode
    paper_trading = not args.live

    if not paper_trading:
        logger.warning("⚠️  LIVE TRADING MODE - Real money at risk!")
        logger.warning("Press Ctrl+C within 5 seconds to cancel...")
        await asyncio.sleep(5)

    # Create and start bot
    bot = ScalpingBot(paper_trading=paper_trading)

    # Setup signal handlers
    setup_signal_handlers(bot)

    # Run the bot
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await bot.shutdown()
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        await bot.shutdown()
        raise


if __name__ == "__main__":
    # Run the async main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
