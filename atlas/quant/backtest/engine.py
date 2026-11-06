"""Event-driven backtest engine for ATLAS.

Replays historical bars through Orchestrator.run_cycle() with an injectable
clock and data feed. Produces a complete trade log and equity curve.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from atlas.quant.backtest.costs import CostModel, IndianCostConfig
from atlas.quant.backtest.fill import FillConfig, FillModel

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


@dataclass
class BacktestConfig:
    """Configuration for the backtest engine."""

    initial_capital: float = 50000.0       # ₹50,000 default
    fill_config: FillConfig = field(default_factory=FillConfig)
    cost_config: IndianCostConfig = field(default_factory=IndianCostConfig)
    symbols: list[str] = field(default_factory=lambda: ["^NSEI"])
    bar_timeframe: str = "5m"
    force_flat_at_close: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_capital": self.initial_capital,
            "fill_config": self.fill_config.to_dict(),
            "cost_config": self.cost_config.to_dict(),
            "symbols": self.symbols,
            "bar_timeframe": self.bar_timeframe,
            "force_flat_at_close": self.force_flat_at_close,
        }


@dataclass
class Trade:
    """A single completed trade (round trip)."""

    symbol: str
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    qty: int
    side: str            # "LONG" or "SHORT"
    pnl: float           # gross PnL in ₹
    cost: float          # total transaction cost in ₹
    net_pnl: float       # pnl - cost
    r_multiple: float    # net_pnl / initial_risk

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "qty": self.qty,
            "side": self.side,
            "pnl": self.pnl,
            "cost": self.cost,
            "net_pnl": self.net_pnl,
            "r_multiple": self.r_multiple,
        }


@dataclass
class BacktestResult:
    """Result of a backtest run."""

    config: BacktestConfig
    trades: list[Trade]
    equity_curve: list[dict[str, Any]]   # [{timestamp, equity, cash, positions_value}]
    fills: list[dict[str, Any]]          # all fills (entries + exits)
    total_pnl: float
    total_costs: float
    net_pnl: float
    n_trades: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "trades": [t.to_dict() for t in self.trades],
            "equity_curve": self.equity_curve,
            "fills": self.fills,
            "total_pnl": self.total_pnl,
            "total_costs": self.total_costs,
            "net_pnl": self.net_pnl,
            "n_trades": self.n_trades,
        }


class BacktestEngine:
    """Event-driven backtest engine.

    Replays bars through a strategy callback (or Orchestrator.run_cycle)
    with realistic fills and costs.

    Usage:
        engine = BacktestEngine(BacktestConfig(initial_capital=50000))
        result = engine.run(bars, strategy_fn)
    """

    def __init__(
        self,
        config: BacktestConfig | None = None,
        cost_model: CostModel | None = None,
        fill_model: FillModel | None = None,
    ) -> None:
        self.config = config or BacktestConfig()
        self.cost_model = cost_model or CostModel(self.config.cost_config)
        self.fill_model = fill_model or FillModel(self.config.fill_config)
        self.cash: float = self.config.initial_capital
        self.positions: dict[str, dict[str, Any]] = {}  # symbol -> position
        self.trades: list[Trade] = []
        self.fills: list[dict[str, Any]] = []
        self.equity_curve: list[dict[str, Any]] = []
        self.pending_orders: list[dict[str, Any]] = []

    def run(
        self,
        bars: list[list[float]],
        strategy_fn: Callable[[list[list[float]], int, dict[str, Any]], dict[str, Any | None]],
        warmup: int = 50,
    ) -> BacktestResult:
        """Run the backtest over a series of bars.

        Args:
            bars: List of [timestamp_ms, open, high, low, close, volume]
            strategy_fn: Callback(bar_history, current_index, context) -> order dict or None
                         Order dict: {"symbol": str, "side": "BUY"/"SELL", "qty": int,
                                      "stop_price": float (optional)}
            warmup: Number of initial bars to use as warmup (no trading)

        Returns:
            BacktestResult with trades, equity curve, and fills
        """
        self._reset()

        for i in range(len(bars)):
            bar = bars[i]
            ts = bar[0]

            # 1. Fill pending orders at this bar's open
            self._fill_pending_orders(bar)

            # 2. Force flat at market close
            if self.fill_model.should_force_flat(ts):
                self._force_flat_all(bars[i])

            # 3. Run strategy (skip warmup period)
            if i >= warmup:
                history = bars[: i + 1]
                context = {
                    "cash": self.cash,
                    "positions": dict(self.positions),
                    "equity": self._compute_equity(bar),
                    "bar_index": i,
                }
                order = strategy_fn(history, i, context)
                if order is not None:
                    self._submit_order(order, bar)

            # 4. Record equity curve
            equity = self._compute_equity(bar)
            positions_value = sum(
                p["qty"] * bar[4] for p in self.positions.values()
            )
            self.equity_curve.append({
                "timestamp": ts,
                "equity": equity,
                "cash": self.cash,
                "positions_value": positions_value,
            })

        # Force flat at the very end if any positions remain
        if self.positions and bars:
            self._force_flat_all(bars[-1])

        total_pnl = sum(t.pnl for t in self.trades)
        total_costs = sum(t.cost for t in self.trades)
        net_pnl = total_pnl - total_costs

        return BacktestResult(
            config=self.config,
            trades=self.trades,
            equity_curve=self.equity_curve,
            fills=self.fills,
            total_pnl=total_pnl,
            total_costs=total_costs,
            net_pnl=net_pnl,
            n_trades=len(self.trades),
        )

    def _reset(self) -> None:
        self.cash = self.config.initial_capital
        self.positions = {}
        self.trades = []
        self.fills = []
        self.equity_curve = []
        self.pending_orders = []

    def _fill_pending_orders(self, bar: list[float]) -> None:
        """Fill all pending orders at this bar's open + slippage."""
        if not self.pending_orders:
            return
        fills = []
        for order in self.pending_orders:
            fill = self.fill_model.fill_order(order, bar)
            fills.append(fill)
            self._execute_fill(fill)
        self.fills.extend(fills)
        self.pending_orders = []

    def _submit_order(self, order: dict[str, Any], current_bar: list[float]) -> None:
        """Submit an order - it will be filled at the NEXT bar's open."""
        order.setdefault("symbol", self.config.symbols[0] if self.config.symbols else "UNKNOWN")
        self.pending_orders.append(order)

    def _execute_fill(self, fill: dict[str, Any]) -> None:
        """Execute a fill and update cash/positions."""
        symbol = fill["symbol"]
        side = fill["side"].upper()
        qty = fill["qty"]
        price = fill["fill_price"]

        if side == "BUY":
            cost = self.cost_model.compute_buy_cost(price, qty)
            total = price * qty + cost
            if total > self.cash:
                logger.warning(f"Insufficient cash for {qty} {symbol} @ {price:.2f}, skipping")
                return
            self.cash -= total
            if symbol in self.positions:
                # Adding to existing long
                pos = self.positions[symbol]
                new_qty = pos["qty"] + qty
                pos["entry_price"] = (pos["entry_price"] * pos["qty"] + price * qty) / new_qty
                pos["qty"] = new_qty
                pos["entry_cost"] += cost
            else:
                self.positions[symbol] = {
                    "symbol": symbol,
                    "side": "BUY",
                    "qty": qty,
                    "entry_price": price,
                    "entry_time": fill["fill_time"],
                    "entry_cost": cost,
                    "stop_price": fill.get("stop_price"),
                }
        else:  # SELL
            cost = self.cost_model.compute_sell_cost(price, qty)
            proceeds = price * qty - cost
            self.cash += proceeds
            if symbol in self.positions:
                pos = self.positions[symbol]
                entry_price = pos["entry_price"]
                entry_cost = pos.get("entry_cost", 0.0)
                pnl = (price - entry_price) * qty
                total_cost = entry_cost + cost
                # R multiple: risk = (entry - stop) * qty, or use 1% of equity as default
                stop = pos.get("stop_price")
                if stop is None:
                    stop = entry_price * 0.99
                risk_per_unit = abs(entry_price - stop)
                if risk_per_unit <= 0:
                    risk_per_unit = entry_price * 0.01
                r_multiple = (pnl - total_cost) / (risk_per_unit * qty) if risk_per_unit * qty > 0 else 0.0
                self.trades.append(Trade(
                    symbol=symbol,
                    entry_time=pos["entry_time"],
                    exit_time=fill["fill_time"],
                    entry_price=entry_price,
                    exit_price=price,
                    qty=qty,
                    side="LONG",
                    pnl=pnl,
                    cost=total_cost,
                    net_pnl=pnl - total_cost,
                    r_multiple=r_multiple,
                ))
                del self.positions[symbol]
            else:
                # Short selling - open short position
                self.positions[symbol] = {
                    "symbol": symbol,
                    "side": "SELL",
                    "qty": qty,
                    "entry_price": price,
                    "entry_time": fill["fill_time"],
                    "entry_cost": cost,
                    "stop_price": fill.get("stop_price"),
                }

    def _force_flat_all(self, bar: list[float]) -> None:
        """Force close all open positions at the current bar's close."""
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            fill = self.fill_model.get_close_fill(pos, bar)
            self._execute_fill(fill)
            self.fills.append(fill)

    def _compute_equity(self, bar: list[float]) -> float:
        """Compute total equity (cash + positions value at current close)."""
        positions_value = sum(
            p["qty"] * bar[4] for p in self.positions.values()
        )
        return float(self.cash + positions_value)
