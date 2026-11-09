"""Tests for atlas/eval_set.py - Grader v2."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from atlas.eval_set import (
    Outcome,
    Grade,
    grade_call,
    compute_metrics,
)


# ---------------------------------------------------------------------------
# Test fixtures / helpers
# ---------------------------------------------------------------------------

def make_call(
    id: str = "call_1",
    created_at: datetime | None = None,
    symbol: str = "RELIANCE.NS",
    side: str = "BUY",
    stop: float = 95.0,
    target: float = 110.0,
    horizon_bars: int = 10,
    confidence: float | None = 0.7,
    timeframe: str = "1d",
) -> dict:
    """Create a call dict for testing."""
    if created_at is None:
        created_at = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
    return {
        "id": id,
        "created_at": created_at,
        "origin": "test",
        "symbol": symbol,
        "side": side,
        "stop": stop,
        "target": target,
        "horizon_bars": horizon_bars,
        "confidence": confidence,
        "rationale": "",
        "snapshot_id": None,
        "timeframe": timeframe,
    }


def make_bar(ts: datetime, open_: float, high: float, low: float, close: float, volume: float = 1000) -> list:
    """Create a bar [timestamp_ms, open, high, low, close, volume]."""
    ts_ms = int(ts.timestamp() * 1000)
    return [ts_ms, open_, high, low, close, volume]


# ---------------------------------------------------------------------------
# grade_call tests
# ---------------------------------------------------------------------------

def test_entry_is_next_bar_open():
    """Entry is the open of the first bar with ts > created_at."""
    call = make_call(created_at=datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc))
    bars = [
        make_bar(datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), 90, 95, 88, 92),  # before call
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 105, 98, 102),  # entry bar
        make_bar(datetime(2024, 1, 15, 9, 30, tzinfo=timezone.utc), 102, 110, 100, 108),  # target hit
    ]
    grade = grade_call(call, bars)
    assert grade.entry_price == 100.0
    assert grade.outcome == Outcome.TARGET_HIT


def test_long_target_hit_2r():
    """Long target hit: entry 100, stop 95, target 110 -> +2R."""
    call = make_call(stop=95.0, target=110.0)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 105, 98, 102),
        make_bar(datetime(2024, 1, 15, 9, 30, tzinfo=timezone.utc), 102, 110, 100, 108),
    ]
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.TARGET_HIT
    assert grade.entry_price == 100.0
    assert grade.exit_price == 110.0
    assert grade.r_gross == 2.0  # (110 - 100) / (100 - 95) = 10/5 = 2


def test_long_stop_hit_1r():
    """Long stop hit: entry 100, stop 95 -> -1R."""
    call = make_call(stop=95.0, target=110.0)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 102, 94, 96),
    ]
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.STOP_HIT
    assert grade.entry_price == 100.0
    assert grade.exit_price == 95.0
    assert grade.r_gross == -1.0  # (95 - 100) / (100 - 95) = -5/5 = -1


def test_bar_touching_both_stop_wins():
    """A bar touching both stop and target: stop wins."""
    call = make_call(stop=95.0, target=110.0)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 110, 95, 105),  # touches both
    ]
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.STOP_HIT
    assert grade.exit_price == 95.0
    assert grade.r_gross == -1.0


def test_gap_through_stop_exits_at_open():
    """Gap through stop exits at the open (worse than 1R loss)."""
    call = make_call(stop=95.0, target=110.0)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 102, 98, 101),  # entry bar
        make_bar(datetime(2024, 1, 15, 9, 30, tzinfo=timezone.utc), 92, 94, 90, 93),  # gapped down
    ]
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.STOP_HIT
    assert grade.entry_price == 100.0
    assert grade.exit_price == 92.0  # exit at the gapped open
    # risk = 100 - 95 = 5, exit - entry = 92 - 100 = -8, R = -8/5 = -1.6
    assert grade.r_gross == -1.6


def test_horizon_reached_exits_at_last_close():
    """Horizon reached with neither level touched exits at last close."""
    call = make_call(stop=95.0, target=110.0, horizon_bars=2)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 102, 98, 101),
        make_bar(datetime(2024, 1, 15, 9, 30, tzinfo=timezone.utc), 101, 104, 100, 104),
    ]
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.EXPIRED
    assert grade.entry_price == 100.0
    assert grade.exit_price == 104.0
    # risk = 5, exit - entry = 4, R = 4/5 = 0.8
    assert grade.r_gross == 0.8


def test_win_inside_horizon_1_is_target_hit():
    """A win inside a horizon of 1 is TARGET_HIT, not EXPIRED."""
    call = make_call(stop=95.0, target=110.0, horizon_bars=1)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 110, 98, 108),
    ]
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.TARGET_HIT
    assert grade.r_gross == 2.0


def test_not_enough_bars_is_not_triggered():
    """Not enough bars is NOT_TRIGGERED with r_gross None."""
    call = make_call(stop=95.0, target=110.0, horizon_bars=5)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 102, 98, 101),
    ]
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.NOT_TRIGGERED
    assert grade.r_gross is None
    assert grade.r_net is None


def test_no_bars_at_all_is_not_triggered():
    """No bars at all is NOT_TRIGGERED."""
    call = make_call()
    bars = []
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.NOT_TRIGGERED
    assert grade.r_gross is None


def test_open_above_target_is_invalid():
    """Open above target is INVALID."""
    call = make_call(stop=95.0, target=110.0)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 112, 115, 110, 113),  # open > target
    ]
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.INVALID
    assert grade.r_gross is None


def test_open_below_stop_is_invalid():
    """Open below stop is INVALID."""
    call = make_call(stop=95.0, target=110.0)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 93, 95, 90, 94),  # open < stop
    ]
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.INVALID
    assert grade.r_gross is None


def test_short_mirror():
    """Short mirror: target below entry, stop above entry."""
    call = make_call(side="SELL", stop=105.0, target=90.0)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 102, 90, 95),  # target hit
    ]
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.TARGET_HIT
    assert grade.entry_price == 100.0
    assert grade.exit_price == 90.0
    # risk = 105 - 100 = 5, entry - exit = 100 - 90 = 10, R = 10/5 = 2
    assert grade.r_gross == 2.0


def test_short_stop_hit():
    """Short stop hit."""
    call = make_call(side="SELL", stop=105.0, target=90.0)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 106, 98, 104),  # stop hit
    ]
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.STOP_HIT
    assert grade.r_gross == -1.0


def test_short_both_touched_stop_wins():
    """Short: bar touching both, stop wins."""
    call = make_call(side="SELL", stop=105.0, target=90.0)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 105, 90, 98),  # touches both
    ]
    grade = grade_call(call, bars)
    assert grade.outcome == Outcome.STOP_HIT
    assert grade.r_gross == -1.0


def test_cost_applied():
    """Cost: 0.5% on entry 100, risk 5 gives 0.1R off."""
    call = make_call(stop=95.0, target=110.0)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 110, 98, 108),
    ]
    grade = grade_call(call, bars, round_trip_cost_pct=0.5)
    assert grade.r_gross == 2.0
    # cost = entry * cost_pct / 100 = 100 * 0.5 / 100 = 0.5
    # cost in R = 0.5 / 5 = 0.1
    # r_net = 2.0 - 0.1 = 1.9
    assert grade.r_net == 1.9


def test_cost_none_when_not_supplied():
    """r_net is None when no cost is supplied."""
    call = make_call(stop=95.0, target=110.0)
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 110, 98, 108),
    ]
    grade = grade_call(call, bars, round_trip_cost_pct=None)
    assert grade.r_net is None


def test_intraday_bar_after_9am_is_entry():
    """An intraday bar after 09:00 on the call's day is the entry."""
    call = make_call(
        created_at=datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc),
        timeframe="1m",
    )
    bars = [
        make_bar(datetime(2024, 1, 15, 8, 59, tzinfo=timezone.utc), 90, 95, 88, 92),  # before 9am
        make_bar(datetime(2024, 1, 15, 9, 1, tzinfo=timezone.utc), 100, 105, 98, 102),  # after 9am - entry
    ]
    grade = grade_call(call, bars)
    assert grade.entry_price == 100.0


def test_grade_dataclass_fields():
    """Grade has all required fields."""
    call = make_call()
    bars = [
        make_bar(datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc), 100, 110, 98, 108),
    ]
    grade = grade_call(call, bars)
    assert hasattr(grade, "outcome")
    assert hasattr(grade, "entry_price")
    assert hasattr(grade, "exit_price")
    assert hasattr(grade, "r_gross")
    assert hasattr(grade, "r_net")
    assert hasattr(grade, "bars_held")
    assert hasattr(grade, "entry_ts")
    assert hasattr(grade, "exit_ts")


# ---------------------------------------------------------------------------
# compute_metrics tests
# ---------------------------------------------------------------------------

def test_compute_metrics_basic():
    """Known set: 2 wins at +2R, 1 loss at -1R, 1 expired at 0R -> hit rate 0.5, avg R 0.75."""
    eval_results = [
        {"ground_truth": {"outcome": "TARGET_HIT", "r_multiple": 2.0}, "decision_proposal": {"confidence": 0.7}, "timeframe": "1d"},
        {"ground_truth": {"outcome": "TARGET_HIT", "r_multiple": 2.0}, "decision_proposal": {"confidence": 0.8}, "timeframe": "1d"},
        {"ground_truth": {"outcome": "STOP_HIT", "r_multiple": -1.0}, "decision_proposal": {"confidence": 0.6}, "timeframe": "1d"},
        {"ground_truth": {"outcome": "EXPIRED", "r_multiple": 0.0}, "decision_proposal": {"confidence": 0.5}, "timeframe": "1d"},
    ]
    metrics = compute_metrics(eval_results)
    assert metrics["total_samples"] == 4
    assert metrics["hit_rate"] == 0.5  # 2/4
    assert metrics["avg_r_multiple"] == 0.75  # (2+2-1+0)/4 = 3/4 = 0.75


def test_compute_metrics_unresolved_excluded_but_counted():
    """Unresolved (NOT_TRIGGERED) excluded from metrics but counted as pending."""
    eval_results = [
        {"ground_truth": {"outcome": "TARGET_HIT", "r_multiple": 2.0}, "decision_proposal": {"confidence": 0.7}, "timeframe": "1d"},
        {"ground_truth": {"outcome": "NOT_TRIGGERED", "r_multiple": None}, "decision_proposal": {"confidence": 0.7}, "timeframe": "1d"},
    ]
    metrics = compute_metrics(eval_results)
    assert metrics["total_samples"] == 1  # only resolved
    assert metrics["hit_rate"] == 1.0
    assert metrics["pending"] == 1


def test_compute_metrics_invalid_excluded_but_counted():
    """INVALID excluded from metrics but counted as invalid."""
    eval_results = [
        {"ground_truth": {"outcome": "TARGET_HIT", "r_multiple": 2.0}, "decision_proposal": {"confidence": 0.7}, "timeframe": "1d"},
        {"ground_truth": {"outcome": "INVALID", "r_multiple": None}, "decision_proposal": {"confidence": 0.7}, "timeframe": "1d"},
    ]
    metrics = compute_metrics(eval_results)
    assert metrics["total_samples"] == 1
    assert metrics["hit_rate"] == 1.0
    assert metrics["invalid"] == 1


def test_compute_metrics_unrated_confidence_skipped_in_calibration():
    """A call with confidence None counts in basic metrics but skipped in calibration."""
    eval_results = [
        {"ground_truth": {"outcome": "TARGET_HIT", "r_multiple": 2.0}, "decision_proposal": {"confidence": 0.7}, "timeframe": "1d"},
        {"ground_truth": {"outcome": "STOP_HIT", "r_multiple": -1.0}, "decision_proposal": {"confidence": None}, "timeframe": "1d"},
    ]
    metrics = compute_metrics(eval_results)
    assert metrics["total_samples"] == 2
    assert metrics["hit_rate"] == 0.5
    # calibration should only have 1 entry (the one with confidence)
    calibration_bins = [b for b in metrics["calibration"] if b["sample_count"] > 0]
    assert sum(b["sample_count"] for b in calibration_bins) == 1


def test_compute_metrics_empty_input():
    """Empty input returns zeros."""
    metrics = compute_metrics([])
    assert metrics["total_samples"] == 0
    assert metrics["hit_rate"] == 0.0
    assert metrics["avg_r_multiple"] == 0.0
    assert metrics["pending"] == 0
    assert metrics["invalid"] == 0


# ---------------------------------------------------------------------------
# Ensure old functions are removed
# ---------------------------------------------------------------------------

def test_grade_outcome_removed():
    """grade_outcome should no longer exist."""
    from atlas import eval_set
    assert not hasattr(eval_set, "grade_outcome")


def test_generate_eval_set_removed():
    """generate_eval_set should no longer exist."""
    from atlas import eval_set
    assert not hasattr(eval_set, "generate_eval_set")


def test_random_not_imported():
    """random module should not be imported in eval_set."""
    import atlas.eval_set as eval_set_module
    # Check that random is not in the module's globals
    assert "random" not in dir(eval_set_module)


# ---------------------------------------------------------------------------
# Tests for build_eval_set
# ---------------------------------------------------------------------------

def test_build_eval_set_basic():
    """build_eval_set creates eval entries from calls and bars."""
    from atlas.eval_set import build_eval_set

    calls = [
        make_call(id="call_1", symbol="RELIANCE.NS", side="BUY", stop=95.0, target=110.0, horizon_bars=10, confidence=0.7),
        make_call(id="call_2", symbol="TCS.NS", side="SELL", stop=3500.0, target=3200.0, horizon_bars=5, confidence=0.6),
    ]

    # Create bars for both symbols
    base_ts = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
    bars_reliance = [
        make_bar(base_ts + timedelta(days=i), 100.0, 105.0, 98.0, 102.0)
        for i in range(15)
    ]
    bars_tcs = [
        make_bar(base_ts + timedelta(days=i), 3400.0, 3450.0, 3350.0, 3380.0)
        for i in range(10)
    ]

    bars_by_symbol = {
        "RELIANCE.NS": bars_reliance,
        "TCS.NS": bars_tcs,
    }

    eval_entries = build_eval_set(calls, bars_by_symbol)

    assert len(eval_entries) == 2
    assert eval_entries[0]["timeframe"] == "1d"
    assert eval_entries[0]["decision_proposal"]["confidence"] == 0.7
    assert eval_entries[0]["decision_proposal"]["side"] == "BUY"
    assert eval_entries[0]["ground_truth"]["outcome"] in [o.value for o in Outcome]
    assert "r_multiple" in eval_entries[0]["ground_truth"]
    assert "entry_price" in eval_entries[0]["ground_truth"]
    assert "exit_price" in eval_entries[0]["ground_truth"]


def test_build_eval_set_skips_missing_symbol():
    """build_eval_set skips calls for symbols without bars."""
    from atlas.eval_set import build_eval_set

    calls = [
        make_call(id="call_1", symbol="RELIANCE.NS"),
        make_call(id="call_2", symbol="TCS.NS"),
    ]

    bars_by_symbol = {
        "RELIANCE.NS": [make_bar(datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc), 100, 105, 98, 102)],
    }

    eval_entries = build_eval_set(calls, bars_by_symbol)

    assert len(eval_entries) == 1
    assert eval_entries[0]["decision_proposal"]["side"] == "BUY"


def test_build_eval_set_skips_empty_bars():
    """build_eval_set skips calls for symbols with empty bars."""
    from atlas.eval_set import build_eval_set

    calls = [make_call(id="call_1", symbol="RELIANCE.NS")]
    bars_by_symbol = {"RELIANCE.NS": []}

    eval_entries = build_eval_set(calls, bars_by_symbol)

    assert len(eval_entries) == 0


def test_build_eval_set_with_costs():
    """build_eval_set applies round-trip costs when provided."""
    from atlas.eval_set import build_eval_set

    calls = [make_call(id="call_1", symbol="RELIANCE.NS", stop=95.0, target=110.0, horizon_bars=10)]

    base_ts = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
    bars = [
        make_bar(base_ts + timedelta(days=i), 100.0, 105.0, 98.0, 102.0)
        for i in range(15)
    ]
    bars_by_symbol = {"RELIANCE.NS": bars}

    # Without costs
    eval_no_cost = build_eval_set(calls, bars_by_symbol, round_trip_cost_pct=None)
    # With costs (0.11%)
    eval_with_cost = build_eval_set(calls, bars_by_symbol, round_trip_cost_pct=0.11)

    # r_net should be different from r_gross when costs applied
    assert eval_with_cost[0]["ground_truth"]["r_multiple"] != eval_no_cost[0]["ground_truth"]["r_multiple"]
    # r_net should be lower (costs reduce returns)
    assert eval_with_cost[0]["ground_truth"]["r_multiple"] < eval_no_cost[0]["ground_truth"]["r_multiple"]


def test_build_eval_set_preserves_all_fields():
    """build_eval_set preserves all relevant fields in output."""
    from atlas.eval_set import build_eval_set

    calls = [make_call(
        id="call_1",
        symbol="RELIANCE.NS",
        side="BUY",
        stop=95.0,
        target=110.0,
        horizon_bars=10,
        confidence=0.75,
        timeframe="5m",
    )]

    base_ts = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
    bars = [
        make_bar(base_ts + timedelta(minutes=5*i), 100.0, 105.0, 98.0, 102.0)
        for i in range(15)
    ]
    bars_by_symbol = {"RELIANCE.NS": bars}

    eval_entries = build_eval_set(calls, bars_by_symbol)

    entry = eval_entries[0]
    assert entry["timeframe"] == "5m"
    assert entry["decision_proposal"]["confidence"] == 0.75
    assert entry["decision_proposal"]["side"] == "BUY"
    assert entry["decision_proposal"]["stop"] == 95.0
    assert entry["decision_proposal"]["target"] == 110.0
    assert entry["decision_proposal"]["horizon_bars"] == 10

    gt = entry["ground_truth"]
    assert gt["outcome"] in [o.value for o in Outcome]
    assert "r_multiple" in gt
    assert "r_gross" in gt
    assert "entry_price" in gt
    assert "exit_price" in gt
    assert "bars_held" in gt
    assert "entry_ts" in gt
    assert "exit_ts" in gt