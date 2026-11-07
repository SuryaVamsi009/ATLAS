"""Backtest package for ATLAS quant layer.

Event-driven backtesting engine that replays bars through the ATLAS pipeline,
with fill model, Indian cost stack, baselines, metrics, and validation harness.

Modules:
- engine: Event-driven engine replaying bars through Orchestrator.run_cycle()
- fill: Fill model (next bar open + slippage, force flat at close)
- costs: Indian cost stack (brokerage, STT, exchange, SEBI, stamp duty, GST)
- baselines: Buy-and-hold and random-entry baselines
- metrics: Net PnL, drawdown, hit rate, avg R, turnover, cost drag
- validation: Purged walk-forward splits, hold-out, trial log
- overfitting: Deflated Sharpe, 2x costs, parameter plateau checks
"""

from __future__ import annotations

from atlas.quant.backtest.baselines import BuyAndHoldBaseline, RandomEntryBaseline
from atlas.quant.backtest.costs import CostModel, IndianCostConfig
from atlas.quant.backtest.engine import BacktestConfig, BacktestEngine, BacktestResult
from atlas.quant.backtest.fill import FillConfig, FillModel
from atlas.quant.backtest.metrics import MetricsConfig, compute_backtest_metrics
from atlas.quant.backtest.overfitting import OverfittingChecker, OverfittingConfig
from atlas.quant.backtest.validation import ValidationConfig, WalkForwardValidator

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "FillModel",
    "FillConfig",
    "CostModel",
    "IndianCostConfig",
    "BuyAndHoldBaseline",
    "RandomEntryBaseline",
    "compute_backtest_metrics",
    "MetricsConfig",
    "WalkForwardValidator",
    "ValidationConfig",
    "OverfittingChecker",
    "OverfittingConfig",
]
