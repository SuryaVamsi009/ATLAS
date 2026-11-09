"""Evaluation pipeline for ATLAS - computes metrics from real replayed bars and surfaces calibration.

This module implements the evaluation pipeline step from the ATLAS forward plan:
- Runs the backtest engine on real replayed bars (no synthetic eval sets)
- Surfaces confidence calibration, hit rates by horizon, and r_multiple averages
- Designed for weekly execution (e.g., via cron or scheduler)

Two-AI compliant: reads from Journal ledger or replays real bars through the
backtest engine; never places orders.
"""

from __future__ import annotations

from typing import Any

# Use absolute imports; the package is on PATH when running from repo root
from atlas.eval_set import Outcome, compute_metrics, build_eval_set
from atlas.call_registry import read_calls


def run_evaluation_pipeline(
    bars_by_symbol: dict[str, list[list[float]]] | None = None,
    calls_path: str | None = None,
    round_trip_cost_pct: float | None = None,
) -> dict[str, Any]:
    """Run the evaluation pipeline on real replayed bars and registered calls.

    Args:
        bars_by_symbol: Dict mapping symbol -> list of OHLCV bars [ts, o, h, l, c, v].
            If None, reads from Journal ledger instead.
        calls_path: Path to call registry JSONL file. If None, uses default.
        round_trip_cost_pct: Optional round-trip cost percentage (e.g., 0.11 for 0.11%).

    Returns:
        Metrics dict with hit_rate, avg_r_multiple, calibration, intraday/swing breakdown.
    """
    print("=== ATLAS Evaluation Pipeline ===")

    # Step 1: Build eval set from registered calls and real bars
    if bars_by_symbol is not None:
        print("  Building eval set from registered calls and real bars...")
        calls = read_calls(calls_path)
        print(f"  Read {len(calls)} calls from registry")

        eval_entries = build_eval_set(calls, bars_by_symbol, round_trip_cost_pct)
        print(f"  Built {len(eval_entries)} eval entries")
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
    print("\n--- Evaluation Results ---")
    print(f"Total samples: {metrics['total_samples']}")
    print(f"Pending (NOT_TRIGGERED): {metrics['pending']}")
    print(f"Invalid: {metrics['invalid']}")
    print(f"Hit rate: {metrics['hit_rate']:.2%}")
    print(f"Average r_multiple: {metrics['avg_r_multiple']:.2f}")
    print(f"Intraday hit rate: {metrics['intraday_hit_rate']:.2%} (avg r: {metrics['intraday_avg_r']:.2f})")
    print(f"Swing hit rate: {metrics['swing_hit_rate']:.2%} (avg r: {metrics['swing_avg_r']:.2f})")

    # Confidence calibration - print observed rates per bin (no hardcoded 70%)
    print("\n--- Confidence Calibration (Observed Rates) ---")
    if metrics['calibration']:
        for bin_entry in metrics['calibration']:
            print(
                f"  Confidence {bin_entry['confidence_range']}: "
                f"success rate {bin_entry['success_rate']:.1%} "
                f"(avg r: {bin_entry['avg_r_multiple']:.2f}, "
                f"samples: {bin_entry['sample_count']})"
            )
    else:
        print("  No calibration data (no resolved entries with confidence)")

    # Overall calibration summary
    if metrics['calibration']:
        total_weighted_hits = sum(
            c['success_rate'] * c['sample_count'] for c in metrics['calibration']
        )
        total_weighted_samples = sum(c['sample_count'] for c in metrics['calibration'])
        overall_calibration = total_weighted_hits / total_weighted_samples if total_weighted_samples > 0 else 0

        print("\n--- Overall Calibration ---")
        print(f"Weighted success rate across all bins: {overall_calibration:.2%}")
        # No hardcoded thresholds - just report the observed rate
        print(f"  (Observed overall success rate: {overall_calibration:.1%})")

    return metrics


if __name__ == "__main__":
    # Run the pipeline when executed directly (reads from journal ledger)
    metrics = run_evaluation_pipeline()

    # Save metrics summary
    print("\n=== Pipeline Complete ===")
    print(f"Metrics: hit_rate={metrics['hit_rate']:.2%}, "
          f"avg_r={metrics['avg_r_multiple']:.2f}, "
          f"samples={metrics['total_samples']}")
