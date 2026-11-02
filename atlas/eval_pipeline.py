"""Evaluation pipeline for ATLAS - computes metrics from eval data and surfaces calibration.

This module implements the evaluation pipeline step from the ATLAS forward plan:
- Runs compute_metrics() from eval_set.py on eval entry data
- Surfaces confidence calibration drift, hit rates by horizon, and r_multiple averages
- Designed for weekly execution (e.g., via cron or scheduler)

Two-AI compliant: reads from Journal ledger or generates fresh eval sets; never places orders.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional, Dict

# Use absolute imports; the package is on PATH when running from repo root
from atlas.eval_set import compute_metrics, generate_eval_set, Outcome
from atlas.research_ai import ConfigDrivenResearchAI
from atlas.rag_corpus import RAGCorpus


def run_evaluation_pipeline(
    n_entries: int = 100,
    use_fresh_data: bool = True,
    rag_corpus: Optional[RAGCorpus] = None,
) -> dict[str, Any]:
    """Run the evaluation pipeline and compute metrics from historical eval data.

    Args:
        n_entries: Number of eval entries to generate (default 100).
        use_fresh_data: If True, generates fresh eval set from yfinance.
            If False, would read from Journal ledger (future extension).
        rag_corpus: Optional RAGCorpus instance to use when generating eval data.

    Returns:
        Metrics dict with hit_rate, avg_r_multiple, calibration, intraday/swing breakdown.
    """
    print(f"=== ATLAS Evaluation Pipeline ===")
    print(f"Generating {n_entries} eval entries...")

    # Step 1: Generate eval set (or read from ledger if use_fresh_data=False)
    if use_fresh_data:
        eval_entries = generate_eval_set(n=n_entries)
        print(f"  Generated {len(eval_entries)} eval entries from yfinance historical data")
    else:
        # TODO: Read from Journal ledger when Journal integration is complete
        print("  [INFO] use_fresh_data=False: would read from Journal ledger")
        eval_entries = generate_eval_set(n=n_entries)

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
    eval_entries: List[dict[str, Any]],
    confidence_bins: Optional[List[tuple[float, float]]] = None,
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

    results: Dict[str, Any] = {
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
    # Run the pipeline when executed directly
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    metrics = run_evaluation_pipeline(n_entries=n)
    
    # Save metrics summary
    print(f"\n=== Pipeline Complete ===")
    print(f"Metrics: hit_rate={metrics['hit_rate']:.2%}, "
          f"avg_r={metrics['avg_r_multiple']:.2f}, "
          f"samples={metrics['total_samples']}")
