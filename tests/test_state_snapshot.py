"""Tests for atlas.state_snapshot module."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from atlas.state_snapshot import StateSnapshot, compute_from_bars

IST = ZoneInfo("Asia/Kolkata")


class TestStateSnapshot:
    def test_state_snapshot_creation(self):
        snapshot = StateSnapshot(
            snapshot_id="TEST_1h_1234567890",
            timestamp=datetime(2026, 11, 6, 11, 0, tzinfo=IST),
            symbol="NIFTY",
            timeframe="1h",
            ohlcv_tail=[19550.0, 19600.0],
            indicators={
                "rsi": 65.0,
                "atr": 50.0,
                "ema_fast": 19500.0,
                "ema_slow": 19400.0,
                "price_change": 0.01,
            },
            regime_features={"realised_vol": 0.02, "trend_slope": 0.01, "spread": 0.0},
            position={"qty": 50, "avg_price": 19500.0, "unrealised_pnl": 5000.0, "stop": 19300.0},
            account={"equity": 100000.0, "buying_power": 80000.0, "daily_pnl": 500.0},
        )
        assert snapshot.symbol == "NIFTY"
        assert snapshot.timeframe == "1h"
        assert snapshot.ohlcv_tail == [19550.0, 19600.0]
        assert snapshot.indicators["rsi"] == 65.0
        assert snapshot.regime_features["trend_slope"] == 0.01
        assert snapshot.position["qty"] == 50
        assert snapshot.account["equity"] == 100000.0

    def test_compute_from_bars_basic(self):
        bars = [
            [1730428800000, 19500.0, 19600.0, 19450.0, 19550.0, 1500000],
            [1730515200000, 19550.0, 19650.0, 19500.0, 19600.0, 1800000],
            [1730601600000, 19600.0, 19700.0, 19550.0, 19650.0, 2000000],
        ]
        snapshot = compute_from_bars("NIFTY", "1d", bars)
        assert snapshot.symbol == "NIFTY"
        assert snapshot.timeframe == "1d"
        assert len(snapshot.ohlcv_tail) == 2
        assert "rsi" in snapshot.indicators
        assert "atr" in snapshot.indicators
        assert "ema_fast" in snapshot.indicators
        assert "ema_slow" in snapshot.indicators
        assert "price_change" in snapshot.indicators
        assert "realised_vol" in snapshot.regime_features
        assert "trend_slope" in snapshot.regime_features
        assert "spread" in snapshot.regime_features

    def test_compute_from_bars_insufficient_data(self):
        bars = [
            [1730428800000, 19500.0, 19600.0, 19450.0, 19550.0, 1500000],
        ]
        with pytest.raises(ValueError, match="at least 2 bars"):
            compute_from_bars("NIFTY", "1d", bars)

    def test_compute_from_bars_indicators_computed(self):
        bars = [
            [1730428800000, 100.0, 102.0, 99.0, 101.0, 1500.0],
            [1730515200000, 101.0, 103.0, 100.0, 102.0, 1800.0],
            [1730601600000, 102.0, 104.0, 101.0, 103.0, 2000.0],
            [1730688000000, 103.0, 105.0, 102.0, 104.0, 2200.0],
            [1730774400000, 104.0, 106.0, 103.0, 105.0, 2500.0],
        ]
        snapshot = compute_from_bars("TEST", "1d", bars)
        assert "rsi" in snapshot.indicators
        assert "atr" in snapshot.indicators
        assert "ema_fast" in snapshot.indicators
        assert "ema_slow" in snapshot.indicators
        assert "price_change" in snapshot.indicators
        assert snapshot.indicators["rsi"] >= 0
        assert snapshot.indicators["rsi"] <= 100
        assert snapshot.indicators["atr"] >= 0

    def test_compute_from_bars_position_and_account(self):
        bars = [
            [1730428800000, 100.0, 102.0, 99.0, 101.0, 1500.0],
            [1730515200000, 101.0, 103.0, 100.0, 102.0, 1800.0],
        ]
        snapshot = compute_from_bars("TEST", "1d", bars)
        assert snapshot.position["qty"] == 0.0
        assert snapshot.position["avg_price"] == 102.0
        assert snapshot.account["equity"] == 10000.0
        assert snapshot.account["buying_power"] == 10000.0
        assert snapshot.account["daily_pnl"] == 0.0
