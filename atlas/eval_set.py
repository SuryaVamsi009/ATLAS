"""Eval set module for the ATLAS architecture.

Provides grading logic to mechanically determine ground truth from price bars,
and metrics computation for evaluation on real replayed bars.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Grading logic – mechanically determine outcome from price bars
# ---------------------------------------------------------------------------

class Outcome(Enum):
    """Ground-truth outcome of a trade proposal."""
    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    EXPIRED = "EXPIRED"
    NOT_TRIGGERED = "NOT_TRIGGERED"


def grade_outcome(
    bars: list[list[float]],
    entry_price: float,
    target_price: float,
    stop_price: float,
    expiry: datetime | None,
    current_time: datetime,
) -> Outcome:
    """Determine the ground-truth outcome from raw OHLC bars.

    The grading logic follows the ATLAS architecture's mechanical call grading
    (see grading.py mapping in ATLAS_6_LAYER_MAPPING.md). Outcome priority:

    1. If price hit target before stop → TARGET_HIT
    2. If price hit stop before target → STOP_HIT
    3. If expiry is set and current_time >= expiry → EXPIRED
    4. Otherwise → NOT_TRIGGERED

    For each bar (timestamp, open, high, low, close, volume), we check whether
    the target or stop was touched at any point during the bar interval.

    Args:
        bars: Raw market bars [timestamp, open, high, low, close, volume].
        entry_price: The price at which the trade was entered.
        target_price: The target price level.
        stop_price: The stop price level.
        expiry: Optional expiry datetime; if None, bars extend indefinitely.
        current_time: The "now" time used to decide EXPIRED vs NOT_TRIGGERED.

    Returns:
        Outcome enum indicating the mechanical grading result.
    """
    # Determine which side of the market we're on based on entry vs target/stop
    # Assume a long position: target above entry, stop below entry
    # If short, the logic is inverted – we detect direction from the price levels.

    is_long = target_price > entry_price and stop_price < entry_price

    # If expiry is set and we've passed it, the trade expired
    if expiry is not None and current_time >= expiry:
        return Outcome.EXPIRED

    # Scan bars to find if target or stop was hit
    for bar in bars:
        bar_timestamp, bar_open, bar_high, bar_low, bar_close, _volume = bar

        # Convert timestamp (ms or s) to datetime
        if bar_timestamp > 1e12:  # milliseconds
            bar_dt = datetime.fromtimestamp(bar_timestamp / 1000.0)
        else:  # seconds
            bar_dt = datetime.fromtimestamp(bar_timestamp)

        # Skip bars after expiry
        if expiry is not None and bar_dt > expiry:
            break

        if is_long:
            # Long: target hit if high >= target; stop hit if low <= stop
            if bar_high >= target_price:
                return Outcome.TARGET_HIT
            if bar_low <= stop_price:
                return Outcome.STOP_HIT
        else:
            # Short: target hit if low <= target; stop hit if high >= stop
            if bar_low <= target_price:
                return Outcome.TARGET_HIT
            if bar_high >= stop_price:
                return Outcome.STOP_HIT

    # No target or stop hit within the available bars
    if expiry is not None and current_time < expiry:
        return Outcome.NOT_TRIGGERED
    return Outcome.EXPIRED


# ---------------------------------------------------------------------------
# Eval entry type
# ---------------------------------------------------------------------------

EvalEntry = dict[str, Any]


# ---------------------------------------------------------------------------
# compute_metrics
# ---------------------------------------------------------------------------

def compute_metrics(eval_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute evaluation metrics from a list of eval entry results.

    Calculates:
    - Hit rate (target vs stop)
    - Average r_multiple
    - Confidence calibration (bin confidence scores vs actual success rates)
    - By horizon (intraday vs swing)

    Args:
        eval_results: List of eval entry dicts as returned by generate_eval_set,
            possibly with additional result fields added by the caller.

    Returns:
        Dict with computed metrics.
    """
    if not eval_results:
        return {
            "hit_rate": 0.0,
            "avg_r_multiple": 0.0,
            "calibration": [],
            "intraday_hit_rate": 0.0,
            "intraday_avg_r": 0.0,
            "swing_hit_rate": 0.0,
            "swing_avg_r": 0.0,
            "total_samples": 0,
        }

    total = len(eval_results)

    # Basic metrics
    hits = 0
    total_r = 0.0
    intraday_hits = 0
    intraday_r = 0.0
    swing_hits = 0
    swing_r = 0.0

    # Confidence calibration: bin confidences into 0.1 buckets
    bins: dict[tuple[int, int], dict[str, Any]] = {}
    for result in eval_results:
        # Get confidence from the decision proposal
        proposal = result.get("decision_proposal") or result
        # Handle both DecisionProposal objects and dicts
        if hasattr(proposal, "confidence"):
            conf = proposal.confidence
        elif isinstance(proposal, dict):
            conf = proposal.get("confidence", 0.5)
        else:
            conf = 0.5

        # Get outcome
        ground_truth = result.get("ground_truth") or {}
        if isinstance(ground_truth, dict):
            outcome_str = ground_truth.get("outcome", "NOT_TRIGGERED")
        else:
            outcome_str = ground_truth if isinstance(ground_truth, str) else "NOT_TRIGGERED"

        # Get timeframe for horizon classification
        timeframe = result.get("timeframe", "1d")
        is_intraday = timeframe in ("1m", "5m", "15m", "1h")

        # Bin the confidence
        bin_index = int(conf * 10)  # 0-9
        bin_index = min(bin_index, 9)  # cap at 9
        bin_key = (bin_index, 0)  # (bin, horizon_flag)

        if bin_key not in bins:
            bins[bin_key] = {"hits": 0, "total": 0, "r_multiples": [], "intraday": []}

        bins[bin_key]["total"] += 1

        # Determine if this is a "hit" (TARGET_HIT, not STOP_HIT/EXPIRED)
        is_hit = outcome_str == "TARGET_HIT"
        if is_hit:
            bins[bin_key]["hits"] += 1

        # Get r_multiple
        r = float(ground_truth.get("r_multiple", 0.0))
        bins[bin_key]["r_multiples"].append(r)

        # Increment basic metrics
        if is_hit:
            hits += 1
        total_r += r

        # Horizon tracking
        if is_intraday:
            bins[bin_key]["intraday"].append(r)
            if is_hit:
                intraday_hits += 1
            intraday_r += r
        else:
            if is_hit:
                swing_hits += 1
            swing_r += r

    # Compute hit rate
    hit_rate = hits / total if total > 0 else 0.0

    # Average r_multiple
    avg_r = total_r / total if total > 0 else 0.0

    # Intraday metrics
    n_intraday = sum(
        1 for r in eval_results if r.get("timeframe", "1d") in ("1m", "5m", "15m", "1h")
    )
    intraday_hit_rate = intraday_hits / n_intraday if n_intraday > 0 else 0.0
    intraday_avg_r = intraday_r / n_intraday if n_intraday > 0 else 0.0

    # Swing metrics
    n_swing = sum(
        1 for r in eval_results if r.get("timeframe", "1d") not in ("1m", "5m", "15m", "1h")
    )
    swing_hit_rate = swing_hits / n_swing if n_swing > 0 else 0.0
    swing_avg_r = swing_r / n_swing if n_swing > 0 else 0.0

    # Confidence calibration – compute success rate per bin
    calibration = []
    for bin_key in sorted(bins.keys()):
        bin_data = bins[bin_key]
        success_rate = bin_data["hits"] / bin_data["total"] if bin_data["total"] > 0 else 0.0
        avg_r_in_bin = sum(bin_data["r_multiples"]) / len(bin_data["r_multiples"]) if bin_data["r_multiples"] else 0.0
        calibration.append(
            {
                "confidence_range": f"{bin_key[0] * 0.1:.1f}-{(bin_key[0] + 1) * 0.1:.1f}",
                "success_rate": success_rate,
                "avg_r_multiple": avg_r_in_bin,
                "sample_count": bin_data["total"],
            }
        )

    return {
        "hit_rate": hit_rate,
        "avg_r_multiple": avg_r,
        "calibration": calibration,
        "intraday_hit_rate": intraday_hit_rate,
        "intraday_avg_r": intraday_avg_r,
        "swing_hit_rate": swing_hit_rate,
        "swing_avg_r": swing_avg_r,
        "total_samples": total,
    }
