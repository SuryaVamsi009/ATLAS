"""Fill model for backtesting.

Fills orders at the next bar's open plus configurable slippage.
Forces all positions flat before market close (intraday only).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# NSE market hours (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MIN = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MIN = 30


@dataclass
class FillConfig:
    """Configuration for the fill model."""

    slippage_bps: float = 5.0          # slippage in basis points (5 bps = 0.05%)
    force_flat_at_close: bool = True   # force all positions flat before market close
    market_close_hour: int = MARKET_CLOSE_HOUR
    market_close_min: int = MARKET_CLOSE_MIN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slippage_bps": self.slippage_bps,
            "force_flat_at_close": self.force_flat_at_close,
            "market_close_hour": self.market_close_hour,
            "market_close_min": self.market_close_min,
        }


class FillModel:
    """Simulates order fills in an event-driven backtest.

    Orders are filled at the next bar's open price plus slippage:
    - Buy fills at open * (1 + slippage)
    - Sell fills at open * (1 - slippage)

    If force_flat_at_close is enabled, all open positions are closed
    at the last bar of the trading day (market close).
    """

    def __init__(self, config: FillConfig | None = None) -> None:
        self.config = config or FillConfig()

    def apply_slippage(self, price: float, side: str) -> float:
        """Apply slippage to a fill price.

        Args:
            price: Base fill price (next bar open)
            side: "BUY" or "SELL"

        Returns:
            Slipped fill price
        """
        slip = self.config.slippage_bps / 10000.0
        if side.upper() == "BUY":
            return price * (1.0 + slip)
        else:
            return price * (1.0 - slip)

    def fill_order(self, order: Dict[str, Any], next_bar: List[float]) -> Dict[str, Any]:
        """Fill an order at the next bar's open plus slippage.

        Args:
            order: Order dict with keys: symbol, side, qty
            next_bar: Next bar [timestamp_ms, open, high, low, close, volume]

        Returns:
            Fill dict with fill_price, fill_time, slippage_applied
        """
        open_price = next_bar[1]
        side = order["side"]
        fill_price = self.apply_slippage(open_price, side)
        return {
            "symbol": order["symbol"],
            "side": side,
            "qty": order["qty"],
            "fill_price": fill_price,
            "fill_time": next_bar[0],
            "raw_open": open_price,
            "slippage_applied": abs(fill_price - open_price),
        }

    def is_market_close(self, timestamp_ms: int) -> bool:
        """Check if a timestamp is at or after market close (15:30 IST)."""
        dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=IST)
        close_time = dt.replace(
            hour=self.config.market_close_hour,
            minute=self.config.market_close_min,
            second=0,
            microsecond=0,
        )
        return dt >= close_time

    def should_force_flat(self, timestamp_ms: int) -> bool:
        """Check if positions should be force-flattened at this timestamp."""
        return self.config.force_flat_at_close and self.is_market_close(timestamp_ms)

    def get_close_fill(self, position: Dict[str, Any], bar: List[float]) -> Dict[str, Any]:
        """Create a force-close fill at the current bar's close price.

        Args:
            position: Open position dict with symbol, side, qty, entry_price
            bar: Current bar [timestamp_ms, open, high, low, close, volume]

        Returns:
            Fill dict for closing the position
        """
        close_price = bar[4]
        # Closing a long = sell, closing a short = buy
        close_side = "SELL" if position["side"] == "BUY" else "BUY"
        fill_price = self.apply_slippage(close_price, close_side)
        return {
            "symbol": position["symbol"],
            "side": close_side,
            "qty": position["qty"],
            "fill_price": fill_price,
            "fill_time": bar[0],
            "raw_close": close_price,
            "forced": True,
        }
