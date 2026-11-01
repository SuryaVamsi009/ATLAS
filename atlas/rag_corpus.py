"""RAGCorpus module for the ATLAS architecture (L2 - Data Ingestion & Context).

This module implements a Retrieval-Augmented Generation corpus that stores
market knowledge, patterns, and reference examples used by the Research AI
to enrich its analysis with historical context and proven patterns.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class RAGCorpus:
    """Retrieval-Augmented Generation corpus for ATLAS market analysis.

    The RAGCorpus stores market patterns, regime descriptions, and event
    templates that the Research AI can query to enrich its analysis with
    historical context and proven patterns. Communication between layers
    occurs only through structured data (StateSnapshot, DecisionProposal,
    RiskVerdict) - the RAG corpus is read-only from the orchestrator's
    perspective.

    Attributes:
        patterns: Dict mapping pattern names to pattern descriptions and
            characteristics.
        regimes: Dict mapping regime names to regime feature profiles.
        event_templates: Dict mapping event types to template descriptions.
        examples: List of example StateSnapshot -> DecisionProposal mappings.
    """

    def __init__(self) -> None:
        self.patterns: Dict[str, Dict[str, Any]] = {}
        self.regimes: Dict[str, Dict[str, Any]] = {}
        self.event_templates: Dict[str, Dict[str, Any]] = {}
        self.examples: List[Dict[str, Any]] = []

    def add_pattern(
        self,
        name: str,
        description: str,
        key_features: Dict[str, Any],
        typical_actions: List[str],
    ) -> None:
        """Add a market pattern to the corpus.

        Args:
            name: Unique pattern identifier (e.g., "breakout_rsi70", "double_bottom").
            description: Human-readable description of the pattern.
            key_features: Dict of indicator values or features that characterize
                the pattern.
            typical_actions: List of typical action strings ("BUY", "SELL", "HOLD")
                associated with this pattern.
        """
        self.patterns[name] = {
            "description": description,
            "key_features": key_features,
            "typical_actions": typical_actions,
        }

    def add_regime(
        self,
        name: str,
        description: str,
        feature_profile: Dict[str, float],
        typical_behavior: str,
    ) -> None:
        """Add a regime profile to the corpus.

        Args:
            name: Unique regime identifier (e.g., "trending_up", "choppy", "reversal").
            description: Human-readable description of the regime.
            feature_profile: Dict of regime feature names to typical values.
            typical_behavior: Description of typical market behavior in this regime.
        """
        self.regimes[name] = {
            "description": description,
            "feature_profile": feature_profile,
            "typical_behavior": typical_behavior,
        }

    def add_event_template(
        self,
        event_type: str,
        template: str,
        conditions: Dict[str, Any],
    ) -> None:
        """Add an event alert template to the corpus.

        Args:
            event_type: Type of event (e.g., "regime_change", "breakout", "earnings_announcement").
            template: Template string for the event alert message.
            conditions: Dict of conditions that trigger this event.
        """
        self.event_templates[event_type] = {
            "template": template,
            "conditions": conditions,
        }

    def add_example(
        self,
        snapshot_id: str,
        decision: DecisionProposal,
        outcome: str,
        rationale: str,
    ) -> None:
        """Add a decision example to the corpus.

        Args:
            snapshot_id: The StateSnapshot ID this example relates to.
            decision: The DecisionProposal that was made.
            outcome: The ground-truth outcome ("TARGET_HIT", "STOP_HIT", etc.).
            rationale: Rationale for the decision.
        """
        self.examples.append({
            "snapshot_id": snapshot_id,
            "decision": decision,
            "outcome": outcome,
            "rationale": rationale,
        })

    def get_pattern_for_regime(self, regime_name: str) -> Optional[Dict[str, Any]]:
        """Get pattern information for a given regime.

        Args:
            regime_name: Name of the regime to look up.

        Returns:
            Pattern dict if found, None otherwise.
        """
        return self.patterns.get(regime_name)

    def get_regime_profile(self, regime_name: str) -> Optional[Dict[str, Any]]:
        """Get regime feature profile.

        Args:
            regime_name: Name of the regime to look up.

        Returns:
            Regime profile dict if found, None otherwise.
        """
        return self.regimes.get(regime_name)

    def get_event_template(self, event_type: str) -> Optional[Dict[str, Any]]:
        """Get event alert template.

        Args:
            event_type: Type of event to look up.

        Returns:
            Event template dict if found, None otherwise.
        """
        return self.event_templates.get(event_type)

    def get_examples(self) -> List[Dict[str, Any]]:
        """Get all stored decision examples.

        Returns:
            List of example dicts with snapshot_id, decision, outcome, and rationale.
        """
        return self.examples