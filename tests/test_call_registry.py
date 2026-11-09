"""Tests for atlas.call_registry module."""

from __future__ import annotations

import json
import os
import pytest
from datetime import datetime, timezone, timedelta

from atlas.call_registry import (
    Call,
    append_call,
    read_calls,
    DuplicateCallError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_call():
    """A valid Call for testing."""
    return Call(
        id="test-001",
        created_at=datetime(2024, 1, 15, 9, 15, tzinfo=timezone.utc),
        origin="research_ai",
        symbol="RELIANCE.NS",
        side="BUY",
        stop=2500.0,
        target=2600.0,
        horizon_bars=10,
        confidence=0.7,
        rationale="Test call",
        snapshot_id="snap-001",
        timeframe="1d",
    )


@pytest.fixture
def temp_registry(tmp_path):
    """Temporary registry file path."""
    return str(tmp_path / "calls.jsonl")


# ---------------------------------------------------------------------------
# Call validation tests
# ---------------------------------------------------------------------------

def test_call_roundtrip(valid_call, temp_registry):
    """Test round-trip: append then read returns equal call."""
    append_call(valid_call, temp_registry)
    calls = read_calls(temp_registry)
    assert len(calls) == 1
    assert calls[0] == valid_call


def test_call_duplicate_id_rejected(valid_call, temp_registry):
    """Test duplicate ID raises DuplicateCallError and file unchanged."""
    append_call(valid_call, temp_registry)

    # Try to append same ID
    with pytest.raises(DuplicateCallError):
        append_call(valid_call, temp_registry)

    # File should have only one entry
    calls = read_calls(temp_registry)
    assert len(calls) == 1


def test_call_invalid_side_raises():
    """Test invalid side raises ValueError."""
    with pytest.raises(ValueError, match="side must be BUY or SELL"):
        Call(
            id="test-001",
            created_at=datetime.now(timezone.utc),
            origin="test",
            symbol="RELIANCE.NS",
            side="HOLD",
            stop=2500.0,
            target=2600.0,
            horizon_bars=10,
            confidence=0.7,
        )


def test_call_buy_stop_ge_target_raises():
    """Test BUY with stop >= target raises ValueError."""
    with pytest.raises(ValueError, match="BUY requires stop < target"):
        Call(
            id="test-001",
            created_at=datetime.now(timezone.utc),
            origin="test",
            symbol="RELIANCE.NS",
            side="BUY",
            stop=2600.0,
            target=2500.0,
            horizon_bars=10,
            confidence=0.7,
        )


def test_call_sell_target_ge_stop_raises():
    """Test SELL with target >= stop raises ValueError."""
    with pytest.raises(ValueError, match="SELL requires target < stop"):
        Call(
            id="test-001",
            created_at=datetime.now(timezone.utc),
            origin="test",
            symbol="RELIANCE.NS",
            side="SELL",
            stop=2500.0,
            target=2600.0,
            horizon_bars=10,
            confidence=0.7,
        )


def test_call_horizon_bars_zero_raises():
    """Test horizon_bars < 1 raises ValueError."""
    with pytest.raises(ValueError, match="horizon_bars must be >= 1"):
        Call(
            id="test-001",
            created_at=datetime.now(timezone.utc),
            origin="test",
            symbol="RELIANCE.NS",
            side="BUY",
            stop=2500.0,
            target=2600.0,
            horizon_bars=0,
            confidence=0.7,
        )


def test_call_negative_prices_raise():
    """Test negative/zero prices raise ValueError."""
    with pytest.raises(ValueError, match="stop and target must be positive"):
        Call(
            id="test-001",
            created_at=datetime.now(timezone.utc),
            origin="test",
            symbol="RELIANCE.NS",
            side="BUY",
            stop=0,
            target=2600.0,
            horizon_bars=10,
            confidence=0.7,
        )


def test_call_confidence_out_of_range_raises():
    """Test confidence outside [0,1] raises ValueError."""
    with pytest.raises(ValueError, match="confidence must be in"):
        Call(
            id="test-001",
            created_at=datetime.now(timezone.utc),
            origin="test",
            symbol="RELIANCE.NS",
            side="BUY",
            stop=2500.0,
            target=2600.0,
            horizon_bars=10,
            confidence=1.5,
        )


def test_call_naive_datetime_raises():
    """Test naive datetime raises ValueError."""
    with pytest.raises(ValueError, match="timezone-aware"):
        Call(
            id="test-001",
            created_at=datetime(2024, 1, 15, 9, 15),  # No tzinfo
            origin="test",
            symbol="RELIANCE.NS",
            side="BUY",
            stop=2500.0,
            target=2600.0,
            horizon_bars=10,
            confidence=0.7,
        )


def test_call_invalid_symbol_format_raises():
    """Test symbol not ending in .NS or .BO raises ValueError."""
    with pytest.raises(ValueError, match="symbol must end with .NS or .BO"):
        Call(
            id="test-001",
            created_at=datetime.now(timezone.utc),
            origin="test",
            symbol="BTC-USD",
            side="BUY",
            stop=2500.0,
            target=2600.0,
            horizon_bars=10,
            confidence=0.7,
        )


def test_call_aapl_rejected():
    """Test AAPL (non-Indian) is rejected."""
    with pytest.raises(ValueError, match="symbol must end with .NS or .BO"):
        Call(
            id="test-001",
            created_at=datetime.now(timezone.utc),
            origin="test",
            symbol="AAPL",
            side="BUY",
            stop=150.0,
            target=160.0,
            horizon_bars=10,
            confidence=0.7,
        )


def test_call_unrated_confidence_allowed(valid_call):
    """Test confidence=None is allowed."""
    call = Call(
        id="test-002",
        created_at=datetime.now(timezone.utc),
        origin="test",
        symbol="RELIANCE.NS",
        side="BUY",
        stop=2500.0,
        target=2600.0,
        horizon_bars=10,
        confidence=None,
    )
    assert call.confidence is None


# ---------------------------------------------------------------------------
# Universe validation tests
# ---------------------------------------------------------------------------

def test_call_universe_validation_passes(valid_call, temp_registry):
    """Test call with symbol in universe passes."""
    universe = ("RELIANCE.NS", "TCS.NS", "INFY.NS")
    append_call(valid_call, temp_registry, universe=universe)
    calls = read_calls(temp_registry)
    assert len(calls) == 1


def test_call_universe_validation_fails(valid_call, temp_registry):
    """Test call with symbol not in universe fails."""
    universe = ("TCS.NS", "INFY.NS")  # RELIANCE.NS not in universe
    with pytest.raises(ValueError, match="not in universe"):
        append_call(valid_call, temp_registry, universe=universe)


# ---------------------------------------------------------------------------
# read_calls tests
# ---------------------------------------------------------------------------

def test_read_calls_missing_file_returns_empty(temp_registry):
    """Test reading non-existent file returns empty list."""
    calls = read_calls(temp_registry)
    assert calls == []


def test_read_calls_multiple_calls(valid_call, temp_registry):
    """Test reading multiple calls preserves order."""
    call2 = Call(
        id="test-002",
        created_at=datetime(2024, 1, 15, 9, 30, tzinfo=timezone.utc),
        origin="research_ai",
        symbol="TCS.NS",
        side="SELL",
        stop=3600.0,
        target=3400.0,
        horizon_bars=5,
        confidence=0.6,
    )
    append_call(valid_call, temp_registry)
    append_call(call2, temp_registry)

    calls = read_calls(temp_registry)
    assert len(calls) == 2
    assert calls[0].id == "test-001"
    assert calls[1].id == "test-002"


def test_read_calls_skips_malformed_lines(valid_call, temp_registry):
    """Test malformed JSON lines are skipped."""
    append_call(valid_call, temp_registry)

    # Append malformed line
    with open(temp_registry, "a", encoding="utf-8") as f:
        f.write("not valid json\n")

    calls = read_calls(temp_registry)
    assert len(calls) == 1
    assert calls[0].id == "test-001"


# ---------------------------------------------------------------------------
# No update/edit/delete functions test
# ---------------------------------------------------------------------------

def test_no_update_edit_delete_functions():
    """Test module has no update, edit, or delete functions."""
    import atlas.call_registry as mod

    # Check for common mutation function names
    forbidden = ["update_call", "edit_call", "delete_call", "remove_call", "modify_call"]
    for name in forbidden:
        assert not hasattr(mod, name), f"Module should not have {name}"