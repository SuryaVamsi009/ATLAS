"""Pure feature functions for ATLAS quant layer.

All functions are pure (no side effects) and operate on OHLCV bar arrays.
These are reused by StateSnapshot instead of duplicating indicator code.

Bar format: [timestamp_ms, open, high, low, close, volume]
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _extract_closes(bars: list[list[float]]) -> np.ndarray:
    """Extract close prices from bars."""
    return np.array([bar[4] for bar in bars], dtype=np.float64)


def _extract_highs(bars: list[list[float]]) -> np.ndarray:
    """Extract high prices from bars."""
    return np.array([bar[2] for bar in bars], dtype=np.float64)


def _extract_lows(bars: list[list[float]]) -> np.ndarray:
    """Extract low prices from bars."""
    return np.array([bar[3] for bar in bars], dtype=np.float64)


def _extract_opens(bars: list[list[float]]) -> np.ndarray:
    """Extract open prices from bars."""
    return np.array([bar[1] for bar in bars], dtype=np.float64)


def _extract_volumes(bars: list[list[float]]) -> np.ndarray:
    """Extract volumes from bars."""
    return np.array([bar[5] for bar in bars], dtype=np.float64)


def _extract_typical_price(bars: list[list[float]]) -> np.ndarray:
    """Extract typical price (H+L+C)/3 from bars."""
    highs = _extract_highs(bars)
    lows = _extract_lows(bars)
    closes = _extract_closes(bars)
    return (highs + lows + closes) / 3.0  # type: ignore


# ---------------------------------------------------------------------------
# RSI (Relative Strength Index)
# ---------------------------------------------------------------------------

def rsi(bars: list[list[float]], period: int = 14) -> np.ndarray:
    """Calculate Relative Strength Index (RSI).

    Args:
        bars: OHLCV bars
        period: RSI period (default 14)

    Returns:
        Array of RSI values (same length as bars, NaN for first `period` bars)
    """
    if len(bars) < period + 1:
        return np.full(len(bars), np.nan)

    closes = _extract_closes(bars)
    deltas = np.diff(closes)

    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Initial average gain/loss (simple average for first period)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    rsi_values = np.full(len(bars), np.nan)

    if avg_loss == 0:
        rsi_values[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi_values[period] = 100.0 - (100.0 / (1.0 + rs))

    # Wilder's smoothing for subsequent values
    for i in range(period + 1, len(bars)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period

        if avg_loss == 0:
            rsi_values[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_values[i] = 100.0 - (100.0 / (1.0 + rs))

    return rsi_values


# ---------------------------------------------------------------------------
# EMA (Exponential Moving Average)
# ---------------------------------------------------------------------------

def ema(bars: list[list[float]], period: int = 20, price_type: str = "close") -> np.ndarray:
    """Calculate Exponential Moving Average (EMA).

    Args:
        bars: OHLCV bars
        period: EMA period (default 20)
        price_type: Price to use - "close", "open", "high", "low", "typical"

    Returns:
        Array of EMA values (same length as bars, NaN for first `period-1` bars)
    """
    if len(bars) < period:
        return np.full(len(bars), np.nan)

    # Extract price series
    if price_type == "close":
        prices = _extract_closes(bars)
    elif price_type == "open":
        prices = _extract_opens(bars)
    elif price_type == "high":
        prices = _extract_highs(bars)
    elif price_type == "low":
        prices = _extract_lows(bars)
    elif price_type == "typical":
        prices = _extract_typical_price(bars)
    else:
        raise ValueError(f"Unknown price_type: {price_type}")

    ema_values = np.full(len(bars), np.nan)
    alpha = 2.0 / (period + 1.0)

    # First EMA is SMA of first `period` values
    ema_values[period - 1] = np.mean(prices[:period])

    # Subsequent EMAs
    for i in range(period, len(bars)):
        ema_values[i] = alpha * prices[i] + (1.0 - alpha) * ema_values[i - 1]

    return ema_values


# ---------------------------------------------------------------------------
# ATR (Average True Range)
# ---------------------------------------------------------------------------

def atr(bars: list[list[float]], period: int = 14) -> np.ndarray:
    """Calculate Average True Range (ATR).

    Args:
        bars: OHLCV bars
        period: ATR period (default 14)

    Returns:
        Array of ATR values (same length as bars, NaN for first `period` bars)
    """
    if len(bars) < period + 1:
        return np.full(len(bars), np.nan)

    highs = _extract_highs(bars)
    lows = _extract_lows(bars)
    closes = _extract_closes(bars)

    # True Range = max(high - low, |high - prev_close|, |low - prev_close|)
    tr = np.zeros(len(bars))
    tr[0] = highs[0] - lows[0]

    for i in range(1, len(bars)):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    atr_values = np.full(len(bars), np.nan)

    # First ATR is simple average of first `period` TR values
    atr_values[period] = np.mean(tr[1:period + 1])

    # Wilder's smoothing
    for i in range(period + 1, len(bars)):
        atr_values[i] = (atr_values[i - 1] * (period - 1) + tr[i]) / period

    return atr_values


# ---------------------------------------------------------------------------
# VWAP (Volume Weighted Average Price)
# ---------------------------------------------------------------------------

def vwap(bars: list[list[float]], anchor: int | None = None) -> np.ndarray:
    """Calculate Volume Weighted Average Price (VWAP).

    Args:
        bars: OHLCV bars
        anchor: Optional index to anchor VWAP from (e.g., session open).
                If None, calculates cumulative VWAP from start.

    Returns:
        Array of VWAP values (same length as bars)
    """
    if not bars:
        return np.array([])

    typical_prices = _extract_typical_price(bars)
    volumes = _extract_volumes(bars)

    vwap_values = np.full(len(bars), np.nan)

    if anchor is not None and 0 <= anchor < len(bars):
        # Anchored VWAP from anchor point
        cum_pv = 0.0
        cum_vol = 0.0
        for i in range(anchor, len(bars)):
            cum_pv += typical_prices[i] * volumes[i]
            cum_vol += volumes[i]
            if cum_vol > 0:
                vwap_values[i] = cum_pv / cum_vol
    else:
        # Cumulative VWAP from start
        cum_pv = np.cumsum(typical_prices * volumes)
        cum_vol = np.cumsum(volumes)
        vwap_values = np.where(cum_vol > 0, cum_pv / cum_vol, np.nan)  # type: ignore[assignment]

    return vwap_values


def session_vwap(bars: list[list[float]], session_start_idx: int = 0) -> np.ndarray:
    """Calculate session VWAP anchored at session start.

    Args:
        bars: OHLCV bars
        session_start_idx: Index of session open bar

    Returns:
        Array of session VWAP values
    """
    return vwap(bars, anchor=session_start_idx)


# ---------------------------------------------------------------------------
# Opening Range
# ---------------------------------------------------------------------------

def opening_range(
    bars: list[list[float]],
    range_minutes: int = 15,
    session_start_time: str = "09:15",
) -> tuple[float, float, int, int]:
    """Calculate opening range high/low for the first N minutes.

    Args:
        bars: OHLCV bars (assumed to be 1-minute bars in IST)
        range_minutes: Number of minutes for opening range (default 15)
        session_start_time: Session start time in HH:MM format (default "09:15")

    Returns:
        Tuple of (opening_range_high, opening_range_low, start_idx, end_idx)
    """
    if not bars:
        return (np.nan, np.nan, -1, -1)

    # Find session start index
    start_idx = -1
    for i, bar in enumerate(bars):
        ts_ms = bar[0]
        dt = pd.Timestamp(ts_ms, unit="ms", tz="UTC").tz_convert("Asia/Kolkata")
        if dt.strftime("%H:%M") == session_start_time:
            start_idx = i
            break

    if start_idx == -1:
        # Default to first bar if session start not found
        start_idx = 0

    end_idx = min(start_idx + range_minutes, len(bars))

    if start_idx >= end_idx:
        return (np.nan, np.nan, start_idx, end_idx)

    range_bars = bars[start_idx:end_idx]
    highs = [bar[2] for bar in range_bars]
    lows = [bar[3] for bar in range_bars]

    return (max(highs), min(lows), start_idx, end_idx)


def opening_range_breakout(
    bars: list[list[float]],
    range_minutes: int = 15,
    session_start_time: str = "09:15",
) -> tuple[str | None, float, float]:
    """Detect opening range breakout.

    Args:
        bars: OHLCV bars
        range_minutes: Opening range minutes
        session_start_time: Session start time

    Returns:
        Tuple of (direction, breakout_price, range_high/low)
        direction: "LONG" if break above, "SHORT" if break below, None if no breakout
    """
    or_high, or_low, start_idx, end_idx = opening_range(bars, range_minutes, session_start_time)

    if np.isnan(or_high) or np.isnan(or_low):
        return (None, np.nan, np.nan)

    # Check bars after opening range for breakout
    for i in range(end_idx, len(bars)):
        high = bars[i][2]
        low = bars[i][3]
        close = bars[i][4]

        if high > or_high:
            return ("LONG", close, or_high)
        if low < or_low:
            return ("SHORT", close, or_low)

    return (None, np.nan, np.nan)


# ---------------------------------------------------------------------------
# Gap Detection
# ---------------------------------------------------------------------------

def gap(bars: list[list[float]], prev_close: float | None = None) -> tuple[float, str]:
    """Calculate gap from previous close to current open.

    Args:
        bars: OHLCV bars (at least 1 bar)
        prev_close: Previous session's close price. If None, uses first bar's close
                    as reference (for intraday gaps within session).

    Returns:
        Tuple of (gap_pct, gap_type)
        gap_pct: Percentage gap (positive = gap up, negative = gap down)
        gap_type: "gap_up", "gap_down", "no_gap", or "unknown"
    """
    if not bars:
        return (0.0, "unknown")

    current_open = bars[0][1]

    if prev_close is None:
        # Intraday: compare to previous bar's close (if available)
        if len(bars) > 1:
            prev_close = bars[1][4]  # Previous bar's close
        else:
            return (0.0, "unknown")

    if prev_close == 0:
        return (0.0, "unknown")

    gap_pct = ((current_open - prev_close) / prev_close) * 100.0

    if gap_pct > 0.5:  # > 0.5% gap up
        return (gap_pct, "gap_up")
    elif gap_pct < -0.5:  # > 0.5% gap down
        return (gap_pct, "gap_down")
    else:
        return (gap_pct, "no_gap")


def overnight_gap(bars: list[list[float]], prev_day_close: float) -> tuple[float, str]:
    """Calculate overnight gap from previous day's close to today's open.

    Args:
        bars: Today's bars (at least 1 bar)
        prev_day_close: Previous trading day's close price

    Returns:
        Tuple of (gap_pct, gap_type)
    """
    return gap(bars, prev_close=prev_day_close)


# ---------------------------------------------------------------------------
# Additional Features
# ---------------------------------------------------------------------------

def sma(bars: list[list[float]], period: int = 20, price_type: str = "close") -> np.ndarray:
    """Simple Moving Average."""
    if len(bars) < period:
        return np.full(len(bars), np.nan)

    if price_type == "close":
        prices = _extract_closes(bars)
    elif price_type == "open":
        prices = _extract_opens(bars)
    elif price_type == "high":
        prices = _extract_highs(bars)
    elif price_type == "low":
        prices = _extract_lows(bars)
    elif price_type == "typical":
        prices = _extract_typical_price(bars)
    else:
        raise ValueError(f"Unknown price_type: {price_type}")

    sma_values = np.full(len(bars), np.nan)
    for i in range(period - 1, len(bars)):
        sma_values[i] = np.mean(prices[i - period + 1:i + 1])

    return sma_values


def bollinger_bands(
    bars: list[list[float]],
    period: int = 20,
    num_std: float = 2.0,
    price_type: str = "close",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands (middle, upper, lower)."""
    middle = sma(bars, period, price_type)
    std = np.full(len(bars), np.nan)

    if price_type == "close":
        prices = _extract_closes(bars)
    elif price_type == "typical":
        prices = _extract_typical_price(bars)
    else:
        prices = _extract_closes(bars)

    for i in range(period - 1, len(bars)):
        std[i] = np.std(prices[i - period + 1:i + 1])

    upper = middle + num_std * std
    lower = middle - num_std * std

    return middle, upper, lower


def macd(
    bars: list[list[float]],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """MACD (macd_line, signal_line, histogram)."""
    fast_ema = ema(bars, fast_period)
    slow_ema = ema(bars, slow_period)

    macd_line = fast_ema - slow_ema
    signal_line = np.full(len(bars), np.nan)

    # Calculate signal line (EMA of MACD line)
    valid_start = max(fast_period, slow_period) + signal_period - 1
    if valid_start < len(bars):
        # First signal is SMA of first `signal_period` MACD values
        first_valid = max(fast_period, slow_period) - 1
        signal_line[valid_start] = np.mean(macd_line[first_valid:valid_start + 1])

        alpha = 2.0 / (signal_period + 1.0)
        for i in range(valid_start + 1, len(bars)):
            if not np.isnan(macd_line[i]):
                signal_line[i] = alpha * macd_line[i] + (1.0 - alpha) * signal_line[i - 1]

    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def stochastic(
    bars: list[list[float]],
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """Stochastic Oscillator (%K, %D)."""
    if len(bars) < k_period:
        return (np.full(len(bars), np.nan), np.full(len(bars), np.nan))

    highs = _extract_highs(bars)
    lows = _extract_lows(bars)
    closes = _extract_closes(bars)

    k_values = np.full(len(bars), np.nan)

    for i in range(k_period - 1, len(bars)):
        highest_high = np.max(highs[i - k_period + 1:i + 1])
        lowest_low = np.min(lows[i - k_period + 1:i + 1])

        if highest_high != lowest_low:
            k_values[i] = 100.0 * (closes[i] - lowest_low) / (highest_high - lowest_low)
        else:
            k_values[i] = 50.0

    # %D is SMA of %K
    d_values = np.full(len(bars), np.nan)
    for i in range(k_period - 1 + d_period - 1, len(bars)):
        d_values[i] = np.mean(k_values[i - d_period + 1:i + 1])

    return k_values, d_values


# ---------------------------------------------------------------------------
# Compute all features at once (for StateSnapshot)
# ---------------------------------------------------------------------------

def compute_all_features(bars: list[list[float]]) -> dict:
    """Compute all technical features for a bar series.

    Returns a dict with all indicator arrays, aligned to bar indices.
    Used by StateSnapshot to enrich market data.

    Args:
        bars: OHLCV bars

    Returns:
        Dict with keys: rsi, ema_20, ema_50, atr, vwap, macd, macd_signal,
        macd_hist, bb_middle, bb_upper, bb_lower, stoch_k, stoch_d,
        opening_range_high, opening_range_low, gap_pct, gap_type
    """
    if not bars:
        return {}

    features: dict[str, Any] = {}

    # RSI
    features["rsi"] = rsi(bars, 14).tolist()

    # EMAs
    features["ema_20"] = ema(bars, 20).tolist()
    features["ema_50"] = ema(bars, 50).tolist()

    # ATR
    features["atr"] = atr(bars, 14).tolist()

    # VWAP (session anchored)
    features["vwap"] = session_vwap(bars).tolist()

    # MACD
    macd_line, signal_line, histogram = macd(bars)
    features["macd"] = macd_line.tolist()
    features["macd_signal"] = signal_line.tolist()
    features["macd_hist"] = histogram.tolist()

    # Bollinger Bands
    bb_mid, bb_up, bb_low = bollinger_bands(bars)
    features["bb_middle"] = bb_mid.tolist()
    features["bb_upper"] = bb_up.tolist()
    features["bb_lower"] = bb_low.tolist()

    # Stochastic
    stoch_k, stoch_d = stochastic(bars)
    features["stoch_k"] = stoch_k.tolist()
    features["stoch_d"] = stoch_d.tolist()

    # Opening Range
    or_high, or_low, _, _ = opening_range(bars)
    features["opening_range_high"] = or_high
    features["opening_range_low"] = or_low

    # Gap
    gap_pct, gap_type = gap(bars)
    features["gap_pct"] = gap_pct
    features["gap_type"] = gap_type

    return features
