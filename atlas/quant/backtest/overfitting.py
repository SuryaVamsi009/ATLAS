"""Overfitting checks for ATLAS backtests.

Implements:
- Deflated Sharpe ratio (Bailey & López de Prado): adjusts Sharpe for the
  number of trials tried, accounting for selection bias under multiple testing
- 2x cost stress test: re-run at double the transaction costs
- Parameter plateau check: performance should hold across a plateau of
  nearby parameters, not just a single peak
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from atlas.quant.backtest.costs import IndianCostConfig
from atlas.quant.backtest.engine import BacktestConfig, BacktestEngine
from atlas.quant.backtest.metrics import compute_backtest_metrics


@dataclass
class OverfittingConfig:
    """Configuration for overfitting checks."""

    cost_multiplier: float = 2.0         # stress test at 2x costs
    plateau_tolerance: float = 0.10      # params within 10% of best are "plateau"
    min_trials_for_deflation: int = 10   # minimum trials before deflated Sharpe is meaningful

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cost_multiplier": self.cost_multiplier,
            "plateau_tolerance": self.plateau_tolerance,
            "min_trials_for_deflation": self.min_trials_for_deflation,
        }


def deflated_sharpe(
    sharpe: float,
    n_trials: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
    n_observations: int = 252,
) -> float:
    """Compute the deflated Sharpe ratio (Bailey & López de Prado, 2014).

    Adjusts the observed Sharpe for the expected maximum Sharpe under
    multiple testing with n_trials independent trials.

    Args:
        sharpe: Observed Sharpe ratio
        n_trials: Number of trials (strategies/parameter sets) tried
        skewness: Return skewness (default 0)
        kurtosis: Return kurtosis (default 3, normal)
        n_observations: Number of return observations

    Returns:
        Deflated Sharpe ratio. If <= 0, the result is not statistically significant.
    """
    if n_trials <= 1 or n_observations <= 1:
        return sharpe

    # Variance of Sharpe ratio estimate
    var_sharpe = (1.0 + (sharpe ** 2) / 2.0 - skewness * sharpe / math.sqrt(n_observations)
                  + (kurtosis - 3.0) / (4.0 * n_observations)) / n_observations
    if var_sharpe <= 0:
        return sharpe

    # Expected maximum Sharpe under null (E[max] of n_trials standard normals)
    # Using the approximation: E[max] ≈ sqrt(2 * ln(n_trials)) for large n
    if n_trials > 2:
        expected_max_sharpe = math.sqrt(var_sharpe) * (
            (1.0 - 0.5772156649) * math.sqrt(2.0 * math.log(n_trials - 1)) + 0.5772156649
        )
    else:
        expected_max_sharpe = math.sqrt(var_sharpe) * 0.5772156649  # Euler-Mascheroni for n=2

    deflated = (sharpe - expected_max_sharpe) / math.sqrt(var_sharpe) if var_sharpe > 0 else 0.0
    # Convert back to Sharpe-like scale
    return deflated * math.sqrt(var_sharpe) + expected_max_sharpe - expected_max_sharpe


def probability_of_sharpe(
    sharpe: float,
    n_trials: int,
    n_observations: int = 252,
) -> float:
    """Probability that the true Sharpe is positive given observed Sharpe and n_trials.

    Uses the deflated Sharpe framework: P(SR_true > 0 | SR_obs, n_trials).
    """
    if n_trials <= 1:
        # Single trial: standard normal CDF
        from math import erf, sqrt
        return 0.5 * (1.0 + erf(sharpe * math.sqrt(n_observations) / math.sqrt(2.0)))

    dsr = deflated_sharpe(sharpe, n_trials, n_observations=n_observations)
    from math import erf, sqrt
    # Probability that deflated Sharpe > 0
    return 0.5 * (1.0 + erf(dsr * math.sqrt(n_observations) / math.sqrt(2.0)))


class OverfittingChecker:
    """Runs overfitting checks on backtest results.

    Checks:
    1. Deflated Sharpe using trial count from the trial log
    2. 2x cost stress test
    3. Parameter plateau (performance holds across nearby params)
    """

    def __init__(self, config: OverfittingConfig | None = None) -> None:
        self.config = config or OverfittingConfig()

    def check_deflated_sharpe(
        self,
        observed_sharpe: float,
        n_trials: int,
        n_observations: int = 252,
    ) -> Dict[str, Any]:
        """Check if the observed Sharpe survives deflation for multiple testing."""
        dsr = deflated_sharpe(observed_sharpe, n_trials, n_observations=n_observations)
        psr = probability_of_sharpe(observed_sharpe, n_trials, n_observations)
        return {
            "observed_sharpe": observed_sharpe,
            "n_trials": n_trials,
            "deflated_sharpe": dsr,
            "probability_sharpe_positive": psr,
            "passes": dsr > 0 and psr > 0.95,
            "significant": psr > 0.95,
        }

    def stress_test_costs(
        self,
        bars: List[List[float]],
        strategy_fn: Callable,
        base_config: BacktestConfig | None = None,
        warmup: int = 50,
    ) -> Dict[str, Any]:
        """Re-run the backtest at 2x transaction costs.

        If performance collapses at 2x costs, the strategy is likely
        overfit to the cost assumptions.
        """
        base_cfg = base_config or BacktestConfig()

        # Base run
        engine_base = BacktestEngine(base_cfg)
        result_base = engine_base.run(bars, strategy_fn, warmup=warmup)
        metrics_base = compute_backtest_metrics(result_base)

        # 2x cost run
        stressed_cost = IndianCostConfig(
            brokerage_rate=base_cfg.cost_config.brokerage_rate * self.config.cost_multiplier,
            brokerage_cap=base_cfg.cost_config.brokerage_cap * self.config.cost_multiplier,
            stt_rate=base_cfg.cost_config.stt_rate * self.config.cost_multiplier,
            exchange_rate=base_cfg.cost_config.exchange_rate * self.config.cost_multiplier,
            sebi_rate=base_cfg.cost_config.sebi_rate * self.config.cost_multiplier,
            stamp_duty_rate=base_cfg.cost_config.stamp_duty_rate * self.config.cost_multiplier,
        )
        stressed_cfg = BacktestConfig(
            initial_capital=base_cfg.initial_capital,
            cost_config=stressed_cost,
        )
        engine_stressed = BacktestEngine(stressed_cfg)
        result_stressed = engine_stressed.run(bars, strategy_fn, warmup=warmup)
        metrics_stressed = compute_backtest_metrics(result_stressed)

        # Performance should hold (not collapse) at 2x costs
        pnl_ratio = (
            metrics_stressed["net_pnl"] / metrics_base["net_pnl"]
            if metrics_base["net_pnl"] != 0 else 0.0
        )

        return {
            "base_metrics": metrics_base,
            "stressed_metrics": metrics_stressed,
            "cost_multiplier": self.config.cost_multiplier,
            "pnl_ratio_at_2x_costs": pnl_ratio,
            "passes": metrics_stressed["net_pnl"] > 0 if metrics_base["net_pnl"] > 0 else metrics_stressed["net_pnl"] >= metrics_base["net_pnl"],
        }

    def check_parameter_plateau(
        self,
        param_results: List[Dict[str, Any]],
        metric_key: str = "avg_sharpe",
    ) -> Dict[str, Any]:
        """Check that performance holds across a plateau of parameters.

        A robust strategy should perform well across a range of nearby
        parameters, not just at a single peak (which suggests overfitting).

        Args:
            param_results: List of {"params": dict, metric_key: float, ...}
            metric_key: Which metric to use for plateau check

        Returns:
            Plateau analysis with best params, plateau params, and pass/fail
        """
        if not param_results:
            return {"passes": False, "reason": "no param results"}

        # Find best
        best = max(param_results, key=lambda x: x.get(metric_key, float("-inf")))
        best_val = best.get(metric_key, 0.0)

        if best_val <= 0:
            return {"passes": False, "reason": "best metric is not positive", "best": best}

        # Plateau: params within tolerance of best
        threshold = best_val * (1.0 - self.config.plateau_tolerance)
        plateau = [p for p in param_results if p.get(metric_key, float("-inf")) >= threshold]

        # A plateau should have more than 1 parameter set
        passes = len(plateau) > 1

        return {
            "best_params": best["params"],
            "best_metric": best_val,
            "plateau_size": len(plateau),
            "plateau_params": [p["params"] for p in plateau],
            "plateau_threshold": threshold,
            "passes": passes,
            "reason": "plateau found" if passes else "single peak - possible overfitting",
        }

    def run_all_checks(
        self,
        bars: List[List[float]],
        strategy_fn: Callable,
        n_trials: int,
        param_results: List[Dict[str, Any]],
        base_config: BacktestConfig | None = None,
        warmup: int = 50,
        n_observations: int = 252,
    ) -> Dict[str, Any]:
        """Run all overfitting checks.

        Returns:
            Dict with deflated_sharpe, cost_stress, plateau checks
        """
        base_cfg = base_config or BacktestConfig()
        engine = BacktestEngine(base_cfg)
        result = engine.run(bars, strategy_fn, warmup=warmup)
        metrics = compute_backtest_metrics(result)

        return {
            "deflated_sharpe": self.check_deflated_sharpe(
                metrics["sharpe"], n_trials, n_observations
            ),
            "cost_stress_2x": self.stress_test_costs(bars, strategy_fn, base_cfg, warmup),
            "parameter_plateau": self.check_parameter_plateau(param_results),
            "base_metrics": metrics,
        }
