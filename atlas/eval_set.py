"""Eval set module for the ATLAS architecture.

Provides grading logic to mechanically determine ground truth from price bars,
and metrics computation for evaluation on real replayed bars.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    INVALID = "INVALID"


@dataclass(frozen=True)
class Grade:
    """Result of grading a call against price bars."""
    outcome: Outcome
    entry_price: float | None
    exit_price: float | None
    r_gross: float | None
    r_net: float | None
    bars_held: int
    entry_ts: int | None  # epoch ms
    exit_ts: int | None   # epoch ms


def grade_call(
    call: dict[str, Any],
    bars: list[list[float]],
    round_trip_cost_pct: float | None = None,
) -> Grade:
    """Grade a call against price bars.

    Args:
        call: Call dict with keys: id, created_at (tz-aware datetime), symbol,
            side (BUY/SELL), stop, target, horizon_bars, confidence, timeframe.
        bars: List of [timestamp_ms, open, high, low, close, volume], ascending.
        round_trip_cost_pct: Optional round-trip cost percentage (e.g., 0.5 for 0.5%).

    Returns:
        Grade with outcome, entry/exit prices, R multiples, and timestamps.
    """
    # Validate call
    created_at = call["created_at"]
    if created_at.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")

    side = call["side"]
    stop = call["stop"]
    target = call["target"]
    horizon_bars = call["horizon_bars"]

    if side not in ("BUY", "SELL"):
        raise ValueError(f"Invalid side: {side}")

    if horizon_bars < 1:
        raise ValueError("horizon_bars must be >= 1")

    if stop <= 0 or target <= 0:
        raise ValueError("stop and target must be > 0")

    is_long = side == "BUY"

    # Validate price relationships
    if is_long:
        if stop >= target:
            raise ValueError("BUY requires stop < target")
    else:
        if target >= stop:
            raise ValueError("SELL requires target < stop")

    # Find entry bar: first bar with ts > created_at
    created_at_ms = int(created_at.timestamp() * 1000)
    entry_bar_idx = None
    for i, bar in enumerate(bars):
        if bar[0] > created_at_ms:
            entry_bar_idx = i
            break

    if entry_bar_idx is None:
        # No bars after created_at
        return Grade(
            outcome=Outcome.NOT_TRIGGERED,
            entry_price=None,
            exit_price=None,
            r_gross=None,
            r_net=None,
            bars_held=0,
            entry_ts=None,
            exit_ts=None,
        )

    entry_bar = bars[entry_bar_idx]
    entry_price = entry_bar[1]  # open
    entry_ts = entry_bar[0]

    # Check INVALID: entry open already beyond stop or target
    if is_long:
        if entry_price >= target or entry_price <= stop:
            return Grade(
                outcome=Outcome.INVALID,
                entry_price=entry_price,
                exit_price=None,
                r_gross=None,
                r_net=None,
                bars_held=0,
                entry_ts=entry_ts,
                exit_ts=None,
            )
    else:
        if entry_price <= target or entry_price >= stop:
            return Grade(
                outcome=Outcome.INVALID,
                entry_price=entry_price,
                exit_price=None,
                r_gross=None,
                r_net=None,
                bars_held=0,
                entry_ts=entry_ts,
                exit_ts=None,
            )

    # Risk per share
    risk = abs(entry_price - stop)
    if risk == 0:
        raise ValueError("Risk cannot be zero (entry == stop)")

    # Walk bars from entry_bar_idx up to horizon_bars
    max_idx = min(entry_bar_idx + horizon_bars, len(bars))
    bars_walked = 0
    for i in range(entry_bar_idx, max_idx):
        bar = bars[i]
        bar_ts, bar_open, bar_high, bar_low, bar_close, _ = bar
        bars_walked += 1

        # Check stop first, then target
        if is_long:
            # Stop hit: low <= stop
            if bar_low <= stop:
                exit_price = stop if bar_open > stop else bar_open  # gap exit at open
                r_gross = (exit_price - entry_price) / risk
                r_net = _apply_cost(r_gross, entry_price, risk, round_trip_cost_pct)
                return Grade(
                    outcome=Outcome.STOP_HIT,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    r_gross=r_gross,
                    r_net=r_net,
                    bars_held=bars_walked,
                    entry_ts=entry_ts,
                    exit_ts=bar_ts,
                )
            # Target hit: high >= target
            if bar_high >= target:
                exit_price = target if bar_open < target else bar_open  # gap exit at open
                r_gross = (exit_price - entry_price) / risk
                r_net = _apply_cost(r_gross, entry_price, risk, round_trip_cost_pct)
                return Grade(
                    outcome=Outcome.TARGET_HIT,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    r_gross=r_gross,
                    r_net=r_net,
                    bars_held=bars_walked,
                    entry_ts=entry_ts,
                    exit_ts=bar_ts,
                )
        else:
            # Short: stop hit: high >= stop
            if bar_high >= stop:
                exit_price = stop if bar_open < stop else bar_open  # gap exit at open
                r_gross = (entry_price - exit_price) / risk
                r_net = _apply_cost(r_gross, entry_price, risk, round_trip_cost_pct)
                return Grade(
                    outcome=Outcome.STOP_HIT,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    r_gross=r_gross,
                    r_net=r_net,
                    bars_held=bars_walked,
                    entry_ts=entry_ts,
                    exit_ts=bar_ts,
                )
            # Target hit: low <= target
            if bar_low <= target:
                exit_price = target if bar_open > target else bar_open  # gap exit at open
                r_gross = (entry_price - exit_price) / risk
                r_net = _apply_cost(r_gross, entry_price, risk, round_trip_cost_pct)
                return Grade(
                    outcome=Outcome.TARGET_HIT,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    r_gross=r_gross,
                    r_net=r_net,
                    bars_held=bars_walked,
                    entry_ts=entry_ts,
                    exit_ts=bar_ts,
                )

    # If we walked fewer bars than horizon, we ran out of data -> NOT_TRIGGERED
    if bars_walked < horizon_bars:
        return Grade(
            outcome=Outcome.NOT_TRIGGERED,
            entry_price=entry_price,
            exit_price=None,
            r_gross=None,
            r_net=None,
            bars_held=bars_walked,
            entry_ts=entry_ts,
            exit_ts=None,
        )

    # Horizon reached without hitting stop or target
    last_bar = bars[max_idx - 1]
    exit_price = last_bar[4]  # close
    exit_ts = last_bar[0]

    if is_long:
        r_gross = (exit_price - entry_price) / risk
    else:
        r_gross = (entry_price - exit_price) / risk

    r_net = _apply_cost(r_gross, entry_price, risk, round_trip_cost_pct)

    return Grade(
        outcome=Outcome.EXPIRED,
        entry_price=entry_price,
        exit_price=exit_price,
        r_gross=r_gross,
        r_net=r_net,
        bars_held=bars_walked,
        entry_ts=entry_ts,
        exit_ts=exit_ts,
    )


def _apply_cost(
    r_gross: float,
    entry_price: float,
    risk: float,
    cost_pct: float | None,
) -> float | None:
    """Apply round-trip cost to R multiple."""
    if cost_pct is None:
        return None
    cost_per_share = entry_price * cost_pct / 100.0
    cost_in_r = cost_per_share / risk
    return r_gross - cost_in_r


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
    - Hit rate (target vs stop) on resolved outcomes only
    - Average r_multiple on resolved outcomes only
    - Confidence calibration (bin confidence scores vs actual success rates)
    - By horizon (intraday vs swing)
    - Counts of pending and invalid

    Args:
        eval_results: List of eval entry dicts with ground_truth and decision_proposal.

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
            "pending": 0,
            "invalid": 0,
        }

    # Filter resolved outcomes
    resolved = []
    pending = 0
    invalid = 0

    for result in eval_results:
        ground_truth = result.get("ground_truth") or {}
        if isinstance(ground_truth, dict):
            outcome_str = ground_truth.get("outcome", "NOT_TRIGGERED")
        else:
            outcome_str = ground_truth if isinstance(ground_truth, str) else "NOT_TRIGGERED"

        if outcome_str in ("TARGET_HIT", "STOP_HIT", "EXPIRED"):
            resolved.append(result)
        elif outcome_str == "NOT_TRIGGERED":
            pending += 1
        elif outcome_str == "INVALID":
            invalid += 1

    total = len(resolved)

    if total == 0:
        return {
            "hit_rate": 0.0,
            "avg_r_multiple": 0.0,
            "calibration": [],
            "intraday_hit_rate": 0.0,
            "intraday_avg_r": 0.0,
            "swing_hit_rate": 0.0,
            "swing_avg_r": 0.0,
            "total_samples": 0,
            "pending": pending,
            "invalid": invalid,
        }

    # Basic metrics
    hits = 0
    total_r = 0.0
    intraday_hits = 0
    intraday_r = 0.0
    swing_hits = 0
    swing_r = 0.0

    # Confidence calibration: bin confidences into 0.1 buckets
    bins: dict[int, dict[str, Any]] = {}
    for result in resolved:
        # Get confidence from the decision proposal
        proposal = result.get("decision_proposal") or result
        if hasattr(proposal, "confidence"):
            conf = proposal.confidence
        elif isinstance(proposal, dict):
            conf = proposal.get("confidence")
        else:
            conf = None

        # Get outcome
        ground_truth = result.get("ground_truth") or {}
        if isinstance(ground_truth, dict):
            outcome_str = ground_truth.get("outcome", "NOT_TRIGGERED")
        else:
            outcome_str = ground_truth if isinstance(ground_truth, str) else "NOT_TRIGGERED"

        # Get timeframe for horizon classification
        timeframe = result.get("timeframe", "1d")
        is_intraday = timeframe in ("1m", "5m", "15m", "1h")

        # Determine if this is a "hit" (TARGET_HIT, not STOP_HIT/EXPIRED)
        is_hit = outcome_str == "TARGET_HIT"

        # Get r_multiple (net if available, else gross)
        r = ground_truth.get("r_multiple")
        if r is None:
            r = ground_truth.get("r_gross", 0.0)
        r = float(r)

        # Increment basic metrics
        if is_hit:
            hits += 1
        total_r += r

        # Horizon tracking
        if is_intraday:
            if is_hit:
                intraday_hits += 1
            intraday_r += r
        else:
            if is_hit:
                swing_hits += 1
            swing_r += r

        # Confidence calibration - only if confidence is not None
        if conf is not None:
            bin_index = int(conf * 10)  # 0-9
            bin_index = min(bin_index, 9)  # cap at 9

            if bin_index not in bins:
                bins[bin_index] = {"hits": 0, "total": 0, "r_multiples": []}

            bins[bin_index]["total"] += 1
            if is_hit:
                bins[bin_index]["hits"] += 1
            bins[bin_index]["r_multiples"].append(r)

    # Compute hit rate
    hit_rate = hits / total if total > 0 else 0.0

    # Average r_multiple
    avg_r = total_r / total if total > 0 else 0.0

    # Intraday metrics
    n_intraday = sum(
        1 for r in resolved if r.get("timeframe", "1d") in ("1m", "5m", "15m", "1h")
    )
    intraday_hit_rate = intraday_hits / n_intraday if n_intraday > 0 else 0.0
    intraday_avg_r = intraday_r / n_intraday if n_intraday > 0 else 0.0

    # Swing metrics
    n_swing = sum(
        1 for r in resolved if r.get("timeframe", "1d") not in ("1m", "5m", "15m", "1h")
    )
    swing_hit_rate = swing_hits / n_swing if n_swing > 0 else 0.0
    swing_avg_r = swing_r / n_swing if n_swing > 0 else 0.0

    # Confidence calibration – compute success rate per bin
    calibration = []
    for bin_index in sorted(bins.keys()):
        bin_data = bins[bin_index]
        success_rate = bin_data["hits"] / bin_data["total"] if bin_data["total"] > 0 else 0.0
        avg_r_in_bin = sum(bin_data["r_multiples"]) / len(bin_data["r_multiples"]) if bin_data["r_multiples"] else 0.0
        calibration.append(
            {
                "confidence_range": f"{bin_index * 0.1:.1f}-{(bin_index + 1) * 0.1:.1f}",
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
        "pending": pending,
        "invalid": invalid,
    }


def build_eval_set(
    calls: list[dict[str, Any]],
    bars_by_symbol: dict[str, list[list[float]]],
    round_trip_cost_pct: float | None = None,
) -> list[dict[str, Any]]:
    """Build evaluation set from registered calls and real replayed bars.

    This replaces the old `generate_eval_set()` which fabricated synthetic data.
    Now we use real calls from the call registry and real bars from data feeds.

    Args:
        calls: List of call dicts from the call registry (append-only JSONL).
        bars_by_symbol: Dict mapping symbol -> list of OHLCV bars [ts, o, h, l, c, v].
        round_trip_cost_pct: Optional round-trip cost percentage (e.g., 0.11 for 0.11%).

    Returns:
        List of eval entry dicts with:
        - timeframe: from call
        - decision_proposal: {confidence, side, stop, target, horizon_bars}
        - ground_truth: {outcome, r_multiple, r_gross, entry_price, exit_price, bars_held}
    """
    eval_entries = []

    for call in calls:
        symbol = call.get("symbol")
        if not symbol or symbol not in bars_by_symbol:
            # Skip calls for symbols we don't have bars for
            continue

        bars = bars_by_symbol[symbol]
        if not bars:
            continue

        # Grade the call against real bars
        grade = grade_call(call, bars, round_trip_cost_pct)

        # Build eval entry
        entry = {
            "timeframe": call.get("timeframe", "1d"),
            "decision_proposal": {
                "confidence": call.get("confidence"),
                "side": call.get("side"),
                "stop": call.get("stop"),
                "target": call.get("target"),
                "horizon_bars": call.get("horizon_bars"),
            },
            "ground_truth": {
                "outcome": grade.outcome.value,
                "r_multiple": grade.r_net if grade.r_net is not None else grade.r_gross,
                "r_gross": grade.r_gross,
                "entry_price": grade.entry_price,
                "exit_price": grade.exit_price,
                "bars_held": grade.bars_held,
                "entry_ts": grade.entry_ts,
                "exit_ts": grade.exit_ts,
            },
        }
        eval_entries.append(entry)

    return eval_entries