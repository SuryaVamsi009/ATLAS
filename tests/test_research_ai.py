"""Tests for atlas.research_ai module."""

from zoneinfo import ZoneInfo

import pytest

from atlas.research_ai import ConfigDrivenResearchAI, ResearchAI
from atlas.state_snapshot import compute_from_bars

IST = ZoneInfo("Asia/Kolkata")


class MockRAGCorpus:
    """Mock RAG corpus for testing."""
    def get_regime_profile(self, regime_name):
        return {"description": "Test", "confidence": 0.8}

    @property
    def event_templates(self):
        return {}


class TestResearchAI:
    def test_research_ai_is_abstract(self):
        with pytest.raises(TypeError):
            ResearchAI()


class TestConfigDrivenResearchAI:
    def setup_method(self):
        self.research_ai = ConfigDrivenResearchAI(
            min_confidence=0.3,
            ai_provider="rule_based",
            model_name="rule-based",
            rag_weight=0.3,
        )
        bars = [
            [1730428800000, 19500.0, 19600.0, 19450.0, 19550.0, 1500000],
            [1730515200000, 19550.0, 19650.0, 19500.0, 19600.0, 1800000],
        ]
        self.snapshot = compute_from_bars("NIFTY", "1d", bars)

    def test_config_driven_research_ai_creation(self):
        assert self.research_ai.min_confidence == 0.3
        assert self.research_ai.ai_provider == "rule_based"
        assert self.research_ai.model_name == "rule-based"
        assert self.research_ai.rag_weight == 0.3

    def test_analyze_returns_dict(self):
        result = self.research_ai.analyze(
            snapshot=self.snapshot,
            news_context="Market trending up",
            rag_corpus=MockRAGCorpus(),
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        assert isinstance(result, dict)
        assert "regime_flags" in result
        assert "event_alerts" in result
        assert isinstance(result["regime_flags"], list)
        assert isinstance(result["event_alerts"], list)

    def test_analyze_with_trending_up(self):
        # Strong uptrend: price increases ~2% per day
        bars = [
            [1730428800000, 19500.0, 19600.0, 19450.0, 19550.0, 1500000],
            [1730515200000, 19900.0, 20000.0, 19850.0, 19950.0, 1800000],
            [1730601600000, 20300.0, 20400.0, 20250.0, 20350.0, 2000000],
            [1730688000000, 20700.0, 20800.0, 20650.0, 20750.0, 2200000],
            [1730774400000, 21100.0, 21200.0, 21050.0, 21150.0, 2500000],
        ]
        snapshot = compute_from_bars("NIFTY", "1d", bars)
        result = self.research_ai.analyze(
            snapshot=snapshot,
            news_context="",
            rag_corpus=MockRAGCorpus(),
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        assert "trending_up" in result["regime_flags"]

    def test_analyze_with_trending_down(self):
        # Strong downtrend: price decreases ~2% per day
        bars = [
            [1730428800000, 21150.0, 21200.0, 21100.0, 21150.0, 1500000],
            [1730515200000, 20750.0, 20800.0, 20700.0, 20750.0, 1800000],
            [1730601600000, 20350.0, 20400.0, 20300.0, 20350.0, 2000000],
            [1730688000000, 19950.0, 20000.0, 19900.0, 19950.0, 2200000],
            [1730774400000, 19550.0, 19600.0, 19500.0, 19550.0, 2500000],
        ]
        snapshot = compute_from_bars("NIFTY", "1d", bars)
        result = self.research_ai.analyze(
            snapshot=snapshot,
            news_context="",
            rag_corpus=MockRAGCorpus(),
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        assert "trending_down" in result["regime_flags"]

    def test_analyze_with_choppy(self):
        # Sideways/choppy market
        bars = [
            [1730428800000, 19500.0, 19600.0, 19450.0, 19550.0, 1500000],
            [1730515200000, 19550.0, 19650.0, 19500.0, 19600.0, 1800000],
            [1730601600000, 19600.0, 19700.0, 19550.0, 19650.0, 2000000],
            [1730688000000, 19650.0, 19750.0, 19600.0, 19700.0, 2200000],
            [1730774400000, 19700.0, 19800.0, 19650.0, 19750.0, 2500000],
        ]
        snapshot = compute_from_bars("NIFTY", "1d", bars)
        result = self.research_ai.analyze(
            snapshot=snapshot,
            news_context="",
            rag_corpus=MockRAGCorpus(),
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        assert "choppy" in result["regime_flags"]

    def test_analyze_with_high_volatility(self):
        bars = [
            [1730428800000, 19500.0, 19600.0, 19450.0, 19550.0, 1500000],
            [1730515200000, 19550.0, 19650.0, 19500.0, 19600.0, 1800000],
        ]
        snapshot = compute_from_bars("NIFTY", "1d", bars)
        # Manually set high volatility
        snapshot.regime_features["realised_vol"] = 0.06
        result = self.research_ai.analyze(
            snapshot=snapshot,
            news_context="",
            rag_corpus=MockRAGCorpus(),
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        assert "high_volatility" in result["regime_flags"]

    def test_analyze_with_oversold(self):
        bars = [
            [1730428800000, 19500.0, 19600.0, 19450.0, 19550.0, 1500000],
            [1730515200000, 19550.0, 19650.0, 19500.0, 19600.0, 1800000],
        ]
        snapshot = compute_from_bars("NIFTY", "1d", bars)
        # Manually set RSI to oversold
        snapshot.indicators["rsi"] = 25.0
        result = self.research_ai.analyze(
            snapshot=snapshot,
            news_context="",
            rag_corpus=MockRAGCorpus(),
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        assert "oversold" in result["regime_flags"]

    def test_analyze_with_overbought(self):
        bars = [
            [1730428800000, 19500.0, 19600.0, 19450.0, 19550.0, 1500000],
            [1730515200000, 19550.0, 19650.0, 19500.0, 19600.0, 1800000],
        ]
        snapshot = compute_from_bars("NIFTY", "1d", bars)
        # Manually set RSI to overbought
        snapshot.indicators["rsi"] = 75.0
        result = self.research_ai.analyze(
            snapshot=snapshot,
            news_context="",
            rag_corpus=MockRAGCorpus(),
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        assert "overbought" in result["regime_flags"]

    def test_analyze_with_news_context(self):
        result = self.research_ai.analyze(
            snapshot=self.snapshot,
            news_context="RBI policy meeting today, expected rate cut",
            rag_corpus=MockRAGCorpus(),
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        # News context should be considered but not break the analysis
        assert "regime_flags" in result
        assert "event_alerts" in result

    def test_analyze_with_rag_corpus(self):
        rag_corpus = MockRAGCorpus()
        result = self.research_ai.analyze(
            snapshot=self.snapshot,
            news_context="",
            rag_corpus=rag_corpus,
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        assert "regime_flags" in result

    def test_analyze_event_alerts_from_news(self):
        result = self.research_ai.analyze(
            snapshot=self.snapshot,
            news_context="Earnings report shows strong growth",
            rag_corpus=MockRAGCorpus(),
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        assert "earnings_announcement" in result["event_alerts"]

    def test_analyze_event_alerts_breakout(self):
        result = self.research_ai.analyze(
            snapshot=self.snapshot,
            news_context="Market breakout to new highs",
            rag_corpus=MockRAGCorpus(),
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        assert "breakout" in result["event_alerts"]

    def test_analyze_event_alerts_policy_change(self):
        result = self.research_ai.analyze(
            snapshot=self.snapshot,
            news_context="Fed interest rate decision today",
            rag_corpus=MockRAGCorpus(),
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        assert "policy_change" in result["event_alerts"]

    def test_analyze_event_alerts_market_decline(self):
        result = self.research_ai.analyze(
            snapshot=self.snapshot,
            news_context="Market crashes on bad news",
            rag_corpus=MockRAGCorpus(),
            context_dict={"symbol": "NIFTY", "timeframe": "1d"},
        )
        assert "market_decline" in result["event_alerts"]
