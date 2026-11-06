"""Quant package for ATLAS - data, backtesting and strategy-validation stack.

This package provides a quantitative trading layer that plugs into the existing
ATLAS flow without changing the contracts (StateSnapshot → DecisionProposal →
RiskVerdict → broker adapter → journal). Research and paper trading only,
no live orders.

Modules:
- data: Loader interface with swappable sources (yfinance intraday) and 1-minute
  collector for Nifty 50 with gap/duplicate/timezone checks
- features: Pure functions on bars (RSI, EMA, ATR, VWAP, opening range, gap)
- strategies: Each strategy emits Signal(symbol, direction, conviction, horizon, stop_distance)
"""

from __future__ import annotations

__version__ = "0.1.0"

# Re-export key classes for convenience
from atlas.quant.data import DataLoader, ParquetCollector, YFinanceLoader
from atlas.quant.features import atr, compute_all_features, ema, gap, opening_range, rsi, vwap
from atlas.quant.strategies import (
    GapFadeStrategy,
    ORBStrategy,
    Signal,
    Strategy,
    VWAPReversionStrategy,
)

__all__ = [
    "DataLoader",
    "YFinanceLoader",
    "ParquetCollector",
    "rsi",
    "ema",
    "atr",
    "vwap",
    "opening_range",
    "gap",
    "compute_all_features",
    "Signal",
    "Strategy",
    "ORBStrategy",
    "VWAPReversionStrategy",
    "GapFadeStrategy",
]
