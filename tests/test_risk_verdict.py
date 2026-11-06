"""Tests for atlas.risk_verdict module."""

from datetime import datetime
from zoneinfo import ZoneInfo

from atlas.decision_proposal import DecisionProposal
from atlas.risk_verdict import VetoReason, verify
from atlas.state_snapshot import StateSnapshot, compute_from_bars

IST = ZoneInfo("Asia/Kolkata")


def make_context(
    max_position_size: float = 1.0,
    max_daily_loss: float = 1000.0,
    max_weekly_loss: float = 5000.0,
    min_confidence: float = 0.3,
    max_confidence: float = 0.9,
    allowed_symbols: list[str] | None = None,
    current_time: datetime | None = None,
    equity: float = 10000.0,
) -> dict:
    """Create a risk context dict with defaults."""
    if allowed_symbols is None:
        allowed_symbols = ["NIFTY", "BANKNIFTY"]
    if current_time is None:
        current_time = datetime(2026, 11, 6, 10, 0, tzinfo=IST)
    return {
        "max_position_size": max_position_size,
        "max_daily_loss": max_daily_loss,
        "max_weekly_loss": max_weekly_loss,
        "min_confidence": min_confidence,
        "max_confidence": max_confidence,
        "allowed_symbols": allowed_symbols,
        "current_time": current_time,
        "equity": equity,
    }


def make_snapshot(
    symbol: str = "NIFTY",
    daily_pnl: float = 0.0,
    timestamp: datetime | None = None,
) -> StateSnapshot:
    """Create a test StateSnapshot."""
    bars = [
        [1730428800000, 19500.0, 19600.0, 19450.0, 19550.0, 1500000],
        [1730515200000, 19550.0, 19650.0, 19500.0, 19600.0, 1800000],
    ]
    snapshot = compute_from_bars(symbol, "1d", bars)
    # Modify account daily_pnl
    snapshot.account["daily_pnl"] = daily_pnl
    if timestamp:
        # Create new snapshot with modified timestamp
        snapshot = StateSnapshot(
            snapshot_id=snapshot.snapshot_id,
            timestamp=timestamp,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            ohlcv_tail=snapshot.ohlcv_tail,
            indicators=snapshot.indicators,
            regime_features=snapshot.regime_features,
            position=snapshot.position,
            account=snapshot.account,
        )
    return snapshot


class TestRiskVerdict:
    def setup_method(self):
        self.context = make_context()
        self.snapshot = make_snapshot()

    def test_risk_verdict_approved_buy(self):
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,  # 50% of equity
            stop_hint=19300.0,
            rationale="Test",
        )
        verdict = verify(proposal, self.snapshot, self.context)
        assert verdict.approved is True
        assert verdict.veto_reason == VetoReason.NONE
        assert verdict.checks["size_ok"] is True
        assert verdict.checks["loss_ok"] is True
        assert verdict.checks["hours_ok"] is True
        assert verdict.checks["symbol_ok"] is True
        assert verdict.checks["confidence_ok"] is True

    def test_risk_verdict_approved_sell(self):
        proposal = DecisionProposal(
            action="SELL",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19700.0,
            rationale="Test",
        )
        verdict = verify(proposal, self.snapshot, self.context)
        assert verdict.approved is True

    def test_risk_verdict_approved_hold(self):
        proposal = DecisionProposal(
            action="HOLD",
            confidence=0.60,
            size_hint=0.0,
            stop_hint=None,
            rationale="Test",
        )
        verdict = verify(proposal, self.snapshot, self.context)
        assert verdict.approved is True

    def test_risk_verdict_rejected_size_too_large(self):
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=2.0,  # 200% of equity - exceeds max_position_size=1.0
            stop_hint=19300.0,
            rationale="Test",
        )
        verdict = verify(proposal, self.snapshot, self.context)
        assert verdict.approved is False
        assert verdict.checks["size_ok"] is False
        assert verdict.veto_reason == VetoReason.SIZE_OK

    def test_risk_verdict_rejected_daily_loss_exceeded(self):
        # Create snapshot with daily loss exceeding limit
        snapshot = make_snapshot(daily_pnl=-1500.0)  # -1500 > -1000 limit

        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test",
        )
        verdict = verify(proposal, snapshot, self.context)
        assert verdict.approved is False
        assert verdict.checks["loss_ok"] is False
        assert verdict.veto_reason == VetoReason.LOSS_OK

    def test_risk_verdict_rejected_outside_market_hours(self):
        # Create context with timestamp before market open (8:00 IST)
        context = make_context(current_time=datetime(2026, 11, 6, 8, 0, tzinfo=IST))

        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test",
        )
        verdict = verify(proposal, self.snapshot, context)
        assert verdict.approved is False
        assert verdict.checks["hours_ok"] is False
        assert verdict.veto_reason == VetoReason.HOURS_OK

    def test_risk_verdict_rejected_symbol_not_allowed(self):
        # The verify function checks symbol from snapshot, not proposal
        # So we need to create a snapshot with a symbol not in allowed_symbols
        snapshot = make_snapshot(symbol="RELIANCE")

        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test",
        )
        verdict = verify(proposal, snapshot, self.context)
        assert verdict.approved is False
        assert verdict.checks["symbol_ok"] is False
        assert verdict.veto_reason == VetoReason.SYMBOL_OK

    def test_risk_verdict_rejected_confidence_too_low(self):
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.2,  # Below 0.3 minimum
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test",
        )
        verdict = verify(proposal, self.snapshot, self.context)
        assert verdict.approved is False
        assert verdict.checks["confidence_ok"] is False
        assert verdict.veto_reason == VetoReason.CONFIDENCE_OK

    def test_risk_verdict_rejected_confidence_too_high(self):
        # Confidence above max_confidence (0.9)
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.95,  # Above 0.9 maximum
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test",
        )
        verdict = verify(proposal, self.snapshot, self.context)
        assert verdict.approved is False
        assert verdict.checks["confidence_ok"] is False
        assert verdict.veto_reason == VetoReason.CONFIDENCE_OK

    def test_risk_verdict_multiple_failures_first_reported(self):
        # Multiple failures - should report first one (size_ok)
        context = make_context(
            current_time=datetime(2026, 11, 6, 8, 0, tzinfo=IST),  # outside hours
            allowed_symbols=["NIFTY"],  # RELIANCE not allowed
        )
        snapshot = make_snapshot(
            symbol="RELIANCE",
            daily_pnl=-1500.0,  # exceeds daily loss
        )

        proposal = DecisionProposal(
            action="BUY",
            confidence=0.2,  # too low
            size_hint=2.0,  # too large
            stop_hint=19300.0,
            rationale="Test",
        )
        verdict = verify(proposal, snapshot, context)
        assert verdict.approved is False
        # First check that fails is size_ok
        assert verdict.veto_reason == VetoReason.SIZE_OK

    def test_risk_verdict_final_qty_calculation(self):
        """Test that final_qty is calculated correctly as whole shares."""
        # With size_hint=0.5 and equity=10000, notional=5000
        # Entry price ~19600, so qty = floor(5000/19600) = 0
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test",
        )
        verdict = verify(proposal, self.snapshot, self.context)
        assert verdict.final_qty == 0

        # With size_hint=1.0, notional=10000, qty = floor(10000/19600) = 0
        proposal2 = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=1.0,
            stop_hint=19300.0,
            rationale="Test",
        )
        verdict2 = verify(proposal2, self.snapshot, self.context)
        assert verdict2.final_qty == 0

        # With size_hint=2.0, notional=20000, qty = floor(20000/19600) = 1
        # But size check fails first (2.0 > 1.0), so final_qty = 0
        proposal3 = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=2.0,
            stop_hint=19300.0,
            rationale="Test",
        )
        verdict3 = verify(proposal3, self.snapshot, self.context)
        assert verdict3.final_qty == 0  # size check fails first

        # To get qty=1, need size_hint <= 1.0 but large enough notional
        # With equity=100000, size_hint=1.0 -> notional=100000, qty = floor(100000/19600) = 5
        # But need to ensure loss check passes - use a tight stop
        context_large = make_context(equity=100000.0, max_daily_loss=100000.0)
        proposal4 = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=1.0,
            stop_hint=19500.0,  # tight stop to pass loss check
            rationale="Test",
        )
        verdict4 = verify(proposal4, self.snapshot, context_large)
        assert verdict4.final_qty == 5

    def test_risk_verdict_context_defaults(self):
        """Test that context defaults work when not provided."""
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test",
        )
        # Empty context should use defaults
        # But need to provide current_time and allowed_symbols
        context = {
            "allowed_symbols": ["NIFTY"],
            "current_time": datetime(2026, 11, 6, 10, 0, tzinfo=IST),
        }
        verdict = verify(proposal, self.snapshot, context)
        # With defaults: max_position_size=1.0, min_confidence=0.3, etc.
        # Should pass all checks
        assert verdict.approved is True

    def test_veto_reason_enum_values(self):
        """Test VetoReason enum values."""
        assert VetoReason.SIZE_OK.value == "size_ok"
        assert VetoReason.LOSS_OK.value == "loss_ok"
        assert VetoReason.HOURS_OK.value == "hours_ok"
        assert VetoReason.SYMBOL_OK.value == "symbol_ok"
        assert VetoReason.CONFIDENCE_OK.value == "confidence_ok"
        assert VetoReason.NONE.value is None

    def test_veto_reason_bool(self):
        """Test VetoReason boolean evaluation."""
        assert bool(VetoReason.SIZE_OK) is True
        assert bool(VetoReason.NONE) is False
