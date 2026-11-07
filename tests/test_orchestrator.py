"""Tests for atlas.orchestrator module."""

import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

from atlas.brokers.kite_adapter import KiteAdapter
from atlas.decision_proposal import DecisionProposal
from atlas.orchestrator import Orchestrator, OrchestratorConfig
from atlas.research_ai import ConfigDrivenResearchAI, ResearchAI
from atlas.risk_verdict import RiskVerdict
from atlas.state_snapshot import StateSnapshot

IST = ZoneInfo("Asia/Kolkata")
MARKET_BARS = [
    [1730428800000, 100.0, 102.0, 99.0, 101.0, 1500.0],
    [1730515200000, 101.0, 103.0, 100.0, 102.0, 1800.0],
    [1730601600000, 102.0, 104.0, 101.0, 103.0, 2000.0],
]


class StaticResearchAI(ResearchAI):
    def __init__(self, *, fail=False, regime_flags=None, event_alerts=None):
        self.fail = fail
        self.regime_flags = regime_flags or ["trending_up"]
        self.event_alerts = event_alerts or []

    def analyze(self, snapshot, news_context, rag_corpus, context_dict):
        if self.fail:
            raise RuntimeError("research unavailable")
        return {"regime_flags": self.regime_flags, "event_alerts": self.event_alerts}


class FakeKiteAdapter:
    def __init__(self, fail=False, validate_symbol=True):
        self.fail = fail
        self.validate_symbol = validate_symbol
        self.order_attempts = 0
        self.last_order = None

    def _validate_symbol(self, symbol):
        return self.validate_symbol

    def place_order(self, symbol, action, quantity, price):
        self.order_attempts += 1
        self.last_order = {"symbol": symbol, "action": action, "quantity": quantity, "price": price}
        if self.fail:
            raise RuntimeError("broker unavailable")
        return {"order_id": "paper-1"}


class TestOrchestratorConfig:
    def test_orchestrator_config_defaults(self):
        config = OrchestratorConfig()
        assert config.paper_trading is True
        assert config.ai_provider == "rule_based"
        assert config.allowed_symbols == []
        assert config.max_position_size == 0.10
        assert config.max_daily_loss == 1000.0
        assert config.min_confidence == 0.3

    def test_orchestrator_config_custom(self):
        config = OrchestratorConfig(
            paper_trading=False,
            ai_provider="openai",
            allowed_symbols=["NIFTY"],
            max_position_size=0.05,
            max_daily_loss=500.0,
            min_confidence=0.5,
        )
        assert config.paper_trading is False
        assert config.ai_provider == "openai"
        assert config.allowed_symbols == ["NIFTY"]
        assert config.max_position_size == 0.05
        assert config.max_daily_loss == 500.0
        assert config.min_confidence == 0.5

    def test_orchestrator_config_to_context_dict(self):
        config = OrchestratorConfig(
            max_position_size=0.10,
            max_daily_loss=1000.0,
            max_weekly_loss=5000.0,
            min_confidence=0.3,
            allowed_symbols=["NIFTY"],
        )
        context = config.to_context_dict()
        assert context["max_position_size"] == 0.10
        assert context["max_daily_loss"] == 1000.0
        assert context["max_weekly_loss"] == 5000.0
        assert context["min_confidence"] == 0.3
        assert context["allowed_symbols"] == ["NIFTY"]
        assert "current_time" in context
        assert "equity" in context


class TestOrchestrator:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def teardown_method(self):
        self.temp_dir.cleanup()

    def make_orchestrator(self, **kwargs):
        """Create an orchestrator with proper config for testing.

        Separates config kwargs from research_ai and broker kwargs.
        """
        # Extract research_ai and broker kwargs
        research_kwargs = kwargs.pop("research_kwargs", {})
        broker_kwargs = kwargs.pop("broker_kwargs", {})

        # Create config with remaining kwargs
        config = OrchestratorConfig(**kwargs)

        # Create components
        research_ai = StaticResearchAI(**research_kwargs)
        broker = FakeKiteAdapter(**broker_kwargs)

        return Orchestrator(
            config,
            research_ai=research_ai,
            kite_adapter=broker,
        )

    def test_run_cycle_success(self):
        # Need to provide allowed_symbols and current_time within market hours
        orchestrator = self.make_orchestrator(
            allowed_symbols=["NIFTY"],
            max_daily_loss=10000.0,  # High limit to pass loss check
        )
        # Use a time within market hours (10:00 IST)
        context = {
            "symbol": "NIFTY",
            "timeframe": "1d",
            "current_time": datetime(2026, 11, 6, 10, 0, tzinfo=IST),
        }
        result = orchestrator.run_cycle(MARKET_BARS, "Test news", context)

        assert result["step7_success"] is True
        assert "step1_snapshot" in result
        assert "step2_regime_flags" in result
        assert "step2_event_alerts" in result
        assert "step3_decision_proposal" in result
        assert "step4_risk_verdict" in result
        assert "step5_order_details" in result
        assert "step6_journal_entry" in result
        assert result["step4_risk_verdict"].approved is True

    def test_run_cycle_snapshot_creation(self):
        orchestrator = self.make_orchestrator()
        result = orchestrator.run_cycle(MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"})

        snapshot = result["step1_snapshot"]
        assert isinstance(snapshot, StateSnapshot)
        assert snapshot.symbol == "NIFTY"
        assert snapshot.timeframe == "1d"
        assert "rsi" in snapshot.indicators
        # The actual indicators are ema_fast and ema_slow, not ema_20
        assert "ema_fast" in snapshot.indicators
        assert "ema_slow" in snapshot.indicators

    def test_run_cycle_research_analysis(self):
        orchestrator = self.make_orchestrator(research_kwargs={"regime_flags": ["trending_up", "low_volatility"]})
        result = orchestrator.run_cycle(MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"})

        assert "trending_up" in result["step2_regime_flags"]
        assert "low_volatility" in result["step2_regime_flags"]

    def test_run_cycle_decision_proposal(self):
        orchestrator = self.make_orchestrator()
        result = orchestrator.run_cycle(MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"})

        proposal = result["step3_decision_proposal"]
        assert isinstance(proposal, DecisionProposal)
        assert proposal.action in ["BUY", "SELL", "HOLD"]
        assert 0 <= proposal.confidence <= 1
        assert proposal.rationale is not None

    def test_run_cycle_risk_verdict(self):
        orchestrator = self.make_orchestrator(
            allowed_symbols=["NIFTY"],
            max_daily_loss=10000.0,
        )
        context = {
            "symbol": "NIFTY",
            "timeframe": "1d",
            "current_time": datetime(2026, 11, 6, 10, 0, tzinfo=IST),
        }
        result = orchestrator.run_cycle(MARKET_BARS, "", context)

        verdict = result["step4_risk_verdict"]
        assert isinstance(verdict, RiskVerdict)
        # The checks are size_ok, loss_ok, hours_ok, symbol_ok, confidence_ok
        assert all(k in verdict.checks for k in ["size_ok", "loss_ok", "hours_ok", "symbol_ok", "confidence_ok"])

    def test_run_cycle_order_placement(self):
        orchestrator = self.make_orchestrator(
            allowed_symbols=["NIFTY"],
            max_daily_loss=10000.0,
        )
        context = {
            "symbol": "NIFTY",
            "timeframe": "1d",
            "current_time": datetime(2026, 11, 6, 10, 0, tzinfo=IST),
        }
        result = orchestrator.run_cycle(MARKET_BARS, "", context)

        assert result["step5_order_details"] is not None
        assert result["step5_order_details"]["order_id"] == "paper-1"

    def test_run_cycle_journal_entry(self):
        orchestrator = self.make_orchestrator(
            allowed_symbols=["NIFTY"],
            max_daily_loss=10000.0,
        )
        context = {
            "symbol": "NIFTY",
            "timeframe": "1d",
            "current_time": datetime(2026, 11, 6, 10, 0, tzinfo=IST),
        }
        result = orchestrator.run_cycle(MARKET_BARS, "", context)

        journal_entry = result["step6_journal_entry"]
        assert journal_entry["status"] == "completed"
        assert journal_entry["step"] == "approved_trade"
        # With Two-AI journal protocol, we now have individual entry IDs
        assert "regime_entry_id" in journal_entry
        assert "proposal_entry_id" in journal_entry
        assert "timestamp_ist" in journal_entry

    def test_run_cycle_risk_rejection_symbol_not_allowed(self):
        orchestrator = self.make_orchestrator(allowed_symbols=["BANKNIFTY"])
        result = orchestrator.run_cycle(MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"})

        assert result["step7_success"] is True
        assert result["step4_risk_verdict"].approved is False
        assert result["step4_risk_verdict"].checks["symbol_ok"] is False
        assert result["step6_journal_entry"]["status"] == "rejected"
        assert result["step6_journal_entry"]["step"] == "risk_rejection"

    def test_run_cycle_risk_rejection_confidence_too_low(self):
        orchestrator = self.make_orchestrator(
            research_kwargs={"regime_flags": ["ranging"]},  # Low confidence regime
            min_confidence=0.9,
            allowed_symbols=["NIFTY"],
            max_daily_loss=10000.0,
        )
        context = {
            "symbol": "NIFTY",
            "timeframe": "1d",
            "current_time": datetime(2026, 11, 6, 10, 0, tzinfo=IST),
        }
        result = orchestrator.run_cycle(MARKET_BARS, "", context)

        assert result["step4_risk_verdict"].approved is False
        assert result["step4_risk_verdict"].checks["confidence_ok"] is False

    def test_run_cycle_research_failure(self):
        orchestrator = self.make_orchestrator(
            research_kwargs={"fail": True},
            allowed_symbols=["NIFTY"],
            max_daily_loss=10000.0,
        )
        context = {
            "symbol": "NIFTY",
            "timeframe": "1d",
            "current_time": datetime(2026, 11, 6, 10, 0, tzinfo=IST),
        }
        result = orchestrator.run_cycle(MARKET_BARS, "", context)

        assert result["step7_success"] is False
        assert result["step7_error"] is not None
        assert "research unavailable" in result["step7_error"]

    def test_run_cycle_execution_failure(self):
        orchestrator = self.make_orchestrator(
            broker_kwargs={"fail": True},
            allowed_symbols=["NIFTY"],
            max_daily_loss=10000.0,
        )
        context = {
            "symbol": "NIFTY",
            "timeframe": "1d",
            "current_time": datetime(2026, 11, 6, 10, 0, tzinfo=IST),
        }
        result = orchestrator.run_cycle(MARKET_BARS, "", context)

        assert result["step7_success"] is False
        assert "broker unavailable" in result["step7_error"]
        assert result["step6_journal_entry"]["step"] == "execution_failure"

    def test_run_cycle_insufficient_bars(self):
        orchestrator = self.make_orchestrator()
        result = orchestrator.run_cycle([[1730428800000, 100.0, 102.0, 99.0, 101.0, 1500.0]], "", {"symbol": "NIFTY"})

        assert result["step7_success"] is False
        assert result["step7_error"] is not None

    def test_run_cycle_invalid_bars_format(self):
        orchestrator = self.make_orchestrator()
        result = orchestrator.run_cycle("invalid", "", {"symbol": "NIFTY"})

        assert result["step7_success"] is False

    def test_run_cycle_paper_trading_true(self):
        config = OrchestratorConfig(paper_trading=True, allowed_symbols=["NIFTY"], max_daily_loss=10000.0)
        orchestrator = Orchestrator(config, research_ai=StaticResearchAI(), kite_adapter=FakeKiteAdapter())
        context = {
            "symbol": "NIFTY",
            "timeframe": "1d",
            "current_time": datetime(2026, 11, 6, 10, 0, tzinfo=IST),
        }
        result = orchestrator.run_cycle(MARKET_BARS, "", context)

        assert result["step5_order_details"]["order_id"] == "paper-1"

    def test_run_cycle_with_news_context(self):
        orchestrator = self.make_orchestrator(
            allowed_symbols=["NIFTY"],
            max_daily_loss=10000.0,
        )
        context = {
            "symbol": "NIFTY",
            "timeframe": "1d",
            "current_time": datetime(2026, 11, 6, 10, 0, tzinfo=IST),
        }
        result = orchestrator.run_cycle(MARKET_BARS, "RBI policy meeting today", context)

        assert result["step7_success"] is True

    def test_run_cycle_with_context_dict(self):
        orchestrator = self.make_orchestrator(
            allowed_symbols=["NIFTY"],
            max_daily_loss=10000.0,
        )
        context = {
            "symbol": "NIFTY",
            "timeframe": "1d",
            "current_time": datetime(2026, 11, 6, 10, 0, tzinfo=IST),
            "custom_field": "test",
        }
        result = orchestrator.run_cycle(MARKET_BARS, "", context)

        assert result["step7_success"] is True

    def test_orchestrator_initialization(self):
        config = OrchestratorConfig(paper_trading=True, ai_provider="rule_based")
        orchestrator = Orchestrator(config)
        assert orchestrator.config.paper_trading is True
        assert orchestrator.config.ai_provider == "rule_based"
        assert isinstance(orchestrator.research_ai, ConfigDrivenResearchAI)
        assert isinstance(orchestrator.kite_adapter, KiteAdapter)
        assert orchestrator.kite_adapter.paper_trading is True

    def test_orchestrator_with_custom_components(self):
        custom_research = StaticResearchAI(regime_flags=["custom_regime"])
        custom_kite = FakeKiteAdapter()
        config = OrchestratorConfig()
        orchestrator = Orchestrator(config, research_ai=custom_research, kite_adapter=custom_kite)
        assert orchestrator.research_ai is custom_research
        assert orchestrator.kite_adapter is custom_kite
