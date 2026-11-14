"""Strategy framework and implementations for ATLAS quant layer.

Each strategy emits Signal(symbol, direction, conviction, horizon, stop_distance).
The orchestrator converts a Signal into a DecisionProposal, and RiskVerdict still gates it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

from atlas.quant.features import (
    atr,
    opening_range,
    rsi,
    vwap,
)

# ---------------------------------------------------------------------------
# Signal and Direction Types
# ---------------------------------------------------------------------------


class Direction(Enum):
    """Trade direction."""

    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class Horizon(Enum):
    """Trade horizon."""

    INTRADAY = "intraday"
    SWING = "swing"


@dataclass
class Signal:
    """Trading signal emitted by a strategy.

    Attributes:
        symbol: Trading symbol
        direction: LONG, SHORT, or FLAT
        conviction: Confidence level 0.0-1.0
        horizon: INTRADAY or SWING
        stop_distance: Distance from entry to stop (in price units)
        entry_price: Suggested entry price (optional, uses current if None)
        target_price: Suggested target price (optional)
        metadata: Additional strategy-specific data
    """

    symbol: str
    direction: Direction
    conviction: float
    horizon: Horizon
    stop_distance: float
    entry_price: float | None = None
    target_price: float | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        """Validate signal parameters."""
        if not 0.0 <= self.conviction <= 1.0:
            raise ValueError(f"Conviction must be in [0, 1], got {self.conviction}")
        if self.stop_distance <= 0:
            raise ValueError(f"Stop distance must be positive, got {self.stop_distance}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "conviction": self.conviction,
            "horizon": self.horizon.value,
            "stop_distance": self.stop_distance,
            "entry_price": self.entry_price,
            "target_price": self.target_price,
            "metadata": self.metadata or {},
        }


# ---------------------------------------------------------------------------
# Base Strategy Class
# ---------------------------------------------------------------------------


class Strategy(ABC):
    """Abstract base class for all strategies.

    Each strategy implements generate_signal() which analyzes bars and
    returns a Signal or None if no trade setup is found.
    """

    def __init__(
        self,
        name: str,
        min_conviction: float = 0.55,
        max_positions: int = 1,
    ):
        """Initialize strategy.

        Args:
            name: Strategy name
            min_conviction: Minimum conviction to emit signal
            max_positions: Maximum concurrent positions
        """
        self.name = name
        self.min_conviction = min_conviction
        self.max_positions = max_positions
        self.active_signals: dict[str, Signal] = {}

    @abstractmethod
    def generate_signal(
        self,
        symbol: str,
        bars: list[list[float]],
        current_position: int = 0,
    ) -> Signal | None:
        """Generate a trading signal for the given symbol and bars.

        Args:
            symbol: Trading symbol
            bars: OHLCV bars (most recent last)
            current_position: Current position (0=flat, >0=long, <0=short)

        Returns:
            Signal if setup found, None otherwise
        """
        pass

    def should_exit(
        self,
        symbol: str,
        bars: list[list[float]],
        current_position: int,
    ) -> bool:
        """Determine if current position should be exited.

        Default: exit on opposite signal or end of session.
        Override for strategy-specific exit logic.
        """
        if current_position == 0:
            return False

        signal = self.generate_signal(symbol, bars, current_position)
        if signal is None:
            return False

        # Exit if signal direction opposes current position
        if current_position > 0 and signal.direction == Direction.SHORT:
            return True
        if current_position < 0 and signal.direction == Direction.LONG:
            return True

        return False


# ---------------------------------------------------------------------------
# Opening Range Breakout (ORB) Strategy
# ---------------------------------------------------------------------------


class ORBStrategy(Strategy):
    """Opening Range Breakout strategy.

    Hypothesis: The first 15 minutes of trading establish a range.
    A breakout above the range high with volume confirms bullish momentum.
    A breakdown below the range low with volume confirms bearish momentum.

    Entry: Break of opening range high (long) or low (short)
    Stop: Other side of opening range
    Target: 2x risk (R:R = 2:1)
    Horizon: Intraday (force flat before close)
    """

    def __init__(
        self,
        range_minutes: int = 15,
        min_volume_ratio: float = 1.2,
        risk_reward: float = 2.0,
        min_conviction: float = 0.6,
    ):
        super().__init__("ORB", min_conviction=min_conviction)
        self.range_minutes = range_minutes
        self.min_volume_ratio = min_volume_ratio
        self.risk_reward = risk_reward

    def generate_signal(
        self,
        symbol: str,
        bars: list[list[float]],
        current_position: int = 0,
    ) -> Signal | None:
        if len(bars) < self.range_minutes + 5:
            return None

        # Calculate opening range
        or_high, or_low, start_idx, end_idx = opening_range(bars, self.range_minutes, "09:15")

        if np.isnan(or_high) or np.isnan(or_low):
            return None

        # Check for breakout after opening range
        current_bar = bars[-1]
        current_high = current_bar[2]
        current_low = current_bar[3]
        current_close = current_bar[4]
        current_volume = current_bar[5]

        # Calculate average volume for comparison
        avg_volume = np.mean([bar[5] for bar in bars[-20:-1]]) if len(bars) > 20 else current_volume
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        # Long breakout: price breaks above OR high with volume
        if (
            current_position <= 0
            and current_high > or_high
            and volume_ratio >= self.min_volume_ratio
        ):
            entry_price = current_close
            stop_distance = entry_price - or_low
            target_price = entry_price + (stop_distance * self.risk_reward)

            # Conviction based on volume and breakout strength
            breakout_strength = (current_high - or_high) / or_high
            volume_score = min(volume_ratio / 2.0, 1.0)
            conviction = float(min(0.5 + 0.3 * breakout_strength * 100 + 0.2 * volume_score, 0.95))

            if conviction >= self.min_conviction:
                return Signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    conviction=conviction,
                    horizon=Horizon.INTRADAY,
                    stop_distance=stop_distance,
                    entry_price=entry_price,
                    target_price=target_price,
                    metadata={
                        "strategy": "ORB",
                        "or_high": or_high,
                        "or_low": or_low,
                        "volume_ratio": volume_ratio,
                        "breakout_strength": breakout_strength,
                    },
                )

        # Short breakdown: price breaks below OR low with volume
        if current_position >= 0 and current_low < or_low and volume_ratio >= self.min_volume_ratio:
            entry_price = current_close
            stop_distance = or_high - entry_price
            target_price = entry_price - (stop_distance * self.risk_reward)

            breakdown_strength = (or_low - current_low) / or_low
            volume_score = min(volume_ratio / 2.0, 1.0)
            conviction = float(min(0.5 + 0.3 * breakdown_strength * 100 + 0.2 * volume_score, 0.95))

            if conviction >= self.min_conviction:
                return Signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    conviction=conviction,
                    horizon=Horizon.INTRADAY,
                    stop_distance=stop_distance,
                    entry_price=entry_price,
                    target_price=target_price,
                    metadata={
                        "strategy": "ORB",
                        "or_high": or_high,
                        "or_low": or_low,
                        "volume_ratio": volume_ratio,
                        "breakdown_strength": breakdown_strength,
                    },
                )

        return None

    def should_exit(
        self,
        symbol: str,
        bars: list[list[float]],
        current_position: int,
    ) -> bool:
        # Force flat before market close (15:15 IST)
        if len(bars) > 0:
            last_bar = bars[-1]
            ts_ms = last_bar[0]
            import pandas as pd

            dt = pd.Timestamp(ts_ms, unit="ms", tz="UTC").tz_convert("Asia/Kolkata")
            if dt.hour >= 15 and dt.minute >= 15:
                return True

        return super().should_exit(symbol, bars, current_position)


# ---------------------------------------------------------------------------
# VWAP Reversion Strategy
# ---------------------------------------------------------------------------


class VWAPReversionStrategy(Strategy):
    """VWAP Mean Reversion strategy.

    Hypothesis: Price tends to revert to VWAP during choppy/range-bound sessions.
    Long when price is significantly below VWAP with oversold RSI.
    Short when price is significantly above VWAP with overbought RSI.

    Entry: Price > 1.5*ATR below VWAP (long) or above VWAP (short)
    Stop: 1.5*ATR beyond entry
    Target: VWAP (mean reversion)
    Horizon: Intraday
    """

    def __init__(
        self,
        atr_period: int = 14,
        atr_multiplier: float = 1.5,
        rsi_period: int = 14,
        rsi_oversold: float = 35,
        rsi_overbought: float = 65,
        min_conviction: float = 0.55,
    ):
        super().__init__("VWAP_REVERSION", min_conviction=min_conviction)
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

    def generate_signal(
        self,
        symbol: str,
        bars: list[list[float]],
        current_position: int = 0,
    ) -> Signal | None:
        if len(bars) < max(self.atr_period, self.rsi_period) + 10:
            return None

        # Calculate indicators
        atr_values = atr(bars, self.atr_period)
        vwap_values = vwap(bars)
        rsi_values = rsi(bars, self.rsi_period)

        current_atr = atr_values[-1]
        current_vwap = vwap_values[-1]
        current_rsi = rsi_values[-1]
        current_close = bars[-1][4]

        if np.isnan(current_atr) or np.isnan(current_vwap) or np.isnan(current_rsi):
            return None

        # Distance from VWAP in ATR units
        dist_from_vwap = (current_close - current_vwap) / current_atr

        # Long: price significantly below VWAP and RSI oversold
        if (
            current_position <= 0
            and dist_from_vwap < -self.atr_multiplier
            and current_rsi < self.rsi_oversold
        ):
            entry_price = current_close
            stop_distance = self.atr_multiplier * current_atr
            target_price = current_vwap  # Target VWAP

            # Conviction based on distance and RSI
            dist_score = min(abs(dist_from_vwap) / 3.0, 1.0)
            rsi_score = (self.rsi_oversold - current_rsi) / self.rsi_oversold
            conviction = min(0.45 + 0.3 * dist_score + 0.25 * rsi_score, 0.9)

            if conviction >= self.min_conviction:
                return Signal(
                    symbol=symbol,
                    direction=Direction.LONG,
                    conviction=conviction,
                    horizon=Horizon.INTRADAY,
                    stop_distance=stop_distance,
                    entry_price=entry_price,
                    target_price=target_price,
                    metadata={
                        "strategy": "VWAP_REVERSION",
                        "vwap": current_vwap,
                        "atr": current_atr,
                        "rsi": current_rsi,
                        "dist_from_vwap_atr": dist_from_vwap,
                    },
                )

        # Short: price significantly above VWAP and RSI overbought
        if (
            current_position >= 0
            and dist_from_vwap > self.atr_multiplier
            and current_rsi > self.rsi_overbought
        ):
            entry_price = current_close
            stop_distance = self.atr_multiplier * current_atr
            target_price = current_vwap  # Target VWAP

            dist_score = min(dist_from_vwap / 3.0, 1.0)
            rsi_score = (current_rsi - self.rsi_overbought) / (100 - self.rsi_overbought)
            conviction = min(0.45 + 0.3 * dist_score + 0.25 * rsi_score, 0.9)

            if conviction >= self.min_conviction:
                return Signal(
                    symbol=symbol,
                    direction=Direction.SHORT,
                    conviction=conviction,
                    horizon=Horizon.INTRADAY,
                    stop_distance=stop_distance,
                    entry_price=entry_price,
                    target_price=target_price,
                    metadata={
                        "strategy": "VWAP_REVERSION",
                        "vwap": current_vwap,
                        "atr": current_atr,
                        "rsi": current_rsi,
                        "dist_from_vwap_atr": dist_from_vwap,
                    },
                )

        return None

    def should_exit(
        self,
        symbol: str,
        bars: list[list[float]],
        current_position: int,
    ) -> bool:
        # Exit when price reaches VWAP (mean reversion target)
        if len(bars) < 20:
            return False

        vwap_values = vwap(bars)
        current_vwap = vwap_values[-1]
        current_close = bars[-1][4]

        if np.isnan(current_vwap):
            return False

        if current_position > 0 and current_close >= current_vwap:
            return True
        if current_position < 0 and current_close <= current_vwap:
            return True

        # Force flat before close
        if len(bars) > 0:
            last_bar = bars[-1]
            ts_ms = last_bar[0]
            import pandas as pd

            dt = pd.Timestamp(ts_ms, unit="ms", tz="UTC").tz_convert("Asia/Kolkata")
            if dt.hour >= 15 and dt.minute >= 15:
                return True

        return super().should_exit(symbol, bars, current_position)


# ---------------------------------------------------------------------------
# Gap Fade Strategy
# ---------------------------------------------------------------------------


class GapFadeStrategy(Strategy):
    """Gap Fade strategy.

    Hypothesis: Overnight gaps often fill during the first hour of trading.
    Fade gap up: short when price gaps up and shows rejection at open.
    Fade gap down: long when price gaps down and shows support at open.

    Entry: Gap > 1% with reversal candle in first 30 minutes
    Stop: Gap extreme (high of gap up bar / low of gap down bar)
    Target: Previous day's close (gap fill)
    Horizon: Intraday
    """

    def __init__(
        self,
        min_gap_pct: float = 1.0,
        lookback_bars: int = 30,
        min_conviction: float = 0.55,
    ):
        super().__init__("GAP_FADE", min_conviction=min_conviction)
        self.min_gap_pct = min_gap_pct
        self.lookback_bars = lookback_bars

    def generate_signal(
        self,
        symbol: str,
        bars: list[list[float]],
        current_position: int = 0,
        prev_day_close: float | None = None,
    ) -> Signal | None:
        if len(bars) < self.lookback_bars:
            return None

        # Calculate gap from previous day close
        if prev_day_close is None:
            # Use first bar's close as proxy if not provided
            prev_day_close = bars[0][4]

        current_open = bars[0][1]
        gap_pct = ((current_open - prev_day_close) / prev_day_close) * 100.0

        if abs(gap_pct) < self.min_gap_pct:
            return None

        # Check for reversal in first N bars
        first_bar_high = bars[0][2]
        first_bar_low = bars[0][3]

        # Look for rejection/reversal in early bars
        for i in range(1, min(self.lookback_bars, len(bars))):
            bar_high = bars[i][2]
            bar_low = bars[i][3]
            bar_close = bars[i][4]
            bar_open = bars[i][1]

            # Gap up fade: price gaps up but shows selling pressure
            if gap_pct > self.min_gap_pct and current_position <= 0:
                # Rejection: bar makes lower high and closes near low
                if bar_high < first_bar_high and bar_close < bar_open:
                    entry_price = bar_close
                    stop_distance = first_bar_high - entry_price
                    target_price = prev_day_close  # Gap fill target

                    # Conviction based on gap size and rejection strength
                    gap_score = min(gap_pct / 3.0, 1.0)
                    rejection_strength = (
                        (bar_open - bar_close) / (bar_high - bar_low) if bar_high != bar_low else 0
                    )
                    conviction = min(0.4 + 0.3 * gap_score + 0.3 * rejection_strength, 0.85)

                    if conviction >= self.min_conviction and stop_distance > 0:
                        return Signal(
                            symbol=symbol,
                            direction=Direction.SHORT,
                            conviction=conviction,
                            horizon=Horizon.INTRADAY,
                            stop_distance=stop_distance,
                            entry_price=entry_price,
                            target_price=target_price,
                            metadata={
                                "strategy": "GAP_FADE",
                                "gap_pct": gap_pct,
                                "gap_type": "gap_up",
                                "prev_close": prev_day_close,
                                "rejection_bar": i,
                            },
                        )

            # Gap down fade: price gaps down but shows buying pressure
            if gap_pct < -self.min_gap_pct and current_position >= 0:
                # Rejection: bar makes higher low and closes near high
                if bar_low > first_bar_low and bar_close > bar_open:
                    entry_price = bar_close
                    stop_distance = entry_price - first_bar_low
                    target_price = prev_day_close  # Gap fill target

                    gap_score = min(abs(gap_pct) / 3.0, 1.0)
                    rejection_strength = (
                        (bar_close - bar_open) / (bar_high - bar_low) if bar_high != bar_low else 0
                    )
                    conviction = min(0.4 + 0.3 * gap_score + 0.3 * rejection_strength, 0.85)

                    if conviction >= self.min_conviction and stop_distance > 0:
                        return Signal(
                            symbol=symbol,
                            direction=Direction.LONG,
                            conviction=conviction,
                            horizon=Horizon.INTRADAY,
                            stop_distance=stop_distance,
                            entry_price=entry_price,
                            target_price=target_price,
                            metadata={
                                "strategy": "GAP_FADE",
                                "gap_pct": gap_pct,
                                "gap_type": "gap_down",
                                "prev_close": prev_day_close,
                                "rejection_bar": i,
                            },
                        )

        return None

    def should_exit(
        self,
        symbol: str,
        bars: list[list[float]],
        current_position: int,
    ) -> bool:
        # Exit on gap fill (price reaches previous close)
        if len(bars) < 2:
            return False

        # We need prev_day_close - would need to pass it or store it
        # For now, use force flat before close
        if len(bars) > 0:
            last_bar = bars[-1]
            ts_ms = last_bar[0]
            import pandas as pd

            dt = pd.Timestamp(ts_ms, unit="ms", tz="UTC").tz_convert("Asia/Kolkata")
            if dt.hour >= 15 and dt.minute >= 15:
                return True

        return super().should_exit(symbol, bars, current_position)


# ---------------------------------------------------------------------------
# Strategy Registry
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, type[Strategy]] = {
    "orb": ORBStrategy,
    "vwap_reversion": VWAPReversionStrategy,
    "gap_fade": GapFadeStrategy,
}


def get_strategy(name: str, **kwargs) -> Strategy:
    """Get strategy instance by name.

    Args:
        name: Strategy name ("orb", "vwap_reversion", "gap_fade")
        **kwargs: Strategy parameters

    Returns:
        Strategy instance
    """
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGY_REGISTRY.keys())}")

    return STRATEGY_REGISTRY[name](**kwargs)


def list_strategies() -> list[str]:
    """List available strategy names."""
    return list(STRATEGY_REGISTRY.keys())


# Type hint for bars
