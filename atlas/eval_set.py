"""Eval set module for the ATLAS architecture.

Generates historical market snapshots with known outcomes for model calibration.
Includes grading logic to mechanically determine ground truth from price bars,
and metrics computation for evaluation.
"""

from __future__ import annotations

from enum import Enum
import random
from datetime import datetime, timedelta
from typing import Any

import yfinance as yf

from decision_proposal import DecisionProposal
from atlas.risk_verdict import RiskVerdict, StateSnapshot, VetoReason
from atlas.state_snapshot import compute_from_bars


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
# Helper: fetch historical bars from yfinance
# ---------------------------------------------------------------------------

def _fetch_bars(
    symbol: str,
    start: datetime,
    end: datetime,
    timeframe: str = "1d",
) -> list[list[float]]:
    """Fetch historical OHLCV bars from yfinance.

    Returns bars in the format [timestamp_ms, open, high, low, close, volume].
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start, end=end, interval=timeframe)
        if hist.empty:
            return []
        # yfinance returns index as datetime; convert to list format
        bars: list[list[float]] = []
        for idx, row in hist.iterrows():
            ts = idx.timestamp() * 1000  # milliseconds
            bars.append([ts, float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]), float(row["Volume"])])
        return bars
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Eval entry type
# ---------------------------------------------------------------------------

EvalEntry = dict[str, Any]


def _make_decision_proposal(
    action: str,
    confidence: float,
    size_hint: float,
    stop_hint: float | None = None,
    rationale: str | None = None,
) -> DecisionProposal:
    """Factory for DecisionProposal."""
    return DecisionProposal(
        action=action,
        confidence=confidence,
        size_hint=size_hint,
        stop_hint=stop_hint,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# generate_eval_set
# ---------------------------------------------------------------------------

def generate_eval_set(
    n: int = 100,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
) -> list[EvalEntry]:
    """Generate a set of historical market snapshots with known outcomes.

    Creates n eval entries drawn from the symbol universe across the date range.
    Each entry contains a StateSnapshot, a DecisionProposal (the "model's"
    decision), a RiskVerdict (the "correct" verdict based on hindsight), and
    a ground-truth Outcome determined mechanically from price bars.

    The set is designed to be diverse: different symbols, different regimes
    (trending, chop, reversal), and different confidence levels.

    Args:
        n: Number of eval entries to generate (default 100).
        start_date: Start date for historical data. Defaults to 2 years ago.
        end_date: End date for historical data. Defaults to now.
        symbols: List of symbols to sample from. If None, uses a default universe.
        timeframes: List of timeframes to sample from. If None, uses ["1h", "4h", "1d"].

    Returns:
        List of eval entry dicts, each with keys:
        - snapshot_id: str
        - timestamp: datetime
        - symbol: str
        - timeframe: str
        - ohlcv_tail: list of bars (each [ts, open, high, low, close, volume])
        - ground_truth: dict with keys "outcome", "entry_price", "target_price",
          "stop_price", "expiry", "r_multiple"
        - decision_proposal: DecisionProposal
        - risk_verdict: RiskVerdict
    """
    # Default date range: 2 years back to now
    if start_date is None:
        start_date = datetime.utcnow() - timedelta(days=730)
    if end_date is None:
        end_date = datetime.utcnow()

    # Default symbol universe (major crypto & forex pairs)
    if symbols is None:
        symbols = [
            "BTC-USD",
            "ETH-USD",
            "AAPL",
            "TSLA",
            "NVDA",
            "SPY",
            "GLD",
        ]

    # Default timeframes
    if timeframes is None:
        timeframes = ["1h", "4h", "1d"]

    eval_entries: list[EvalEntry] = []

    # Regime types and confidence levels for diversity
    regime_types = ["trending", "chop", "reversal"]
    confidence_levels = [0.55, 0.65, 0.75, 0.85]

    for i in range(n):
        # Select symbol and timeframe round-robin for diversity, then randomize
        symbol = symbols[i % len(symbols)]
        timeframe = timeframes[i % len(timeframes)]
        regime = regime_types[i % len(regime_types)]
        confidence = confidence_levels[i % len(confidence_levels)]

        # Compute date range for this snapshot – roughly evenly spread across
        # the total range, with some randomness for diversity
        range_ms = (end_date - start_date).total_seconds()
        lookback_days = random.uniform(7, 60)
        snap_start = start_date + timedelta(
            seconds=random.uniform(0, range_ms - lookback_days * 86400)
        )
        snap_end = min(snap_start + timedelta(days=lookback_days), end_date)

        # Fetch historical bars
        bars = _fetch_bars(symbol, snap_start, snap_end, timeframe)

        if len(bars) < 10:
            # Skip insufficient data
            bars = _fetch_bars(symbol, start_date, end_date, timeframe)
            if len(bars) < 10:
                continue

        # Take a random contiguous segment as the "tail"
        tail_start = random.randint(0, max(0, len(bars) - 10))
        ohlcv_tail = bars[tail_start : tail_start + random.randint(5, 15)]

        # Determine entry, target, stop, and expiry from the tail
        # Use the first bar's close as entry price
        entry_price = float(ohlcv_tail[0][4])  # close of first bar in tail

        # Pick a later bar for target/stop levels (simulating a trade horizon)
        horizon_idx = random.randint(2, len(ohlcv_tail) - 1)
        horizon_bar = ohlcv_tail[horizon_idx]
        horizon_close = float(horizon_bar[4])

        # Randomly decide trade direction (mimicking model's action)
        action = random.choice(["BUY", "SELL"])

        if action == "BUY":
            # Long trade: target above, stop below
            target_pct = random.uniform(0.5, 3.0)  # target % from entry
            stop_pct = target_pct / random.uniform(1.5, 3.0)  # stop % from entry (RR >= 1.5)
            if random.random() < 0.5:
                # Price goes up direction
                target_price = entry_price * (1 + target_pct / 100)
                stop_price = entry_price * (1 - stop_pct / 100)
            else:
                # Price goes down direction
                target_price = entry_price * (1 + target_pct / 100)
                stop_price = entry_price * (1 - stop_pct / 100)
        else:
            # Short trade: target below, stop above
            target_pct = random.uniform(0.5, 3.0)
            stop_pct = target_pct / random.uniform(1.5, 3.0)
            target_price = entry_price * (1 - target_pct / 100)
            stop_price = entry_price * (1 + stop_pct / 100)

        # Set expiry – 30 days from the tail's start timestamp
        first_ts = int(ohlcv_tail[0][0])
        if first_ts > 1e12:
            first_dt = datetime.fromtimestamp(first_ts / 1000.0)
        else:
            first_dt = datetime.fromtimestamp(first_ts)
        expiry = first_dt + timedelta(days=30)

        # --- GROUND TRUTH: mechanically determine outcome from bars ---
        # Re-fetch a broader set of bars to determine the true outcome
        full_start = snap_start
        full_end = snap_end + timedelta(days=1)
        all_bars = _fetch_bars(symbol, full_start, full_end, timeframe)

        # Use snap_end as current_time so expiry is relative to the data range,
        # not absolute wall-clock time. This ensures outcomes are mechanically
        # determined from the available bar data rather than depending on when
        # the eval set is generated.
        current_time = snap_end if all_bars else snap_start

        if all_bars:
            outcome = grade_outcome(
                all_bars,
                entry_price=entry_price,
                target_price=target_price,
                stop_price=stop_price,
                expiry=expiry,
                current_time=current_time,
            )
        else:
            outcome = Outcome.NOT_TRIGGERED

        # Compute r_multiple: (exit_price - entry_price) / risk
        # risk = |entry - stop|
        risk = abs(entry_price - stop_price)
        if risk == 0:
            r_multiple = 0.0
        else:
            if outcome == Outcome.TARGET_HIT:
                reward = abs(target_price - entry_price)
                r_multiple = reward / risk if risk != 0 else 0.0
            elif outcome == Outcome.STOP_HIT:
                reward = -risk  # negative r multiple
                r_multiple = reward / risk if risk != 0 else 0.0
            elif outcome == Outcome.EXPIRED:
                r_multiple = 0.0
            else:  # NOT_TRIGGERED
                r_multiple = 0.0

        # Determine horizon label
        horizon_label = "intraday" if timeframe in ("1m", "5m", "15m", "1h") else "swing"

        # Build the DecisionProposal (the "model's" decision)
        proposal = _make_decision_proposal(
            action=action,
            confidence=confidence,
            size_hint=random.uniform(0.1, 0.5),
            stop_hint=stop_price,
            rationale=f"Generated eval set entry {i+1}: {regime} regime, {symbol} {timeframe}",
        )

        # Build ohlcv_tail as list of lists for the EvalEntry (serializable)
        ohlcv_tail_serializable = [
            [int(bar[0]), bar[1], bar[2], bar[3], bar[4], bar[5]] for bar in ohlcv_tail
        ]

        # Build RiskVerdict based on ground-truth outcome
        # This represents the "correct" verdict with hindsight
        if outcome == Outcome.TARGET_HIT:
            verdict = RiskVerdict(
                approved=True,
                final_qty=proposal.size_hint * 10000.0,
                final_stop=stop_price,
                veto_reason=None,
                checks={
                    "size_ok": True,
                    "loss_ok": True,
                    "hours_ok": True,
                    "symbol_ok": True,
                    "confidence_ok": proposal.confidence >= 0.3,
                },
            )
        elif outcome == Outcome.STOP_HIT:
            verdict = RiskVerdict(
                approved=True,
                final_qty=proposal.size_hint * 10000.0,
                final_stop=stop_price,
                veto_reason=None,
                checks={
                    "size_ok": True,
                    "loss_ok": True,
                    "hours_ok": True,
                    "symbol_ok": True,
                    "confidence_ok": proposal.confidence >= 0.3,
                },
            )
        elif outcome == Outcome.EXPIRED:
            verdict = RiskVerdict(
                approved=False,
                final_qty=0.0,
                final_stop=stop_price,
                veto_reason=VetoReason.CONFIDENCE_OK,
                checks={
                    "size_ok": True,
                    "loss_ok": True,
                    "hours_ok": False,
                    "symbol_ok": True,
                    "confidence_ok": False,
                },
            )
        else:  # NOT_TRIGGERED
            verdict = RiskVerdict(
                approved=False,
                final_qty=0.0,
                final_stop=stop_price,
                veto_reason=VetoReason.SIZE_OK,
                checks={
                    "size_ok": True,
                    "loss_ok": True,
                    "hours_ok": True,
                    "symbol_ok": True,
                    "confidence_ok": False,
                },
            )

        entry: EvalEntry = {
            "snapshot_id": f"{symbol}_{timeframe}_{int(datetime.utcnow().timestamp())}_{i}",
            "timestamp": datetime.utcnow(),
            "symbol": symbol,
            "timeframe": timeframe,
            "ohlcv_tail": ohlcv_tail_serializable,
            "ground_truth": {
                "outcome": outcome.value,
                "entry_price": entry_price,
                "target_price": target_price,
                "stop_price": stop_price,
                "expiry": expiry,
                "r_multiple": r_multiple,
            },
            "decision_proposal": proposal,
            "risk_verdict": verdict,
        }

        eval_entries.append(entry)

    return eval_entries


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
    bins: dict[tuple[int, int], dict[str, list[float]]] = {}
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
    intraday_avg_r = intraday_r / total if total > 0 else 0.0

    # Swing metrics
    n_swing = sum(
        1 for r in eval_results if r.get("timeframe", "1d") not in ("1m", "5m", "15m", "1h")
    )
    swing_hit_rate = swing_hits / n_swing if n_swing > 0 else 0.0
    swing_avg_r = swing_r / total if total > 0 else 0.0

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