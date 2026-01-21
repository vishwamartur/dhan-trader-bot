"""
Order Manager for Bank Nifty Scalping Bot.
Handles order execution, position tracking, and risk management.
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List

from dhanhq import dhanhq

from config import (
    CLIENT_ID, ACCESS_TOKEN, PAPER_TRADING,
    INDEX_SECURITY_ID, INDEX_EXCHANGE_SEGMENT,
    QUANTITY, STOP_LOSS_POINTS, TARGET_POINTS, SLIPPAGE_BUFFER,
    MAX_ORDERS_PER_SECOND, ORDER_THROTTLE_SECONDS,
    SL_UPDATE_MIN_POINTS, SL_UPDATE_MIN_INTERVAL,
    MAX_DAILY_LOSS, MAX_POSITIONS
)
from models import (
    Signal, Position, OrderRequest, OrderResponse, OrderStatus,
    OptionType, OptionContract, TradeStats
)
from utils import (
    logger, Throttle, SLUpdateThrottle, async_retry,
    get_next_weekly_expiry, get_expiry_string, calculate_atm_strike
)


class OrderManager:
    """
    Manages order execution with Dhan API.
    Features:
    - Marketable limit orders to minimize slippage
    - Rate limiting (25 orders/sec max)
    - Position tracking with SL/Target
    - Daily loss limit enforcement
    """
    
    def __init__(self, paper_trading: bool = PAPER_TRADING):
        """
        Initialize the order manager.
        
        Args:
            paper_trading: If True, simulate orders without live execution
        """
        self.paper_trading = paper_trading
        
        # Initialize Dhan client
        if not paper_trading:
            self.dhan = dhanhq(CLIENT_ID, ACCESS_TOKEN)
            logger.info("✅ Connected to Dhan API (LIVE MODE)")
        else:
            self.dhan = None
            logger.info("📋 Paper Trading Mode - Orders will be simulated")
        
        # Position tracking
        self._positions: Dict[str, Position] = {}  # order_id -> Position
        self._current_position: Optional[Position] = None
        
        # Rate limiting
        self._order_throttle = Throttle(MAX_ORDERS_PER_SECOND, 1.0)
        self._sl_update_throttle = SLUpdateThrottle(
            SL_UPDATE_MIN_POINTS,
            SL_UPDATE_MIN_INTERVAL
        )
        
        # Daily statistics
        self._daily_stats = TradeStats(date=datetime.now().date())
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
    async def get_option_token(
        self,
        strike: int,
        option_type: OptionType,
        expiry: Optional[str] = None
    ) -> Optional[str]:
        """
        Fetch the security ID for a specific option contract.
        
        Args:
            strike: Strike price
            option_type: CALL or PUT
            expiry: Expiry date string (default: next weekly expiry)
            
        Returns:
            Security ID or None if not found
        """
        if expiry is None:
            expiry = get_expiry_string()
        
        try:
            if self.paper_trading:
                # Return mock token for paper trading
                mock_token = f"MOCK_{strike}_{option_type.value}_{expiry}"
                logger.debug(f"Mock token: {mock_token}")
                return mock_token
            
            # Fetch option chain from Dhan
            chain = self.dhan.option_chain(
                under_security_id=INDEX_SECURITY_ID,
                under_exchange_segment=INDEX_EXCHANGE_SEGMENT,
                expiry=expiry
            )
            
            if not chain or 'data' not in chain:
                logger.error(f"Invalid option chain response: {chain}")
                return None
            
            # Parse the chain to find matching contract
            # Note: Exact parsing depends on Dhan's response structure
            for contract in chain.get('data', []):
                contract_strike = contract.get('strike_price')
                contract_type = contract.get('option_type')
                
                if (contract_strike == strike and 
                    contract_type == option_type.value):
                    return str(contract.get('security_id'))
            
            logger.warning(f"Contract not found: {strike} {option_type.value}")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching option token: {e}")
            return None
    
    async def get_option_ltp(self, security_id: str) -> Optional[float]:
        """
        Get the last traded price of an option.
        
        Args:
            security_id: Option security ID
            
        Returns:
            LTP or None
        """
        if self.paper_trading:
            # Return mock LTP for paper trading
            return 150.0  # Placeholder
        
        try:
            quote = self.dhan.ohlc_data(
                securities={"NSE_FNO": [security_id]}
            )
            
            if quote and 'data' in quote:
                # Parse LTP from response
                for item in quote['data']:
                    if str(item.get('security_id')) == security_id:
                        return float(item.get('ltp', 0))
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching LTP: {e}")
            return None
    
    @async_retry(max_retries=2, delay=0.5)
    async def place_order(
        self,
        security_id: str,
        transaction_type: str,
        quantity: int = QUANTITY,
        price: Optional[float] = None,
        is_sl_order: bool = False
    ) -> Optional[OrderResponse]:
        """
        Place a marketable limit order.
        
        Args:
            security_id: Option security ID
            transaction_type: 'BUY' or 'SELL'
            quantity: Order quantity
            price: Limit price (if None, fetches LTP + buffer)
            is_sl_order: If True, this is a stop loss order
            
        Returns:
            OrderResponse or None if failed
        """
        # Enforce rate limiting
        await self._order_throttle.acquire()
        
        async with self._lock:
            # Check daily loss limit
            if self._daily_stats.total_pnl <= -MAX_DAILY_LOSS:
                logger.error("❌ Daily loss limit reached. No more orders allowed.")
                return None
            
            # Check position limit
            if len(self._positions) >= MAX_POSITIONS and transaction_type == 'BUY':
                logger.warning("Max positions reached. Skipping order.")
                return None
            
            # Get LTP for marketable limit price
            if price is None:
                ltp = await self.get_option_ltp(security_id)
                if ltp is None:
                    logger.error("Could not fetch LTP for order")
                    return None
                
                # Marketable limit: LTP + buffer for BUY, LTP - buffer for SELL
                if transaction_type == 'BUY':
                    price = ltp + SLIPPAGE_BUFFER
                else:
                    price = max(0.05, ltp - SLIPPAGE_BUFFER)  # Min tick size
            
            logger.info(
                f"📝 Placing order: {transaction_type} {quantity} @ {price:.2f} "
                f"(Security: {security_id})"
            )
            
            if self.paper_trading:
                # Simulate order execution
                return await self._simulate_order(
                    security_id, transaction_type, quantity, price
                )
            
            try:
                # Place order via Dhan API
                order = self.dhan.place_order(
                    security_id=security_id,
                    exchange_segment=self.dhan.NSE_FNO,
                    transaction_type=self.dhan.BUY if transaction_type == 'BUY' else self.dhan.SELL,
                    quantity=quantity,
                    order_type=self.dhan.LIMIT,
                    price=price,
                    product_type=self.dhan.INTRA,
                    validity=self.dhan.DAY
                )
                
                self._daily_stats.orders_placed += 1
                
                if order and 'orderId' in order:
                    logger.info(f"✅ Order placed: {order['orderId']}")
                    return OrderResponse(
                        order_id=order['orderId'],
                        status=OrderStatus.OPEN,
                        security_id=security_id,
                        quantity=quantity,
                        price=price,
                        filled_quantity=0
                    )
                else:
                    logger.error(f"Order failed: {order}")
                    return None
                    
            except Exception as e:
                logger.error(f"Order execution failed: {e}")
                return None
    
    async def _simulate_order(
        self,
        security_id: str,
        transaction_type: str,
        quantity: int,
        price: float
    ) -> OrderResponse:
        """Simulate order for paper trading."""
        import uuid
        
        order_id = f"PAPER_{uuid.uuid4().hex[:8]}"
        
        logger.info(f"📋 [PAPER] Order executed: {order_id}")
        
        self._daily_stats.orders_placed += 1
        
        return OrderResponse(
            order_id=order_id,
            status=OrderStatus.FILLED,
            security_id=security_id,
            quantity=quantity,
            price=price,
            filled_quantity=quantity,
            average_price=price
        )
    
    async def execute_signal(
        self,
        signal: Signal,
        spot_price: float,
        atm_strike: int
    ) -> Optional[Position]:
        """
        Execute a trading signal.
        
        Args:
            signal: BUY_CE or BUY_PE signal
            spot_price: Current spot price
            atm_strike: ATM strike price
            
        Returns:
            Position if order filled, None otherwise
        """
        if self._current_position is not None:
            logger.warning("Position already open. Ignoring signal.")
            return None
        
        # Determine option type
        option_type = OptionType.CALL if signal == Signal.BUY_CE else OptionType.PUT
        
        # Get option token
        token = await self.get_option_token(atm_strike, option_type)
        
        if not token:
            logger.error(f"Could not get token for {atm_strike} {option_type.value}")
            return None
        
        # Place entry order
        order = await self.place_order(
            security_id=token,
            transaction_type='BUY',
            quantity=QUANTITY
        )
        
        if not order or order.status == OrderStatus.REJECTED:
            logger.error("Entry order failed")
            return None
        
        # Calculate SL and Target
        entry_price = order.average_price or order.price
        
        # For options, SL/Target are based on option premium
        stop_loss = max(0.05, entry_price - STOP_LOSS_POINTS)
        target = entry_price + TARGET_POINTS
        
        # Create position
        position = Position(
            security_id=token,
            symbol=f"BANKNIFTY {atm_strike} {option_type.value}",
            option_type=option_type,
            strike=atm_strike,
            quantity=QUANTITY,
            entry_price=entry_price,
            entry_time=datetime.now(),
            order_id=order.order_id,
            stop_loss=stop_loss,
            target=target
        )
        
        self._current_position = position
        self._positions[order.order_id] = position
        
        logger.info(
            f"🎯 Position opened: {position.symbol} @ {entry_price:.2f} | "
            f"SL: {stop_loss:.2f} | Target: {target:.2f}"
        )
        
        return position
    
    async def check_exit_conditions(self, current_ltp: float) -> bool:
        """
        Check if current position should be exited.
        
        Args:
            current_ltp: Current option LTP
            
        Returns:
            True if position was exited
        """
        if self._current_position is None:
            return False
        
        position = self._current_position
        
        # Check stop loss
        if position.should_exit_sl(current_ltp):
            logger.warning(f"🛑 Stop Loss Hit! LTP: {current_ltp:.2f}")
            await self._exit_position(current_ltp, "STOP_LOSS")
            return True
        
        # Check target
        if position.should_exit_target(current_ltp):
            logger.info(f"🎉 Target Hit! LTP: {current_ltp:.2f}")
            await self._exit_position(current_ltp, "TARGET")
            return True
        
        return False
    
    async def _exit_position(self, exit_price: float, reason: str) -> None:
        """Exit the current position."""
        if self._current_position is None:
            return
        
        position = self._current_position
        
        # Place exit order
        order = await self.place_order(
            security_id=position.security_id,
            transaction_type='SELL',
            quantity=position.quantity,
            price=exit_price - SLIPPAGE_BUFFER  # Marketable limit for exit
        )
        
        if order:
            # Calculate P&L
            pnl = (exit_price - position.entry_price) * position.quantity
            
            # Update stats
            self._daily_stats.total_trades += 1
            self._daily_stats.total_pnl += pnl
            
            if pnl > 0:
                self._daily_stats.winning_trades += 1
            else:
                self._daily_stats.losing_trades += 1
            
            logger.info(
                f"📊 Position closed ({reason}): "
                f"Entry: {position.entry_price:.2f} | "
                f"Exit: {exit_price:.2f} | "
                f"P&L: {pnl:+.2f}"
            )
        
        # Clear position
        if position.order_id in self._positions:
            del self._positions[position.order_id]
        self._current_position = None
    
    async def update_trailing_sl(self, current_ltp: float) -> None:
        """
        Update trailing stop loss if price moved favorably.
        
        Args:
            current_ltp: Current option LTP
        """
        if self._current_position is None:
            return
        
        position = self._current_position
        
        # Calculate new SL (trail by maintaining fixed distance from high)
        new_sl = current_ltp - STOP_LOSS_POINTS
        
        # Only update if new SL is higher than current
        if new_sl <= position.stop_loss:
            return
        
        # Check throttle
        if not self._sl_update_throttle.should_update(current_ltp, new_sl):
            return
        
        # Update SL
        old_sl = position.stop_loss
        position.stop_loss = new_sl
        self._sl_update_throttle.mark_updated(new_sl)
        
        logger.debug(f"📈 SL Updated: {old_sl:.2f} → {new_sl:.2f}")
    
    @property
    def has_open_position(self) -> bool:
        """Check if there's an open position."""
        return self._current_position is not None
    
    @property
    def current_position(self) -> Optional[Position]:
        """Get current open position."""
        return self._current_position
    
    @property
    def daily_stats(self) -> TradeStats:
        """Get daily trading statistics."""
        return self._daily_stats
    
    def reset_daily_stats(self) -> None:
        """Reset daily statistics (call at start of new trading day)."""
        self._daily_stats = TradeStats(date=datetime.now().date())
        logger.info("Daily statistics reset")
    
    async def close_all_positions(self, reason: str = "MANUAL") -> None:
        """Emergency close all positions."""
        if self._current_position:
            # Get current LTP
            ltp = await self.get_option_ltp(self._current_position.security_id)
            if ltp:
                await self._exit_position(ltp, reason)
            else:
                logger.error("Could not get LTP for emergency exit")
