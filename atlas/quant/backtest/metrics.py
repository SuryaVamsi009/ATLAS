"""Backtest metrics for ATLAS.

Reports: net PnL after costs, max drawdown, hit rate, average R, trade count,
turnover, and cost drag. Capital is a parameter (run at ₹2,000 and ₹50,000).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from atlas.quant.backtest.engine import BacktestResult


@dataclass
class MetricsConfig:
    """Configuration for metrics computation."""

    risk_free_rate_annual: float = 0.06   # 6% annual risk-free (India)
    bars_per_year: int = 252 * 78         # ~78 5-min bars per trading day

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_free_rate_annual": self.risk_free_rate_annual,
            "bars_per_year": self.bars_per_year,
        }


def compute_backtest_metrics(
    result: BacktestResult,
    config: MetricsConfig | None = None,
) -> dict[str, Any]:
    """Compute comprehensive backtest metrics.

    Args:
        result: BacktestResult from BacktestEngine.run()
        config: MetricsConfig (optional)

    Returns:
        Dict with net_pnl, net_pnl_pct, max_drawdown, max_drawdown_pct,
        hit_rate, avg_r, sharpe, trade_count, turnover, cost_drag, etc.
    """
    cfg = config or MetricsConfig()
    initial_capital = result.config.initial_capital

    # Equity curve
    equity = np.array([e["equity"] for e in result.equity_curve], dtype=np.float64)
    timestamps = [e["timestamp"] for e in result.equity_curve]

    # Net PnL
    net_pnl = result.net_pnl
    net_pnl_pct = (net_pnl / initial_capital) if initial_capital > 0 else 0.0

    # Drawdown
    if len(equity) > 0:
        running_max = np.maximum.accumulate(equity)
        drawdowns = (equity - running_max) / running_max
        max_drawdown_pct = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0
        max_drawdown = float(np.min(equity - running_max)) if len(equity) > 0 else 0.0
    else:
        max_drawdown_pct = 0.0
        max_drawdown = 0.0

    # Trade stats
    trades = result.trades
    n_trades = len(trades)
    winning_trades = [t for t in trades if t.net_pnl > 0]
    losing_trades = [t for t in trades if t.net_pnl <= 0]
    hit_rate = len(winning_trades) / n_trades if n_trades > 0 else 0.0
    avg_r = float(np.mean([t.r_multiple for t in trades])) if n_trades > 0 else 0.0
    avg_win = float(np.mean([t.net_pnl for t in winning_trades])) if winning_trades else 0.0
    avg_loss = float(np.mean([t.net_pnl for t in losing_trades])) if losing_trades else 0.0
    profit_factor = (
        abs(sum(t.net_pnl for t in winning_trades) / sum(t.net_pnl for t in losing_trades))
        if losing_trades and sum(t.net_pnl for t in losing_trades) != 0 else float("inf")
    )

    # Turnover: sum of (price * qty) for all fills
    turnover = sum(f["fill_price"] * f["qty"] for f in result.fills)
    turnover_pct = turnover / initial_capital if initial_capital > 0 else 0.0

    # Cost drag: total costs as % of initial capital and as % of turnover
    total_costs = result.total_costs
    cost_drag_pct_capital = total_costs / initial_capital if initial_capital > 0 else 0.0
    cost_drag_pct_turnover = total_costs / turnover if turnover > 0 else 0.0

    # Sharpe ratio (annualized)
    if len(equity) > 1:
        returns = np.diff(equity) / equity[:-1]
        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns))
        if std_ret > 0:
            sharpe = (mean_ret - cfg.risk_free_rate_annual / cfg.bars_per_year) / std_ret * math.sqrt(cfg.bars_per_year)
        else:
            sharpe = 0.0
    else:
        sharpe = 0.0

    # Duration
    if timestamps:
        duration_days = (timestamps[-1] - timestamps[0]) / (1000.0 * 86400.0)
    else:
        duration_days = 0.0

    return {
        "initial_capital": initial_capital,
        "final_equity": float(equity[-1]) if len(equity) > 0 else initial_capital,
        "net_pnl": net_pnl,
        "net_pnl_pct": net_pnl_pct,
        "gross_pnl": result.total_pnl,
        "total_costs": total_costs,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
        "hit_rate": hit_rate,
        "avg_r_multiple": avg_r,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "trade_count": n_trades,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "turnover": turnover,
        "turnover_pct_capital": turnover_pct,
        "cost_drag_pct_capital": cost_drag_pct_capital,
        "cost_drag_pct_turnover": cost_drag_pct_turnover,
        "sharpe": sharpe,
        "duration_days": duration_days,
        "n_bars": len(equity),
    }


def run_at_capital_levels(
    bars: list[list[float]],
    strategy_fn,
    capitals: list[float] | None = None,
    warmup: int = 50,
) -> dict[float, dict[str, Any]]:
    """Run the same strategy at multiple capital levels (e.g., ₹2,000 and ₹50,000).

    Args:
        bars: Historical bars
        strategy_fn: Strategy callback
        capitals: List of capital levels (default [2000, 50000])
        warmup: Warmup bars

    Returns:
        Dict mapping capital -> metrics dict
    """
    from atlas.quant.backtest.engine import BacktestConfig, BacktestEngine

    if capitals is None:
        capitals = [2000.0, 50000.0]

    results = {}
    for cap in capitals:
        cfg = BacktestConfig(initial_capital=cap)
        engine = BacktestEngine(cfg)
        result = engine.run(bars, strategy_fn, warmup=warmup)
        results[cap] = compute_backtest_metrics(result)
    return results
