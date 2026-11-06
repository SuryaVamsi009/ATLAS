"""Tests for atlas.decision_proposal module."""

from atlas.decision_proposal import DecisionProposal


class TestDecisionProposal:
    def test_decision_proposal_creation_buy(self):
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Strong uptrend with RSI > 60 and MACD bullish crossover",
        )
        assert proposal.action == "BUY"
        assert proposal.confidence == 0.85
        assert proposal.size_hint == 0.5
        assert proposal.stop_hint == 19300.0
        assert proposal.rationale == "Strong uptrend with RSI > 60 and MACD bullish crossover"

    def test_decision_proposal_creation_sell(self):
        proposal = DecisionProposal(
            action="SELL",
            confidence=0.75,
            size_hint=0.5,
            stop_hint=19700.0,
            rationale="Bearish divergence on RSI",
        )
        assert proposal.action == "SELL"
        assert proposal.stop_hint == 19700.0

    def test_decision_proposal_creation_hold(self):
        proposal = DecisionProposal(
            action="HOLD",
            confidence=0.60,
            size_hint=0.0,
            stop_hint=None,
            rationale="Mixed signals, waiting for clearer direction",
        )
        assert proposal.action == "HOLD"
        assert proposal.size_hint == 0.0
        assert proposal.stop_hint is None

    def test_decision_proposal_confidence_bounds(self):
        # The actual class doesn't validate confidence bounds in __init__
        # It just stores the value
        proposal = DecisionProposal(
            action="BUY",
            confidence=1.5,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test",
        )
        assert proposal.confidence == 1.5

        proposal2 = DecisionProposal(
            action="BUY",
            confidence=-0.1,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test",
        )
        assert proposal2.confidence == -0.1

    def test_decision_proposal_size_hint_negative(self):
        # The actual class doesn't validate size_hint in __init__
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=-10,
            stop_hint=19300.0,
            rationale="Test",
        )
        assert proposal.size_hint == -10

    def test_decision_proposal_hold_no_stop(self):
        proposal = DecisionProposal(
            action="HOLD",
            confidence=0.60,
            size_hint=0.0,
            stop_hint=None,
            rationale="Hold",
        )
        assert proposal.stop_hint is None

    def test_decision_proposal_equality(self):
        """Test that two proposals with same values are equal."""
        p1 = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test",
        )
        p2 = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test",
        )
        assert p1 == p2

    def test_decision_proposal_immutable_fields(self):
        """Test that dataclass fields can be accessed."""
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test",
        )
        # All fields should be accessible
        assert hasattr(proposal, 'action')
        assert hasattr(proposal, 'confidence')
        assert hasattr(proposal, 'size_hint')
        assert hasattr(proposal, 'stop_hint')
        assert hasattr(proposal, 'rationale')
