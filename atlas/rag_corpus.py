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

    # --- Pre-seeded Indian market regime profiles ---

    def _init_indian_regimes(self) -> None:
        """Initialize regime profiles for Indian market conditions."""
        if self.regimes:
            return  # Already initialized

        # Trending up: Nifty above 50-DMA, sustained buying
        self.add_regime(
            name="trending_up",
            description="Sustained upward trend with Nifty above 50-DMA and FII buying",
            feature_profile={
                "trend_slope": 0.03,      # > 3% weekly slope
                "rsi": 55.0,              # Moderate RSI, room to run
                "realised_vol": 0.025,    # 2.5% weekly vol
                "fii_net_flows": 500.0,   # Net FII buying in crores
                "dii_net_flows": -100.0,  # Slight DII selling
            },
            typical_behavior="Nifty gradually grinds higher; select individual stock strength; banks and IT lead; volatility contained",
        )

        # Choppy/range-bound: Nifty between 20-DMA and 50-DMA, low volume
        self.add_regime(
            name="choppy",
            description="Range-bound market with Nifty between 20-DMA and 50-DMA",
            feature_profile={
                "trend_slope": 0.005,     # Near-zero slope
                "rsi": 48.0,              # Neutral RSI
                "realised_vol": 0.018,    # 1.8% weekly vol (low)
                "fii_net_flows": -200.0,  # Net FII selling
                "dii_net_flows": 200.0,   # DII buying offsets
            },
            typical_behavior="Nifty oscillates between pivot levels; high concentration names trade; volume below average; avoid new positions",
        )

        # Reversal: Nifty below 20-DMA after prior uptrend, bearish breadth
        self.add_regime(
            name="reversal",
            description="Trend reversal in progress - Nifty breaking below 20-DMA",
            feature_profile={
                "trend_slope": -0.04,     # -4% weekly slope
                "rsi": 35.0,              # Oversold but weakening
                "realised_vol": 0.045,    # 4.5% weekly vol (spiking)
                "fii_net_flows": -500.0,  # Strong FII selling
                "dii_net_flows": -100.0,  # DII also selling
            },
            typical_behavior="Nifty decline accelerates; broad selling; stop-losses triggered; wait for confirmation before new positions",
        )

        # Breakout: Nifty above recent highs with volume expansion
        self.add_regime(
            name="breakout",
            description="Price breakout above resistance with volume expansion",
            feature_profile={
                "trend_slope": 0.05,      # > 5% weekly slope
                "rsi": 65.0,              # RSI expanding from neutral
                "realised_vol": 0.060,    # 6% weekly vol (elevated)
                "fii_net_flows": 200.0,   # Modest FII buying
                "dii_net_flows": 100.0,   # DII buying
                "volume_ratio": 1.5,      # 1.5x average volume
            },
            typical_behavior="Nifty rallies above key resistance (23,500); follow-through in IT/Pharma; watch for fakeouts on low volume",
        )

        # High volatility (crude-driven, FII panic)
        self.add_regime(
            name="high_vol_panic",
            description="Elevated volatility from crude/FII sentiment shock",
            feature_profile={
                "trend_slope": 0.01,      # Mixed trend
                "rsi": 42.0,              # Weak RSI
                "realised_vol": 0.080,    # 8% weekly vol (very high)
                "fii_net_flows": -800.0,  # Heavy FII selling
                "dii_net_flows": 100.0,   # Limited DII support
            },
            typical_behavior="Wide daily swings; avoid discretionary entries; focus on high-liquidity names only; protect capital",
        )

        # Mean-reversion after oversold
        self.add_regime(
            name="mean_reversion_oversold",
            description="Oversold condition awaiting mean reversion bounce",
            feature_profile={
                "trend_slope": -0.01,     # Slight negative slope
                "rsi": 25.0,              # Deeply oversold
                "realised_vol": 0.035,   # 3.5% weekly vol
                "fii_net_flows": -100.0,  # Moderate FII selling
                "dii_net_flows": 300.0,   # DII strong support
            },
            typical_behavior="Nifty bottoms and bounces 2-4% on technical oversold; quality names lead; good for short-term trades with tight stops",
        )

        # Sector rotation: IT leading, financials lagging
        self.add_regime(
            name="sector_rotation_it_leading",
            description="IT sector leading market, financials lagging",
            feature_profile={
                "trend_slope": 0.02,      # 2% weekly slope
                "rsi": 58.0,              # RSI healthy but not extreme
                "realised_vol": 0.022,   # 2.2% weekly vol
                "fii_net_flows": 100.0,   # FII rotating into IT
                "dii_net_flows": 200.0,   # DII supporting IT
                "it_sector_return": 0.03, # IT +3% weekly
                "financial_sector_return": -0.01,  # Financials -1% weekly
            },
            typical_behavior="IT stocks outperform; select on Q2 AI revenue beats; banks selected individually on Q2 beats, not index momentum",
        )

        # Earnings-driven volatility
        self.add_regime(
            name="earnings_volatility",
            description="Individual stock volatility from Q2 earnings results",
            feature_profile={
                "trend_slope": 0.00,      # Market flat, stock-specific moves
                "rsi": 45.0,              # Neutral per-stock
                "realised_vol": 0.070,   # 7% weekly vol (stock-specific)
                "fii_net_flows": 0.0,     # Neutral aggregate
                "dii_net_flows": 0.0,     # Neutral aggregate
            },
            typical_behavior="Earnings season: 20-30% moves per stock on beat/miss; use Journal lessons for past calls; avoid broad market calls",
        )

    # --- Pre-seeded Indian market patterns ---

    def _init_indian_patterns(self) -> None:
        """Initialize market pattern descriptions for Indian equities."""
        if self.patterns:
            return  # Already initialized

        # Breakout RSI 70 - typical overbought breakout
        self.add_pattern(
            name="breakout_rsi70",
            description="Price breaks above resistance with RSI > 70, overbought but momentum strong",
            key_features={
                "rsi": 75.0,
                "price_vs_52w_high": 0.95,  # Near 52-week high
                "volume_ratio": 1.8,        # 1.8x average volume
            },
            typical_actions=["BUY", "HOLD"],
        )

        # Mean reversion from oversold RSI 30
        self.add_pattern(
            name="mean_reversion_oversold_rsi30",
            description="Price oversold with RSI < 30, mean reversion bounce expected",
            key_features={
                "rsi": 25.0,
                "price_vs_52w_low": 0.85,   # Near 52-week low
                "volume_ratio": 1.2,        # Slightly above average volume
            },
            typical_actions=["BUY", "HOLD"],
        )

        # Double bottom - reversal pattern
        self.add_pattern(
            name="double_bottom",
            description="Classic double bottom reversal pattern after sustained decline",
            key_features={
                "price_retrace": 0.03,      # 3% retrace from low
                "volume_confirmation": True, # Volume higher on second bottom
                "rsi_divergence": True,     # RSI higher low vs price lower low
            },
            typical_actions=["BUY", "HOLD"],
        )

        # Top formation - distribution pattern
        self.add_pattern(
            name="top_formation",
            description="Distribution top formation after sustained advance",
            key_features={
                "price_vs_50_dma": -0.02,   # Below 50-DMA
                "rsi": 62.0,                # Rising but overbought
                "volume_divergence": True,  # Price higher on lower volume
            },
            typical_actions=["SELL", "HOLD"],
        )

        # Earnings beat - positive catalyst
        self.add_pattern(
            name="earnings_beat",
            description="Q2 earnings beat with positive guidance, typical 10-15% immediate move",
            key_features={
                "eps_beat": True,
                "revenue_beat": True,
                "guidance_raised": True,
            },
            typical_actions=["BUY", "HOLD"],
        )

        # Earnings miss - negative catalyst
        self.add_pattern(
            name="earnings_miss",
            description="Q2 earnings miss with negative guidance, typical 8-12% immediate decline",
            key_features={
                "eps_miss": True,
                "revenue_miss": True,
                "guidance_lowered": True,
            },
            typical_actions=["SELL", "HOLD"],
        )

        # FII buying surge - macro catalyst
        self.add_pattern(
            name="fii_buying_surge",
            description="Net FII buying surge > ₹500cr, broad market support",
            key_features={
                "fii_net_flows": 500.0,     # Net FII buying in crores
                "fii_futures_oi_change": 0.1, # 10% increase in index futures OI
            },
            typical_actions=["BUY", "HOLD"],
        )

        # FII selling pressure - macro catalyst
        self.add_pattern(
            name="fii_selling_pressure",
            description="Net FII selling pressure > ₹500cr, broad market headwind",
            key_features={
                "fii_net_flows": -500.0,    # Net FII selling in crores
                "fii_futures_oi_change": -0.1, # 10% decrease in index futures OI
            },
            typical_actions=["SELL", "HOLD"],
        )

        # Bank Nifty weak - sector selection needed
        self.add_pattern(
            name="banknifty_weak",
            description="Bank Nifty below MAs, financials need individual strength",
            key_features={
                "banknifty_vs_20dma": -0.03,  # -3% below 20-DMA
                "banknifty_vs_50dma": -0.05,  # -5% below 50-DMA
            },
            typical_actions=["SELECT_INDIVIDUAL", "AVOID_BANK_INDEX"],
        )

        # IT sector strength
        self.add_pattern(
            name="it_sector_strength",
            description="IT sector leading on AI revenue deals and digital transformation",
            key_features={
                "it_deal_tcv": 5000.0,      # Total contract value in $Mn
                "ai_revenue_growth": 0.25,  # 25% QoQ AI revenue growth
            },
            typical_actions=["BUY_IT", "HOLD"],
        )

    # --- Initialization on first use ---

    def ensure_initialized(self) -> None:
        """Ensure the corpus has Indian market regimes and patterns pre-seeded."""
        self._init_indian_regimes()
        self._init_indian_patterns()

    # --- Regime methods (unchanged) ---

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