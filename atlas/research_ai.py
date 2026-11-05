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
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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
    4. Configurable AI provider settings (OpenAI, Anthropic, Gemini, or rule_based)

    The design allows swapping the underlying AI provider (OpenAI, Anthropic,
    Gemini, etc.) without changing the core logic - only the provider-specific
    configuration changes. When provider is "rule_based", the implementation
    falls back to indicator-based regime detection and RAG corpus pattern matching.

    Supported providers:
    - "rule_based": Rule-based regime detection (default, for robustness)
    - "openai": OpenAI GPT models via API
    - "anthropic": Anthropic Claude models via API
    - "gemini": Google Gemini models via API
    """

    def __init__(
        self,
        min_confidence: float = 0.3,
        ai_provider: str = "rule_based",
        model_name: str = "rule-based",
        rag_weight: float = 0.3,  # Changed from 0.5 to 0.3 - rule-based dominant
    ) -> None:
        """Initialize the config-driven Research AI.

        Args:
            min_confidence: Minimum confidence threshold for flag generation.
            ai_provider: Name of the AI provider ("openai", "anthropic", "gemini", "rule_based").
            model_name: Name of the specific model/config to use.
            rag_weight: Weight given to RAG corpus results vs. pure rule-based
                analysis (0.0 = pure rules, 1.0 = pure RAG).
        """
        self.min_confidence = min_confidence
        self.ai_provider = ai_provider
        self.model_name = model_name
        self.rag_weight = rag_weight

        # Provider-specific configuration
        self.ai_provider_config = self._init_provider_config(ai_provider)

    def _init_provider_config(self, ai_provider: str) -> Dict[str, Any]:
        """Initialize provider-specific configuration.

        Args:
            ai_provider: Name of the AI provider.

        Returns:
            Dict with provider-specific configuration (API keys, model names, etc.).
        """
        config: Dict[str, Any] = {
            "api_key": None,
            "model": None,
            "endpoint": None,
        }

        if ai_provider == "openai":
            config["api_key"] = os.environ.get("OPENAI_API_KEY")
            config["model"] = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            config["endpoint"] = "https://api.openai.com/v1/chat/completions"
        elif ai_provider == "anthropic":
            config["api_key"] = os.environ.get("ANTHROPIC_API_KEY")
            config["model"] = os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
            config["endpoint"] = "https://api.anthropic.com/v1/messages"
        elif ai_provider == "gemini":
            config["api_key"] = os.environ.get("GEMINI_API_KEY")
            config["model"] = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
            config["endpoint"] = "https://generativelanguage.googleapis.com/v1beta/models:generateContent"
        # "rule_based" keeps default None config, falls back to rule-based logic

        return config

    def analyze(
        self,
        snapshot: Any,  # StateSnapshot
        news_context: str,
        rag_corpus: Any,  # RAGCorpus
        context_dict: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        """Analyze market data and news to produce regime flags and event alerts.

        This implementation follows a priority order:
        1. If ai_provider != "rule_based": attempt LLM provider generation
        2. Fall back to rule-based regime detection from StateSnapshot indicators
        3. Supplement with RAG corpus pattern matching (weighted by rag_weight)
        4. Keyword-based event alert detection from news context

        The output is always regime_flags and event_alerts lists, regardless of
        the underlying provider. The rule-based fallback ensures robustness when
        LLM calls fail or are not configured.

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

        # --- Step 1: Attempt LLM provider generation if configured ---
        if self.ai_provider != "rule_based" and self.ai_provider_config.get("api_key"):
            try:
                provider_regime, provider_thesis = self._call_provider_llm(
                    snapshot, news_context, rag_corpus
                )
                if provider_regime:
                    regime_flags = provider_regime
                    # Use thesis if available, otherwise generate from rules
                    if provider_thesis:
                        # Thesis is used for context but not returned directly
                        pass
                    logger.info(f"LLM provider {self.ai_provider} generated regime flags: {regime_flags}")
                else:
                    logger.warning("LLM provider returned no regime flags, falling back to rule-based")
            except Exception as e:
                logger.error(f"LLM provider {self.ai_provider} failed: {str(e)}, falling back to rule-based")
        else:
            logger.info(f"Using rule-based fallback (ai_provider={self.ai_provider})")

        # --- Step 2: Rule-based regime detection from StateSnapshot indicators ---
        # Always run rule-based detection as the foundation
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

        # --- Step 3: RAG corpus pattern matching (weighted by rag_weight) ---
        rag_patterns: List[str] = []
        if rag_corpus is not None:
            # Check for patterns matching the current regime
            for regime_name in regime_flags:
                pattern_info = rag_corpus.get_regime_profile(regime_name)
                if pattern_info is not None:
                    rag_patterns.append(f"rag_{regime_name}")

        # Combine rule-based and RAG results weighted by rag_weight
        # With rag_weight=0.3 (default), rule-based dominates; RAG is supplementary
        if self.rag_weight > 0.0 and rag_patterns:
            # Calculate how many RAG patterns to include based on weight
            num_rag = max(1, int(len(rag_patterns) * self.rag_weight))
            rag_selected = rag_patterns[:num_rag]

            # Add RAG patterns that aren't already rule-based
            rule_based_flags = [f for f in regime_flags if not f.startswith("rag_")]
            combined = rag_selected + rule_based_flags

            # Deduplicate while preserving order
            seen = set()
            regime_flags = [x for x in combined if not (x in seen or seen.add(x))]

        # --- Step 4: Event alert detection ---
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

    def _call_provider_llm(
        self,
        snapshot: Any,  # StateSnapshot
        news_context: str,
        rag_corpus: Any,  # RAGCorpus
    ) -> tuple[Optional[List[str]], Optional[str]]:
        """Call the configured LLM provider to generate regime flags and thesis.

        Args:
            snapshot: StateSnapshot with current market state.
            news_context: String summarizing recent news.
            rag_corpus: RAGCorpus for retrieval-augmented generation.

        Returns:
            Tuple of (regime_flags list, thesis string), or (None, None) if failed.
        """
        # TODO: Implement actual API calls to OpenAI/Anthropic/Gemini
        # For now, return None to maintain rule-based fallback
        return None, None