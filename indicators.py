"""
Technical Indicators for Bank Nifty Scalping Bot.
Uses TA-Lib for high-performance indicator calculation.
"""

from typing import Optional

import numpy as np
import pandas as pd

try:
    import talib

    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    print("[WARNING] TA-Lib not installed. Using pure Python fallback (slower).")

from config import EMA_PERIOD, RSI_PERIOD
from utils import logger


def calculate_ema(prices: np.ndarray, period: int = EMA_PERIOD) -> np.ndarray:
    """
    Calculate Exponential Moving Average.

    Args:
        prices: Array of closing prices
        period: EMA period (default: 9)

    Returns:
        Array of EMA values
    """
    if TALIB_AVAILABLE:
        return talib.EMA(prices.astype(float), timeperiod=period)
    else:
        # Pure Python fallback
        return _ema_python(prices, period)


def _ema_python(prices: np.ndarray, period: int) -> np.ndarray:
    """Pure Python EMA calculation."""
    ema = np.full_like(prices, np.nan, dtype=float)
    if len(prices) < period:
        return ema

    # First EMA is SMA
    ema[period - 1] = np.mean(prices[:period])

    # EMA formula: EMA_today = (Price_today * k) + (EMA_yesterday * (1-k))
    k = 2 / (period + 1)

    for i in range(period, len(prices)):
        ema[i] = (prices[i] * k) + (ema[i - 1] * (1 - k))

    return ema


def calculate_rsi(prices: np.ndarray, period: int = RSI_PERIOD) -> np.ndarray:
    """
    Calculate Relative Strength Index.

    Args:
        prices: Array of closing prices
        period: RSI period (default: 14)

    Returns:
        Array of RSI values (0-100)
    """
    if TALIB_AVAILABLE:
        return talib.RSI(prices.astype(float), timeperiod=period)
    else:
        return _rsi_python(prices, period)


def _rsi_python(prices: np.ndarray, period: int) -> np.ndarray:
    """Pure Python RSI calculation."""
    rsi = np.full_like(prices, np.nan, dtype=float)
    if len(prices) < period + 1:
        return rsi

    # Calculate price changes
    deltas = np.diff(prices)

    # Separate gains and losses
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    # Initial averages
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(prices)):
        if avg_loss == 0:
            rsi[i] = 100
        else:
            rs = avg_gain / avg_loss
            rsi[i] = 100 - (100 / (1 + rs))

        if i < len(gains):
            # Smoothed averages
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    return rsi


def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculate Volume Weighted Average Price.
    VWAP = Cumulative(TypicalPrice * Volume) / Cumulative(Volume)

    Args:
        df: DataFrame with 'High', 'Low', 'Close', 'Volume' columns

    Returns:
        Series of VWAP values
    """
    # Typical Price = (High + Low + Close) / 3
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3

    # VWAP = Cumulative(TP * Volume) / Cumulative(Volume)
    cum_tp_vol = (typical_price * df["Volume"]).cumsum()
    cum_vol = df["Volume"].cumsum()

    vwap = cum_tp_vol / cum_vol

    return vwap


def calculate_vwap_from_arrays(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, volume: np.ndarray
) -> np.ndarray:
    """
    Calculate VWAP from numpy arrays.

    Args:
        high: Array of high prices
        low: Array of low prices
        close: Array of closing prices
        volume: Array of volumes

    Returns:
        Array of VWAP values
    """
    typical_price = (high + low + close) / 3
    cum_tp_vol = np.cumsum(typical_price * volume)
    cum_vol = np.cumsum(volume)

    # Avoid division by zero
    vwap = np.where(cum_vol > 0, cum_tp_vol / cum_vol, 0)

    return vwap


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate all indicators for the strategy.

    Args:
        df: DataFrame with OHLCV data

    Returns:
        DataFrame with added indicator columns
    """
    df = df.copy()

    # Get close prices as numpy array
    close = df["Close"].values.astype(float)

    # EMA 9
    df["ema_9"] = calculate_ema(close, EMA_PERIOD)

    # RSI 14
    df["rsi"] = calculate_rsi(close, RSI_PERIOD)

    # VWAP
    df["vwap"] = calculate_vwap(df)

    return df


def get_latest_indicators(df: pd.DataFrame) -> Optional[dict]:
    """
    Calculate indicators and return only the latest values.

    Args:
        df: DataFrame with OHLCV data

    Returns:
        Dict with latest indicator values or None if insufficient data
    """
    if len(df) < RSI_PERIOD + 1:
        logger.debug(f"Insufficient data for indicators: {len(df)} candles")
        return None

    df_with_indicators = calculate_all_indicators(df)
    latest = df_with_indicators.iloc[-1]

    # Check for NaN values
    if pd.isna(latest["ema_9"]) or pd.isna(latest["rsi"]) or pd.isna(latest["vwap"]):
        logger.debug("Indicator values contain NaN")
        return None

    return {
        "close": latest["Close"],
        "ema_9": latest["ema_9"],
        "rsi": latest["rsi"],
        "vwap": latest["vwap"],
        "high": latest["High"],
        "low": latest["Low"],
        "volume": latest["Volume"],
    }


def detect_rsi_crossover(
    rsi_values: np.ndarray, threshold: float, direction: str = "above"
) -> bool:
    """
    Detect if RSI has crossed a threshold.

    Args:
        rsi_values: Array of RSI values (at least 2 values)
        threshold: RSI level to check
        direction: 'above' for bullish, 'below' for bearish

    Returns:
        True if crossover detected
    """
    if len(rsi_values) < 2:
        return False

    prev_rsi = rsi_values[-2]
    curr_rsi = rsi_values[-1]

    if pd.isna(prev_rsi) or pd.isna(curr_rsi):
        return False

    if direction == "above":
        return prev_rsi <= threshold and curr_rsi > threshold
    else:
        return prev_rsi >= threshold and curr_rsi < threshold


def calculate_atr(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14
) -> np.ndarray:
    """
    Calculate Average True Range (for volatility-based stops).

    Args:
        high: Array of high prices
        low: Array of low prices
        close: Array of closing prices
        period: ATR period

    Returns:
        Array of ATR values
    """
    if TALIB_AVAILABLE:
        return talib.ATR(
            high.astype(float),
            low.astype(float),
            close.astype(float),
            timeperiod=period,
        )
    else:
        return _atr_python(high, low, close, period)


def _atr_python(
    high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int
) -> np.ndarray:
    """Pure Python ATR calculation."""
    atr = np.full_like(close, np.nan, dtype=float)
    if len(close) < period + 1:
        return atr

    # Calculate True Range
    tr = np.zeros(len(close))
    tr[0] = high[0] - low[0]

    for i in range(1, len(close)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    # First ATR is simple average
    atr[period] = np.mean(tr[1 : period + 1])

    # Subsequent ATRs are smoothed
    for i in range(period + 1, len(close)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr
