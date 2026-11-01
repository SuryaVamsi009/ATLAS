"""StateSnapshot module for the ATLAS architecture.

This module defines the StateSnapshot frozen dataclass that represents
the only thing the model ever sees, as described in the ATLAS architecture
document. All values are computed in Python - the model receives values,
never supplies them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class StateSnapshot:
    """Immutable snapshot of market state that the model receives.

    This is the only thing the model ever sees - all values are computed
    in Python from raw market data, never supplied by the model.
    """

    snapshot_id: str
    timestamp: datetime
    symbol: str
    timeframe: str
    ohlcv_tail: list[float]
    indicators: dict[str, float]
    regime_features: dict[str, float]
    position: dict[str, Any]
    account: dict[str, Any]


def compute_from_bars(symbol: str, timeframe: str, bars: list[list[float]]) -> StateSnapshot:
    """Compute a StateSnapshot from raw market bars.

    Args:
        symbol: Trading symbol (e.g. "BTC-USD")
        timeframe: Bar timeframe (e.g. "1h", "1d")
        bars: Raw market bars [timestamp, open, high, low, close, volume]

    Returns:
        A StateSnapshot instance with all fields computed from the bars.

    Raises:
        ValueError: If ohlcv_tail has fewer than 2 bars or required
            indicators are missing.
    """
    if len(bars) < 2:
        msg = "ohlcv_tail must have at least 2 bars"
        raise ValueError(msg)

    # Extract last N bars as plain floats (ohlcv_tail)
    # Each bar: [timestamp, open, high, low, close, volume]
    ohlcv_tail = [float(bar[1]) for bar in bars[-2:]]  # last 2 close prices as example

    # Compute indicators from bars
    # Example: RSI, ATR, EMA fast/slow, etc.
    closes = [float(bar[4]) for bar in bars]
    if len(closes) < 2:
        msg = "Need at least 2 closes to compute indicators"
        raise ValueError(msg)

    # Simple example indicators - in practice these would use proper formulas
    last_close = closes[-1]
    prev_close = closes[-2]

    # Price change ratio as a simple indicator
    price_change = (last_close - prev_close) / prev_close if prev_close != 0 else 0.0

    # EMA fast (short period) and EMA slow (long period) - simplified
    # In production, use proper EMA calculation
    ema_fast = last_close  # placeholder
    ema_slow = last_close  # placeholder

    # Realised volatility (simplified std dev of returns)
    if len(closes) >= 3:
        returns = [(closes[i] / closes[i - 1]) - 1 for i in range(1, len(closes))]
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        realised_vol = variance ** 0.5
    else:
        realised_vol = 0.0

    # ATR (Average True Range) - simplified
    highs = [float(bar[2]) for bar in bars]
    lows = [float(bar[3]) for bar in bars]
    if len(highs) >= 2:
        tr_values = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - highs[i - 1]),
                abs(lows[i] - lows[i - 1]),
            )
            tr_values.append(tr)
        atr = sum(tr_values) / len(tr_values) if tr_values else 0.0
    else:
        atr = 0.0

    # RSI (Relative Strength Index) - simplified 14-period
    if len(closes) >= 15:
        gains = []
        losses = []
        for i in range(1, min(15, len(closes))):
            diff = closes[i] - closes[i - 1]
            if diff > 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(-diff)
        avg_gain = sum(gains) / len(gains) if gains else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        rs = avg_gain / avg_loss if avg_loss != 0 else 0.0
        rsi = 100.0 - (100.0 / (1.0 + rs))
    else:
        rsi = 50.0  # neutral

    # Regime features
    regime_features = {
        "realised_vol": realised_vol,
        "trend_slope": price_change,
        "spread": 0.0,  # placeholder - would need bid/ask data
    }

    # Position state
    position = {
        "qty": 0.0,
        "avg_price": last_close,
        "unrealised_pnl": 0.0,
        "stop": 0.0,
    }

    # Account state
    account = {
        "equity": 10000.0,  # placeholder starting equity
        "buying_power": 10000.0,
        "daily_pnl": 0.0,
    }

    # Build indicators dict with required keys
    indicators = {
        "rsi": rsi,
        "atr": atr,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "price_change": price_change,
    }

    # Validate required indicator keys
    required_keys = {"rsi", "atr", "ema_fast", "ema_slow"}
    missing = required_keys - set(indicators.keys())
    if missing:
        msg = f"Indicators missing required keys: {missing}"
        raise ValueError(msg)

    # Build and return the snapshot
    snapshot_id = f"{symbol}_{timeframe}_{int(datetime.utcnow().timestamp())}"

    return StateSnapshot(
        snapshot_id=snapshot_id,
        timestamp=datetime.utcnow(),
        symbol=symbol,
        timeframe=timeframe,
        ohlcv_tail=ohlcv_tail,
        indicators=indicators,
        regime_features=regime_features,
        position=position,
        account=account,
    )


# Example usage (can be removed or kept for testing)
if __name__ == "__main__":
    # Sample bars: [timestamp, open, high, low, close, volume]
    sample_bars = [
        [1730428800000, 35000.0, 35200.0, 34900.0, 35100.0, 1500.0],
        [1730515200000, 35100.0, 35300.0, 35050.0, 35250.0, 1800.0],
        [1730601600000, 35250.0, 35400.0, 35200.0, 35350.0, 2000.0],
    ]

    snapshot = compute_from_bars("BTC-USD", "1h", sample_bars)
    print(f"Snapshot ID: {snapshot.snapshot_id}")
    print(f"Symbol: {snapshot.symbol}")
    print(f"Timeframe: {snapshot.timeframe}")
    print(f"OHLCV tail: {snapshot.ohlcv_tail}")
    print(f"Indicators: {snapshot.indicators}")
    print(f"Regime features: {snapshot.regime_features}")
    print(f"Position: {snapshot.position}")
    print(f"Account: {snapshot.account}")