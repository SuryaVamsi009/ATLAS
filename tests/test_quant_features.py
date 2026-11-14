"""Tests for atlas.quant.features module."""

import numpy as np
import pytest

from atlas.quant.features import (
    atr,
    bollinger_bands,
    compute_all_features,
    ema,
    gap,
    macd,
    opening_range,
    opening_range_breakout,
    overnight_gap,
    rsi,
    session_vwap,
    sma,
    stochastic,
    vwap,
)


def create_test_bars(n: int = 50, start_price: float = 100.0, seed: int = 42) -> list:
    """Create synthetic OHLCV bars for testing.
    Format: [timestamp_ms, open, high, low, close, volume]
    """
    import pandas as pd

    rng = np.random.default_rng(seed)
    base_time = pd.Timestamp("2026-11-01 09:15", tz="Asia/Kolkata").timestamp() * 1000
    bars = []
    price = start_price
    for i in range(n):
        # Random walk
        change = rng.normal() * 0.5
        price = max(price + change, 1.0)
        open_price = price
        high = price + abs(rng.normal()) * 0.3
        low = price - abs(rng.normal()) * 0.3
        close = price + rng.normal() * 0.2
        volume = rng.uniform(1000, 2000)
        timestamp = base_time + i * 60000  # 1-minute bars
        bars.append([timestamp, open_price, high, low, close, volume])
    return bars


class TestRSI:
    def test_rsi_basic(self):
        bars = create_test_bars(30, 100.0)
        # Make it trend up
        for i, bar in enumerate(bars):
            bar[4] = 100 + i * 0.5  # close
            bar[1] = bar[4] - 0.1  # open
            bar[2] = bar[4] + 0.2  # high
            bar[3] = bar[4] - 0.2  # low
        result = rsi(bars, period=14)
        assert len(result) == len(bars)
        # Last value should be > 50 for uptrend
        assert result[-1] > 50
        assert result[-1] <= 100

    def test_rsi_downtrend(self):
        bars = create_test_bars(30, 110.0)
        # Make it trend down
        for i, bar in enumerate(bars):
            bar[4] = 110 - i * 0.5  # close
            bar[1] = bar[4] + 0.1  # open
            bar[2] = bar[4] + 0.2  # high
            bar[3] = bar[4] - 0.2  # low
        result = rsi(bars, period=14)
        assert result[-1] < 50
        assert result[-1] >= 0

    def test_rsi_insufficient_data(self):
        bars = create_test_bars(5, 100.0)
        result = rsi(bars, period=14)
        assert np.isnan(result[-1])

    def test_rsi_flat(self):
        # Create flat bars with no price changes
        bars = []
        base_time = 1730428800000  # 2026-11-01 09:15 IST in ms
        for i in range(20):
            bars.append([base_time + i * 60000, 100.0, 100.0, 100.0, 100.0, 1000.0])
        result = rsi(bars, period=14)
        # Flat line - no losses means RSI = 100 (Wilder's method)
        assert result[-1] == 100.0


class TestEMA:
    def test_ema_basic(self):
        bars = create_test_bars(30, 100.0)
        result = ema(bars, period=20)
        assert len(result) == len(bars)
        assert not np.isnan(result[-1])
        assert result[-1] > 0

    def test_ema_custom_price_type(self):
        bars = create_test_bars(30, 100.0)
        result = ema(bars, period=20, price_type="open")
        assert len(result) == len(bars)
        result_typical = ema(bars, period=20, price_type="typical")
        assert len(result_typical) == len(bars)

    def test_ema_insufficient_data(self):
        bars = create_test_bars(5, 100.0)
        result = ema(bars, period=20)
        assert np.isnan(result[-1])

    def test_ema_invalid_price_type(self):
        bars = create_test_bars(30, 100.0)
        with pytest.raises(ValueError, match="Unknown price_type"):
            ema(bars, period=20, price_type="invalid")


class TestATR:
    def test_atr_basic(self):
        bars = create_test_bars(30, 100.0)
        result = atr(bars, period=14)
        assert len(result) == len(bars)
        assert not np.isnan(result[-1])
        assert result[-1] > 0

    def test_atr_insufficient_data(self):
        bars = create_test_bars(5, 100.0)
        result = atr(bars, period=14)
        assert np.isnan(result[-1])


class TestVWAP:
    def test_vwap_basic(self):
        bars = create_test_bars(30, 100.0)
        result = vwap(bars)
        assert len(result) == len(bars)
        assert not np.isnan(result[-1])

    def test_vwap_anchored(self):
        bars = create_test_bars(30, 100.0)
        result = vwap(bars, anchor=10)
        assert len(result) == len(bars)
        # Values before anchor should be NaN
        assert np.isnan(result[9])
        assert not np.isnan(result[10])

    def test_session_vwap(self):
        bars = create_test_bars(30, 100.0)
        result = session_vwap(bars, session_start_idx=0)
        assert len(result) == len(bars)
        assert not np.isnan(result[-1])


class TestOpeningRange:
    def test_opening_range_basic(self):
        bars = create_test_bars(60, 100.0)
        or_high, or_low, start_idx, end_idx = opening_range(bars, range_minutes=15)
        assert not np.isnan(or_high)
        assert not np.isnan(or_low)
        assert or_high >= or_low
        assert start_idx >= 0
        assert end_idx > start_idx

    def test_opening_range_breakout_long(self):
        # Create deterministic bars with known timestamps
        bars = []
        base_time = 1730428800000  # 2026-11-01 09:15 IST in ms
        for i in range(60):
            bars.append([base_time + i * 60000, 100.0, 100.0, 100.0, 100.0, 1000.0])
        # Set opening range (first 15 bars)
        for i in range(15):
            bars[i][2] = 101.0  # high
            bars[i][3] = 99.0  # low
        # Breakout above at bar 20
        bars[20][2] = 102.0  # high breaks above
        bars[20][4] = 101.5  # close
        direction, breakout_price, level = opening_range_breakout(bars, range_minutes=15)
        assert direction == "LONG"
        assert breakout_price == 101.5
        assert level == 101.0

    def test_opening_range_breakout_short(self):
        # Create deterministic bars with known timestamps
        bars = []
        base_time = 1730428800000  # 2026-11-01 09:15 IST in ms
        for i in range(60):
            bars.append([base_time + i * 60000, 100.0, 100.0, 100.0, 100.0, 1000.0])
        # Set opening range (first 15 bars)
        for i in range(15):
            bars[i][2] = 101.0
            bars[i][3] = 99.0
        # Breakout below at bar 20
        bars[20][3] = 98.0  # low breaks below
        bars[20][4] = 98.5  # close
        direction, breakout_price, level = opening_range_breakout(bars, range_minutes=15)
        assert direction == "SHORT"
        assert breakout_price == 98.5
        assert level == 99.0

    def test_opening_range_no_breakout(self):
        bars = create_test_bars(60, 100.0)
        for i in range(15):
            bars[i][2] = 101.0
            bars[i][3] = 99.0
        # No breakout - stay within range
        for i in range(15, 60):
            bars[i][2] = 100.5
            bars[i][3] = 99.5
        direction, breakout_price, level = opening_range_breakout(bars, range_minutes=15)
        assert direction is None
        assert np.isnan(breakout_price)


class TestGap:
    def test_gap_up(self):
        bars = create_test_bars(10, 100.0)
        bars[0][1] = 102.0  # open
        bars[0][4] = 101.0  # close
        gap_pct, gap_type = gap(bars, prev_close=100.0)
        assert gap_pct > 0.5
        assert gap_type == "gap_up"

    def test_gap_down(self):
        bars = create_test_bars(10, 100.0)
        bars[0][1] = 98.0  # open
        bars[0][4] = 99.0  # close
        gap_pct, gap_type = gap(bars, prev_close=100.0)
        assert gap_pct < -0.5
        assert gap_type == "gap_down"

    def test_no_gap(self):
        bars = create_test_bars(10, 100.0)
        bars[0][1] = 100.2  # open
        bars[0][4] = 100.1  # close
        gap_pct, gap_type = gap(bars, prev_close=100.0)
        assert abs(gap_pct) <= 0.5
        assert gap_type == "no_gap"

    def test_overnight_gap(self):
        bars = create_test_bars(10, 100.0)
        bars[0][1] = 102.0
        gap_pct, gap_type = overnight_gap(bars, prev_day_close=100.0)
        assert gap_pct > 0.5
        assert gap_type == "gap_up"


class TestSMA:
    def test_sma_basic(self):
        bars = create_test_bars(30, 100.0)
        for i, bar in enumerate(bars):
            bar[4] = 100 + i  # close = 100, 101, 102...
        result = sma(bars, period=3)
        assert len(result) == len(bars)
        # SMA at index 2 (3rd bar) = (100+101+102)/3 = 101
        assert result[2] == 101.0
        assert result[5] == 104.0  # (103+104+105)/3

    def test_sma_insufficient_data(self):
        bars = create_test_bars(5, 100.0)
        result = sma(bars, period=10)
        assert np.isnan(result[-1])


class TestBollingerBands:
    def test_bollinger_bands_basic(self):
        bars = create_test_bars(50, 100.0)
        middle, upper, lower = bollinger_bands(bars, period=20)
        assert len(middle) == len(bars)
        assert len(upper) == len(bars)
        assert len(lower) == len(bars)
        # Upper >= middle >= lower for valid values
        valid = ~np.isnan(middle)
        assert (upper[valid] >= middle[valid]).all()
        assert (middle[valid] >= lower[valid]).all()


class TestMACD:
    def test_macd_basic(self):
        bars = create_test_bars(50, 100.0)
        macd_line, signal_line, histogram = macd(bars)
        assert len(macd_line) == len(bars)
        assert len(signal_line) == len(bars)
        assert len(histogram) == len(bars)
        # Histogram = MACD - Signal
        valid = ~np.isnan(histogram)
        np.testing.assert_array_almost_equal(
            histogram[valid], macd_line[valid] - signal_line[valid]
        )

    def test_macd_custom_periods(self):
        bars = create_test_bars(50, 100.0)
        macd_line, signal_line, histogram = macd(
            bars, fast_period=8, slow_period=21, signal_period=5
        )
        assert len(macd_line) == len(bars)


class TestStochastic:
    def test_stochastic_basic(self):
        bars = create_test_bars(30, 100.0)
        k, d = stochastic(bars, k_period=14, d_period=3)
        assert len(k) == len(bars)
        assert len(d) == len(bars)
        # %K should be between 0 and 100
        valid_k = ~np.isnan(k)
        assert (k[valid_k] >= 0).all()
        assert (k[valid_k] <= 100).all()

    def test_stochastic_insufficient_data(self):
        bars = create_test_bars(5, 100.0)
        k, d = stochastic(bars, k_period=14)
        assert np.isnan(k[-1])
        assert np.isnan(d[-1])


class TestComputeAllFeatures:
    def test_compute_all_features(self):
        bars = create_test_bars(100, 100.0)
        features = compute_all_features(bars)
        expected_keys = [
            "rsi",
            "ema_20",
            "ema_50",
            "atr",
            "vwap",
            "macd",
            "macd_signal",
            "macd_hist",
            "bb_middle",
            "bb_upper",
            "bb_lower",
            "stoch_k",
            "stoch_d",
            "opening_range_high",
            "opening_range_low",
            "gap_pct",
            "gap_type",
        ]
        for key in expected_keys:
            assert key in features, f"Missing feature: {key}"
        # All arrays should have same length as bars (except scalars)
        for key, value in features.items():
            if isinstance(value, list):
                assert len(value) == len(bars), f"Feature {key} has wrong length"
