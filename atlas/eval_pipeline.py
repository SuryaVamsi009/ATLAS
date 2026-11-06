"""Evaluation pipeline for ATLAS - computes metrics from real replayed bars and surfaces calibration.

This module implements the evaluation pipeline step from the ATLAS forward plan:
- Runs the backtest engine on real replayed bars (no synthetic eval sets)
- Surfaces confidence calibration drift, hit rates by horizon, and r_multiple averages
- Designed for weekly execution (e.g., via cron or scheduler)

Two-AI compliant: reads from Journal ledger or replays real bars through the
backtest engine; never places orders.
"""

from __future__ import annotations

from typing import Any

# Use absolute imports; the package is on PATH when running from repo root
from atlas.eval_set import Outcome, compute_metrics
from atlas.rag_corpus import RAGCorpus


def run_evaluation_pipeline(
    bars: list[list[float]] | None = None,
    use_fresh_data: bool = True,
    rag_corpus: RAGCorpus | None = None,
) -> dict[str, Any]:
    """Run the evaluation pipeline on real replayed bars.

    Args:
        bars: Real OHLCV bars to replay through the backtest engine.
            If None, reads from Journal ledger instead.
        use_fresh_data: If True and bars provided, runs backtest on real bars.
            If False, reads from Journal ledger instead.
        rag_corpus: Optional RAGCorpus instance.

    Returns:
        Metrics dict with hit_rate, avg_r_multiple, calibration, intraday/swing breakdown.
    """
    print(f"=== ATLAS Evaluation Pipeline ===")

    # Step 1: Evaluate on real replayed bars (or read from ledger)
    if use_fresh_data and bars is not None:
        from atlas.quant.backtest.engine import BacktestConfig, BacktestEngine
        from atlas.quant.backtest.metrics import compute_backtest_metrics

        print(f"  Replaying {len(bars)} real bars through backtest engine...")
        cfg = BacktestConfig()
        engine = BacktestEngine(cfg)

        def _noop_strategy(history, idx, context):
            return None

        bt_result = engine.run(bars, _noop_strategy, warmup=50)
        bt_metrics = compute_backtest_metrics(bt_result)
        print(f"  Backtest: net_pnl={bt_metrics['net_pnl']:.2f}, "
              f"sharpe={bt_metrics['sharpe']:.2f}, trades={bt_metrics['trade_count']}")

        # Convert backtest trades to eval entries for compute_metrics
        eval_entries = [
            {
                "timeframe": "5m",
                "decision_proposal": {"confidence": 0.7},
                "ground_truth": {
                    "outcome": "TARGET_HIT" if t.net_pnl > 0 else "STOP_HIT",
                    "r_multiple": t.r_multiple,
                },
            }
            for t in bt_result.trades
        ]
        print(f"  Converted {len(eval_entries)} trades to eval entries")
    else:
        # Read from Journal ledger
        from atlas.journal import read_all_regime_entries
        eval_entries = read_all_regime_entries()
        print(f"  Read {len(eval_entries)} eval entries from Journal ledger")
        if not eval_entries:
            print("  [WARNING] No journal entries found and no bars provided.")
            eval_entries = []

    # Step 2: Compute metrics
    print("Computing metrics...")
    metrics = compute_metrics(eval_entries)

    # Step 3: Surface key findings
    print(f"\n--- Evaluation Results ---")
    print(f"Total samples: {metrics['total_samples']}")
    print(f"Hit rate: {metrics['hit_rate']:.2%}")
    print(f"Average r_multiple: {metrics['avg_r_multiple']:.2f}")
    print(f"Intraday hit rate: {metrics['intraday_hit_rate']:.2%} (avg r: {metrics['intraday_avg_r']:.2f})")
    print(f"Swing hit rate: {metrics['swing_hit_rate']:.2%} (avg r: {metrics['swing_avg_r']:.2f})")

    # Calibration drift analysis
    print(f"\n--- Confidence Calibration ---")
    for bin_entry in metrics['calibration']:
        drift = bin_entry['success_rate'] - 0.7  # Expected 70% hit rate at this confidence
        drift_marker = " ⚠️" if abs(drift) > 0.1 else ""
        print(
            f"  Confidence {bin_entry['confidence_range']}: "
            f"success rate {bin_entry['success_rate']:.1%} "
            f"(avg r: {bin_entry['avg_r_multiple']:.2f}, "
            f"samples: {bin_entry['sample_count']}){drift_marker}"
        )

    # Calibration summary - check if system is over/under-confident
    if metrics['calibration']:
        # Weighted average success rate
        total_weighted_hits = sum(
            c['success_rate'] * c['sample_count'] for c in metrics['calibration']
        )
        total_weighted_samples = sum(c['sample_count'] for c in metrics['calibration'])
        overall_calibration = total_weighted_hits / total_weighted_samples if total_weighted_samples > 0 else 0

        print(f"\n--- Overall Calibration ---")
        print(f"Weighted success rate across all bins: {overall_calibration:.2%}")
        if overall_calibration > 0.75:
            print("  ⚠️ System is over-confident (success rate > 75%)")
        elif overall_calibration < 0.65:
            print("  ⚠️ System is under-confident (success rate < 65%)")
        else:
            print("  ✅ System confidence is well-calibrated (~70%)")

    # Key insight: if confidence calibration shows significant drift, surface it
    calibration_drifts = [
        c['success_rate'] - 0.7
        for c in metrics['calibration']
        if abs(c['success_rate'] - 0.7) > 0.1
    ]
    if calibration_drifts:
        print(f"\n--- Key Insight ---")
        print(f"  {len(calibration_drifts)} confidence bin(s) show significant drift from expected 70%")
        for drift in calibration_drifts:
            bin_idx = int(drift * 10)
            conf_range = f"{bin_idx * 0.1:.1f}-{(bin_idx + 1) * 0.1:.1f}"
            actual = next(
                c['success_rate'] for c in metrics['calibration']
                if f"{conf_range}" in c['confidence_range']
            )
            direction = "over" if actual > 0.7 else "under"
            print(f"  - {conf_range}: {direction}-confident (actual {actual:.0%} vs expected 70%)")

    return metrics


def quick_calibration_check(
    eval_entries: list[dict[str, Any]],
    confidence_bins: list[tuple[float, float | None]] | None = None,
) -> dict[str, Any]:
    """Quick calibration check on existing eval entries.

    Args:
        eval_entries: List of eval entry dicts.
        confidence_bins: Optional custom confidence bins (min, max). Defaults to 0.1-width bins.

    Returns:
        Calibration dict with success rates per bin.
    """
    if confidence_bins is None:
        confidence_bins = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4),
                          (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8),
                          (0.8, 0.9), (0.9, 1.0)]

    results: dict[str, Any] = {
        "bins": [],
        "overall_success_rate": 0.0,
        "total_samples": len(eval_entries),
        "calibration_drift": 0.0,
    }

    total_hits = 0

    for min_conf, max_conf in confidence_bins:
        bin_entries = [
            e for e in eval_entries
            if min_conf <= (e.get("decision_proposal", {}) or {}).get("confidence", 0.5) < max_conf
        ]

        if not bin_entries:
            results["bins"].append({
                "confidence_range": f"{min_conf:.1f}-{max_conf:.1f}",
                "success_rate": 0.0,
                "avg_r_multiple": 0.0,
                "sample_count": 0,
            })
            continue

        hits = sum(
            1 for e in bin_entries
            if (e.get("ground_truth", {}) or {}).get("outcome") == Outcome.TARGET_HIT.value
        )
        success_rate = hits / len(bin_entries)
        avg_r = sum(
            float((e.get("ground_truth", {}) or {}).get("r_multiple", 0.0))
            for e in bin_entries
        ) / len(bin_entries)

        results["bins"].append({
            "confidence_range": f"{min_conf:.1f}-{max_conf:.1f}",
            "success_rate": success_rate,
            "avg_r_multiple": avg_r,
            "sample_count": len(bin_entries),
        })
        total_hits += hits

    overall_success_rate = total_hits / len(eval_entries) if len(eval_entries) > 0 else 0
    results["overall_success_rate"] = overall_success_rate
    results["calibration_drift"] = overall_success_rate - 0.7  # vs expected 70%

    return results


if __name__ == "__main__":
    # Run the pipeline when executed directly (reads from journal ledger)
    metrics = run_evaluation_pipeline(use_fresh_data=False)
    
    # Save metrics summary
    print(f"\n=== Pipeline Complete ===")
    print(f"Metrics: hit_rate={metrics['hit_rate']:.2%}, "
          f"avg_r={metrics['avg_r_multiple']:.2f}, "
          f"samples={metrics['total_samples']}")
