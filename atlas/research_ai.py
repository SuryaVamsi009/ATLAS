"""ResearchAI module for the ATLAS architecture (L3 - Analysis & Signal Generation).

This module implements the Research AI component that analyzes market data
and news context to produce regime flags and event alerts. It does NOT
place orders - its output is purely informational and feeds into the
DecisionProposal generation via the orchestrator.

The Research AI is model-agnostic and config-driven, supporting multiple
AI providers through a common interface. It communicates only through
structured data (StateSnapshot, DecisionProposal, RiskVerdict, RAGCorpus).
"""

from __future__ import annotations

import abc
from datetime import datetime
from typing import Any, Dict, List, Optional


class ResearchAI(abc.ABC):
    """Abstract base class for Research AI implementations.

    The Research AI analyzes market data and news context to produce:
    - Regime flags (e.g., "trending_up", "choppy", "reversal")
    - Event alerts (e.g., "breakout", "earnings_announcement")

    Crucially, the Research AI does NOT place orders. Its output is purely
    informational and feeds into the DecisionProposal generation through
    the orchestrator's Two-AI architecture.

    Subclasses must implement the `analyze` method to produce regime flags
    and event alerts from market data and news context, potentially using
    a RAGCorpus for retrieval-augmented generation.

    The output is a dict with two keys:
    - "regime_flags": List of regime flag strings
    - "event_alerts": List of event alert strings
    """

    @abc.abstractmethod
    def analyze(
        self,
        snapshot: Any,  # StateSnapshot
        news_context: str,
        rag_corpus: Any,  # RAGCorpus
        context_dict: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        """Analyze market data and news to produce regime flags and event alerts.

        Args:
            snapshot: The StateSnapshot containing current market state.
            news_context: String summarizing recent news context.
            rag_corpus: RAGCorpus instance for retrieval-augmented generation.
            context_dict: Additional context dict from the orchestrator.

        Returns:
            Dict with keys:
            - "regime_flags": List of regime flag strings (e.g., ["trending_up"])
            - "event_alerts": List of event alert strings (e.g., ["breakout"])
        """
        raise NotImplementedError


class ConfigDrivenResearchAI(ResearchAI):
    """Research AI implementation driven by configuration.

    This implementation is model-agnostic and config-driven. It uses:
    1. Indicator-based regime detection from the StateSnapshot
    2. RAGCorpus retrieval for pattern matching
    3. Simple rule-based event detection from market features
    4. Configurable AI provider settings (placeholder for LLM integration)

    The design allows swapping the underlying AI provider (OpenAI, Anthropic,
    Gemini, etc.) without changing the core logic - only the provider-specific
    configuration changes.
    """

    def __init__(
        self,
        min_confidence: float = 0.3,
        ai_provider: str = "rule_based",
        model_name: str = "rule-based",
        rag_weight: float = 0.5,
    ) -> None:
        """Initialize the config-driven Research AI.

        Args:
            min_confidence: Minimum confidence threshold for flag generation.
            ai_provider: Name of the AI provider (for config compatibility).
            model_name: Name of the specific model/config to use.
            rag_weight: Weight given to RAG corpus results vs. pure rule-based
                analysis (0.0 = pure rules, 1.0 = pure RAG).
        """
        self.min_confidence = min_confidence
        self.ai_provider = ai_provider
        self.model_name = model_name
        self.rag_weight = rag_weight

    def analyze(
        self,
        snapshot: Any,  # StateSnapshot
        news_context: str,
        rag_corpus: Any,  # RAGCorpus
        context_dict: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        """Analyze market data and news to produce regime flags and event alerts.

        This rule-based implementation examines the StateSnapshot's indicators
        and regime_features to determine market regime, and uses the RAG corpus
        for pattern matching. News context is also examined for keyword triggers.

        Args:
            snapshot: StateSnapshot with current market state.
            news_context: String summarizing recent news.
            rag_corpus: RAGCorpus for pattern retrieval.
            context_dict: Additional context from orchestrator.

        Returns:
            Dict with "regime_flags" and "event_alerts" lists.
        """
        regime_flags: List[str] = []
        event_alerts: List[str] = []

        # --- Regime flag detection from StateSnapshot indicators ---
        indicators = getattr(snapshot, "indicators", {})
        regime_features = getattr(snapshot, "regime_features", {})

        # RSI-based regime
        rsi = indicators.get("rsi", 50.0)
        if rsi > 70:
            regime_flags.append("overbought")
        elif rsi < 30:
            regime_flags.append("oversold")
        else:
            regime_flags.append("neutral")

        # Trend regime based on price change
        price_change = regime_features.get("trend_slope", 0.0)
        if price_change > 0.02:
            regime_flags.append("trending_up")
        elif price_change < -0.02:
            regime_flags.append("trending_down")
        else:
            regime_flags.append("choppy")

        # Volatility regime
        vol = regime_features.get("realised_vol", 0.0)
        if vol > 0.05:
            regime_flags.append("high_volatility")
        elif vol > 0.02:
            regime_flags.append("moderate_volatility")
        else:
            regime_flags.append("low_volatility")

        # --- RAG corpus pattern matching ---
        rag_patterns: List[str] = []
        if rag_corpus is not None:
            # Check for patterns matching the current regime
            for regime_name in regime_flags:
                pattern_info = rag_corpus.get_regime_profile(regime_name)
                if pattern_info is not None:
                    rag_patterns.append(f"rag_{regime_name}")

        # Combine rule-based and RAG results
        # Weighted approach: higher rag_weight gives more influence to RAG
        if self.rag_weight > 0.5 and rag_patterns:
            # RAG has more influence - use RAG patterns as primary
            regime_flags = rag_patterns[:2]  # Take top 2 RAG patterns
            # Keep at least one rule-based flag for balance
            if not any("rule_" in f for f in regime_flags):
                regime_flags.append("rule_based")

        # --- Event alert detection ---
        # Keyword-based news event detection
        news_lower = news_context.lower() if news_context else ""
        if "earnings" in news_lower or "report" in news_lower:
            event_alerts.append("earnings_announcement")
        if "breakout" in news_lower or "surge" in news_lower:
            event_alerts.append("breakout")
        if "fed" in news_lower or "interest rate" in news_lower:
            event_alerts.append("policy_change")
        if "crash" in news_lower or "drop" in news_lower or "plunge" in news_lower:
            event_alerts.append("market_decline")

        # RAG-based event templates
        if rag_corpus is not None:
            for event_type, template_info in rag_corpus.event_templates.items():
                conditions = template_info.get("conditions", {})
                # Simple condition check - in production would be more sophisticated
                if all(
                    cond.lower() in news_lower for cond in conditions.get("keywords", [])
                ):
                    event_alerts.append(f"rag_{event_type}")

        # Deduplicate alerts
        event_alerts = list(dict.fromkeys(event_alerts))

        return {
            "regime_flags": regime_flags,
            "event_alerts": event_alerts,
        }