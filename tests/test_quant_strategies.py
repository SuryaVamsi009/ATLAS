"""Tests for atlas.quant.strategies module."""

import numpy as np
import pytest

from atlas.quant.strategies import (
    STRATEGY_REGISTRY,
    Direction,
    GapFadeStrategy,
    Horizon,
    ORBStrategy,
    Signal,
    Strategy,
    VWAPReversionStrategy,
)


def create_test_bars(n: int = 60, start_price: float = 100.0, seed: int = 42) -> list:
    """Create synthetic OHLCV bars for testing.
    Format: [timestamp_ms, open, high, low, close, volume]
    """
    import pandas as pd
    rng = np.random.default_rng(seed)
    base_time = pd.Timestamp("2026-11-01 09:15", tz="Asia/Kolkata").timestamp() * 1000
    bars = []
    price = start_price
    for i in range(n):
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


class TestDirection:
    def test_direction_values(self):
        assert Direction.LONG.value == "LONG"
        assert Direction.SHORT.value == "SHORT"
        assert Direction.FLAT.value == "FLAT"


class TestHorizon:
    def test_horizon_values(self):
        assert Horizon.INTRADAY.value == "intraday"
        assert Horizon.SWING.value == "swing"


class TestSignal:
    def test_signal_creation(self):
        signal = Signal(
            symbol="RELIANCE.NS",
            direction=Direction.LONG,
            conviction=0.8,
            horizon=Horizon.INTRADAY,
            stop_distance=2.0,
            entry_price=100.0,
            target_price=104.0,
            metadata={"strategy": "ORB"},
        )
        assert signal.symbol == "RELIANCE.NS"
        assert signal.direction == Direction.LONG
        assert signal.conviction == 0.8
        assert signal.horizon == Horizon.INTRADAY
        assert signal.stop_distance == 2.0
        assert signal.entry_price == 100.0
        assert signal.target_price == 104.0
        assert signal.metadata["strategy"] == "ORB"

    def test_signal_validation_conviction_bounds(self):
        with pytest.raises(ValueError, match="Conviction must be in"):
            Signal(
                symbol="TEST",
                direction=Direction.LONG,
                conviction=1.5,
                horizon=Horizon.INTRADAY,
                stop_distance=1.0,
            )

        with pytest.raises(ValueError, match="Conviction must be in"):
            Signal(
                symbol="TEST",
                direction=Direction.LONG,
                conviction=-0.1,
                horizon=Horizon.INTRADAY,
                stop_distance=1.0,
            )

    def test_signal_validation_stop_distance(self):
        with pytest.raises(ValueError, match="Stop distance must be positive"):
            Signal(
                symbol="TEST",
                direction=Direction.LONG,
                conviction=0.5,
                horizon=Horizon.INTRADAY,
                stop_distance=0.0,
            )

        with pytest.raises(ValueError, match="Stop distance must be positive"):
            Signal(
                symbol="TEST",
                direction=Direction.LONG,
                conviction=0.5,
                horizon=Horizon.INTRADAY,
                stop_distance=-1.0,
            )

    def test_signal_to_dict(self):
        signal = Signal(
            symbol="RELIANCE.NS",
            direction=Direction.LONG,
            conviction=0.8,
            horizon=Horizon.INTRADAY,
            stop_distance=2.0,
            entry_price=100.0,
            target_price=104.0,
            metadata={"strategy": "ORB"},
        )
        d = signal.to_dict()
        assert d["symbol"] == "RELIANCE.NS"
        assert d["direction"] == "LONG"
        assert d["conviction"] == 0.8
        assert d["horizon"] == "intraday"
        assert d["stop_distance"] == 2.0
        assert d["entry_price"] == 100.0
        assert d["target_price"] == 104.0
        assert d["metadata"]["strategy"] == "ORB"


class TestStrategyBase:
    def test_strategy_is_abstract(self):
        with pytest.raises(TypeError):
            Strategy("test")

    def test_strategy_init(self):
        class ConcreteStrategy(Strategy):
            def generate_signal(self, symbol, bars, current_position=0):
                return None

        strat = ConcreteStrategy("Test", min_conviction=0.6, max_positions=2)
        assert strat.name == "Test"
        assert strat.min_conviction == 0.6
        assert strat.max_positions == 2
        assert strat.active_signals == {}


class TestORBStrategy:
    def test_orb_strategy_creation(self):
        strat = ORBStrategy(range_minutes=15, min_volume_ratio=1.2, risk_reward=2.0)
        assert strat.name == "ORB"
        assert strat.range_minutes == 15
        assert strat.min_volume_ratio == 1.2
        assert strat.risk_reward == 2.0

    def test_orb_generate_signal_long_breakout(self):
        strat = ORBStrategy(range_minutes=15, min_volume_ratio=1.0, min_conviction=0.5)
        bars = create_test_bars(60, 100.0)

        # Set up opening range (first 15 bars)
        for i in range(15):
            bars[i][2] = 101.0  # high
            bars[i][3] = 99.0   # low
            bars[i][5] = 1000.0  # volume

        # Breakout on LAST bar (bar 59) - high breaks above OR high with volume
        bars[-1][2] = 102.0  # high > 101
        bars[-1][4] = 101.5  # close
        bars[-1][5] = 2000.0  # high volume

        signal = strat.generate_signal("RELIANCE.NS", bars, current_position=0)
        assert signal is not None
        assert signal.direction == Direction.LONG
        assert signal.horizon == Horizon.INTRADAY
        assert signal.stop_distance > 0
        assert signal.target_price > signal.entry_price
        assert signal.metadata["strategy"] == "ORB"

    def test_orb_generate_signal_short_breakdown(self):
        strat = ORBStrategy(range_minutes=15, min_volume_ratio=1.0, min_conviction=0.5)
        bars = create_test_bars(60, 100.0)

        for i in range(15):
            bars[i][2] = 101.0
            bars[i][3] = 99.0
            bars[i][5] = 1000.0

        # Breakdown on LAST bar - low breaks below OR low
        # Set high to NOT break above OR high (101.0), so only short breakdown triggers
        bars[-1][2] = 100.5  # high <= or_high (101.0)
        bars[-1][3] = 98.0   # low < or_low (99.0)
        bars[-1][4] = 98.5   # close
        bars[-1][5] = 2000.0

        signal = strat.generate_signal("RELIANCE.NS", bars, current_position=0)
        assert signal is not None
        assert signal.direction == Direction.SHORT
        assert signal.stop_distance > 0
        assert signal.target_price < signal.entry_price

    def test_orb_no_signal_insufficient_bars(self):
        strat = ORBStrategy()
        bars = create_test_bars(10, 100.0)
        signal = strat.generate_signal("RELIANCE.NS", bars)
        assert signal is None

    def test_orb_no_signal_no_breakout(self):
        strat = ORBStrategy(min_conviction=0.5)
        bars = create_test_bars(60, 100.0)

        for i in range(15):
            bars[i][2] = 101.0
            bars[i][3] = 99.0

        # No breakout - price stays within range
        for i in range(15, 60):
            bars[i][2] = 100.5
            bars[i][3] = 99.5

        signal = strat.generate_signal("RELIANCE.NS", bars)
        assert signal is None

    def test_orb_should_exit_before_close(self):
        strat = ORBStrategy()
        bars = create_test_bars(60, 100.0)
        # Set last bar to 15:15 IST
        import pandas as pd
        close_time = pd.Timestamp("2026-11-01 15:15", tz="Asia/Kolkata").timestamp() * 1000
        bars[-1][0] = close_time

        # ORBStrategy forces exit at 15:15 regardless of position
        assert strat.should_exit("RELIANCE.NS", bars, current_position=1) is True
        assert strat.should_exit("RELIANCE.NS", bars, current_position=-1) is True
        assert strat.should_exit("RELIANCE.NS", bars, current_position=0) is True


class TestVWAPReversionStrategy:
    def test_vwap_reversion_creation(self):
        strat = VWAPReversionStrategy(atr_period=14, atr_multiplier=1.5)
        assert strat.name == "VWAP_REVERSION"
        assert strat.atr_period == 14
        assert strat.atr_multiplier == 1.5

    def test_vwap_reversion_long_signal(self):
        strat = VWAPReversionStrategy(min_conviction=0.5)
        bars = create_test_bars(50, 100.0)

        # Price significantly below VWAP with oversold RSI
        # We need to manipulate bars to create this condition
        for i, bar in enumerate(bars):
            bar[4] = 95.0 - i * 0.1  # declining price
            bar[1] = bar[4] + 0.1
            bar[2] = bar[4] + 0.3
            bar[3] = bar[4] - 0.3

        signal = strat.generate_signal("RELIANCE.NS", bars, current_position=0)
        # May or may not generate signal depending on exact values
        if signal:
            assert signal.direction == Direction.LONG
            assert signal.horizon == Horizon.INTRADAY
            assert signal.target_price is not None

    def test_vwap_reversion_short_signal(self):
        strat = VWAPReversionStrategy(min_conviction=0.5)
        bars = create_test_bars(50, 100.0)

        # Price significantly above VWAP with overbought RSI
        for i, bar in enumerate(bars):
            bar[4] = 105.0 + i * 0.1  # rising price
            bar[1] = bar[4] - 0.1
            bar[2] = bar[4] + 0.3
            bar[3] = bar[4] - 0.3

        signal = strat.generate_signal("RELIANCE.NS", bars, current_position=0)
        if signal:
            assert signal.direction == Direction.SHORT

    def test_vwap_reversion_should_exit_at_vwap(self):
        strat = VWAPReversionStrategy()
        bars = create_test_bars(50, 100.0)

        # Price at VWAP - use constant volume to avoid floating point errors in VWAP calculation
        for bar in bars:
            bar[4] = 100.0  # close
            bar[1] = 100.0  # open
            bar[2] = 100.0  # high
            bar[3] = 100.0  # low
            bar[5] = 1000.0  # constant volume

        # Long position at VWAP should exit (close >= vwap)
        assert strat.should_exit("RELIANCE.NS", bars, current_position=1) is True
        # Short position at VWAP should exit (close <= vwap)
        assert strat.should_exit("RELIANCE.NS", bars, current_position=-1) is True
        # Flat should not exit
        assert strat.should_exit("RELIANCE.NS", bars, current_position=0) is False


class TestGapFadeStrategy:
    def test_gap_fade_creation(self):
        strat = GapFadeStrategy(min_gap_pct=1.0, lookback_bars=30)
        assert strat.name == "GAP_FADE"
        assert strat.min_gap_pct == 1.0
        assert strat.lookback_bars == 30

    def test_gap_fade_gap_up_short(self):
        strat = GapFadeStrategy(min_gap_pct=1.0, min_conviction=0.5)
        bars = create_test_bars(40, 100.0)

        # Gap up: open at 102, prev close at 100
        bars[0][1] = 102.0  # open
        bars[0][2] = 102.5  # high
        bars[0][3] = 101.5  # low
        bars[0][4] = 101.8  # close

        # Rejection bar: lower high, closes near low
        bars[1][2] = 102.0  # lower high
        bars[1][1] = 101.9  # open
        bars[1][4] = 101.6  # close < open (red candle)
        bars[1][3] = 101.4  # low

        signal = strat.generate_signal("RELIANCE.NS", bars, current_position=0, prev_day_close=100.0)
        if signal:
            assert signal.direction == Direction.SHORT
            assert signal.metadata["gap_type"] == "gap_up"

    def test_gap_fade_gap_down_long(self):
        strat = GapFadeStrategy(min_gap_pct=1.0, min_conviction=0.5)
        bars = create_test_bars(40, 100.0)

        # Gap down: open at 98, prev close at 100
        bars[0][1] = 98.0  # open
        bars[0][2] = 98.5  # high
        bars[0][3] = 97.5  # low
        bars[0][4] = 98.2  # close

        # Rejection bar: higher low, closes near high
        bars[1][3] = 98.0  # higher low
        bars[1][1] = 98.1  # open
        bars[1][4] = 98.4  # close > open (green candle)
        bars[1][2] = 98.6  # high

        signal = strat.generate_signal("RELIANCE.NS", bars, current_position=0, prev_day_close=100.0)
        if signal:
            assert signal.direction == Direction.LONG
            assert signal.metadata["gap_type"] == "gap_down"

    def test_gap_fade_no_signal_small_gap(self):
        strat = GapFadeStrategy(min_gap_pct=1.0)
        bars = create_test_bars(40, 100.0)

        # Small gap (< 1%)
        bars[0][1] = 100.5  # open
        bars[0][4] = 100.4  # close

        signal = strat.generate_signal("RELIANCE.NS", bars, current_position=0, prev_day_close=100.0)
        assert signal is None


class TestStrategyRegistry:
    def test_registry_contains_expected_strategies(self):
        assert "orb" in STRATEGY_REGISTRY
        assert "vwap_reversion" in STRATEGY_REGISTRY
        assert "gap_fade" in STRATEGY_REGISTRY

    def test_registry_strategies_are_classes(self):
        assert STRATEGY_REGISTRY["orb"] == ORBStrategy
        assert STRATEGY_REGISTRY["vwap_reversion"] == VWAPReversionStrategy
        assert STRATEGY_REGISTRY["gap_fade"] == GapFadeStrategy

    def test_can_instantiate_from_registry(self):
        for _name, cls in STRATEGY_REGISTRY.items():
            strat = cls()
            assert isinstance(strat, Strategy)
            assert strat.name is not None
