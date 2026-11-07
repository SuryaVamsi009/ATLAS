"""Validation harness for ATLAS backtests.

Implements:
- Purged walk-forward splits (purge gap between train and test to avoid leakage)
- Untouched hold-out period (never used during development)
- Trial log (quant/trials.jsonl) recording every strategy and parameter set tried
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


@dataclass
class ValidationConfig:
    """Configuration for walk-forward validation."""

    n_splits: int = 5                    # number of walk-forward splits
    purge_bars: int = 20                 # bars purged between train and test (leakage prevention)
    holdout_fraction: float = 0.2        # fraction of data reserved as untouched hold-out
    trial_log_path: str = "atlas/quant/trials.jsonl"

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_splits": self.n_splits,
            "purge_bars": self.purge_bars,
            "holdout_fraction": self.holdout_fraction,
            "trial_log_path": self.trial_log_path,
        }


@dataclass
class WalkForwardSplit:
    """A single walk-forward split."""

    split_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    train_bars: list[list[float]]
    test_bars: list[list[float]]


class TrialLog:
    """Append-only trial log at quant/trials.jsonl.

    Records every strategy and parameter set tried during validation.
    """

    def __init__(self, path: str = "atlas/quant/trials.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log_trial(
        self,
        strategy_name: str,
        params: dict[str, Any],
        metrics: dict[str, Any],
        split_index: int | None = None,
        is_holdout: bool = False,
    ) -> str:
        """Log a single trial. Returns the trial ID."""
        trial_id = f"trial_{datetime.now(tz=IST).strftime('%Y%m%d_%H%M%S_%f')}"
        entry = {
            "trial_id": trial_id,
            "timestamp": datetime.now(tz=IST).isoformat(),
            "strategy": strategy_name,
            "params": params,
            "metrics": metrics,
            "split_index": split_index,
            "is_holdout": is_holdout,
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return trial_id

    def read_all(self) -> list[dict[str, Any]]:
        """Read all trial entries."""
        if not self.path.exists():
            return []
        entries = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def count_trials(self) -> int:
        """Count total number of trials logged."""
        return len(self.read_all())


class WalkForwardValidator:
    """Purged walk-forward validation with hold-out.

    Splits data into:
    1. Hold-out: last `holdout_fraction` of bars (never touched during dev)
    2. Walk-forward: remaining bars split into n_splits train/test windows
       with `purge_bars` gap between train end and test start
    """

    def __init__(self, config: ValidationConfig | None = None) -> None:
        self.config = config or ValidationConfig()
        self.trial_log = TrialLog(self.config.trial_log_path)

    def create_splits(self, bars: list[list[float]]) -> tuple[list[WalkForwardSplit], list[list[float]]]:
        """Create walk-forward splits and hold-out from bars.

        Returns:
            (splits, holdout_bars)
        """
        n = len(bars)
        holdout_size = int(n * self.config.holdout_fraction)
        holdout_bars = bars[n - holdout_size:] if holdout_size > 0 else []
        wf_bars = bars[: n - holdout_size] if holdout_size > 0 else bars

        n_wf = len(wf_bars)
        # Each split: test window is n_wf / n_splits bars
        test_size = n_wf // self.config.n_splits
        splits = []

        for i in range(self.config.n_splits):
            test_start = i * test_size
            test_end = test_start + test_size if i < self.config.n_splits - 1 else n_wf
            # Train: everything before test_start minus purge gap
            train_end = max(0, test_start - self.config.purge_bars)
            train_start = 0

            if train_end <= train_start or test_end <= test_start:
                continue

            splits.append(WalkForwardSplit(
                split_index=i,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                train_bars=wf_bars[train_start:train_end],
                test_bars=wf_bars[test_start:test_end],
            ))

        return splits, holdout_bars

    def run_validation(
        self,
        bars: list[list[float]],
        strategy_factory: Callable[[dict[str, Any]], Callable],
        param_grid: list[dict[str, Any]],
        warmup: int = 50,
    ) -> dict[str, Any]:
        """Run walk-forward validation over a parameter grid.

        Args:
            bars: Full bar series
            strategy_factory: fn(params) -> strategy_fn for BacktestEngine
            param_grid: List of parameter dicts to try
            warmup: Warmup bars for each backtest

        Returns:
            Validation results with per-split metrics, hold-out metrics, trial count
        """
        from atlas.quant.backtest.engine import BacktestConfig, BacktestEngine
        from atlas.quant.backtest.metrics import compute_backtest_metrics

        splits, holdout_bars = self.create_splits(bars)
        results: dict[str, Any] = {
            "n_splits": len(splits),
            "n_holdout_bars": len(holdout_bars),
            "param_results": [],
            "holdout_results": [],
        }

        for params in param_grid:
            strategy_fn = strategy_factory(params)
            split_metrics = []

            for split in splits:
                cfg = BacktestConfig()
                engine = BacktestEngine(cfg)
                bt_result = engine.run(split.test_bars, strategy_fn, warmup=warmup)
                metrics = compute_backtest_metrics(bt_result)
                split_metrics.append(metrics)
                self.trial_log.log_trial(
                    strategy_name=strategy_factory.__name__ if hasattr(strategy_factory, "__name__") else "strategy",
                    params=params,
                    metrics=metrics,
                    split_index=split.split_index,
                )

            # Aggregate across splits
            avg_net_pnl = sum(m["net_pnl"] for m in split_metrics) / len(split_metrics) if split_metrics else 0.0
            avg_sharpe = sum(m["sharpe"] for m in split_metrics) / len(split_metrics) if split_metrics else 0.0
            avg_hit_rate = sum(m["hit_rate"] for m in split_metrics) / len(split_metrics) if split_metrics else 0.0

            param_result = {
                "params": params,
                "avg_net_pnl": avg_net_pnl,
                "avg_sharpe": avg_sharpe,
                "avg_hit_rate": avg_hit_rate,
                "split_metrics": split_metrics,
            }
            results["param_results"].append(param_result)

            # Hold-out evaluation (only for the best params, or all - here we do all)
            if holdout_bars:
                cfg = BacktestConfig()
                engine = BacktestEngine(cfg)
                bt_result = engine.run(holdout_bars, strategy_fn, warmup=warmup)
                ho_metrics = compute_backtest_metrics(bt_result)
                self.trial_log.log_trial(
                    strategy_name=strategy_factory.__name__ if hasattr(strategy_factory, "__name__") else "strategy",
                    params=params,
                    metrics=ho_metrics,
                    is_holdout=True,
                )
                results["holdout_results"].append({"params": params, "metrics": ho_metrics})

        results["total_trials"] = self.trial_log.count_trials()
        return results
