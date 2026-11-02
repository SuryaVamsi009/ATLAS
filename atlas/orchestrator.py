"""Orchestrator module for the ATLAS architecture - wires all 6 ATLAS layers together.

This module implements the Orchestrator class that runs one complete cycle:
data → analysis → decision → risk → execution → ledger

The orchestrator follows the Two-AI architecture:
- Research AI produces regime flags, event alerts (NO order placement)
- Agent AI (via DecisionProposal + RiskVerdict) decides on orders
- Communication only through ledger/structured data

Configuration is model-agnostic and config-driven.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from atlas.decision_proposal import DecisionProposal
from atlas.eval_set import Outcome
from atlas.risk_verdict import RiskVerdict, verify
from atlas.research_ai import ResearchAI, ConfigDrivenResearchAI
from atlas.rag_corpus import RAGCorpus
from atlas.state_snapshot import StateSnapshot, compute_from_bars
from atlas.brokers.kite_adapter import KiteAdapter, RateLimitError

# Configure logging
logger = logging.getLogger(__name__)


class OrchestratorConfig:
    """Configuration class for the Orchestrator.

    All values are config-driven and model-agnostic. Changing the AI provider
    or model only requires updating the config, not the orchestrator logic.
    """

    def __init__(
        self,
        min_confidence: float = 0.3,
        min_rr: float = 2.0,  # minimum reward-to-risk ratio
        max_position_size: float = 0.10,  # 10% of equity
        paper_trading: bool = True,
        ai_provider: str = "rule_based",
        model_name: str = "rule-based",
        max_daily_loss: float = 1000.0,
        max_weekly_loss: float = 5000.0,
        allowed_symbols: Optional[list] = None,
        min_reward_to_risk: float = 2.0,
        max_api_calls_per_cycle: int = 10,
        rate_limit_backoff_factor: float = 2.0,
        rate_limit_max_retries: int = 3,
    ) -> None:
        """Initialize orchestrator configuration.

        Args:
            min_confidence: Minimum confidence threshold for DecisionProposal (0.0-1.0).
            min_rr: Minimum reward-to-risk ratio required for a trade.
            max_position_size: Maximum position size as fraction of equity (e.g., 0.10 = 10%).
            paper_trading: If True, use paper trading mode; False for live trading.
            ai_provider: AI provider name (for config-driven model agnosticism).
            model_name: Specific model/config name.
            max_daily_loss: Maximum daily loss limit in currency units.
            max_weekly_loss: Maximum weekly loss limit in currency units.
            allowed_symbols: List of allowed trading symbols (e.g., ["BTC-USD", "ETH-USD"]).
            min_reward_to_risk: Alias for min_rd (reward-to-risk ratio).
            max_api_calls_per_cycle: Max API calls per cycle before backoff (default 10).
            rate_limit_backoff_factor: Exponential backoff factor (default 2.0).
            rate_limit_max_retries: Max retry attempts on 429 (default 3).
        """
        self.min_confidence = min_confidence
        self.min_rr = min_rr
        self.max_position_size = max_position_size
        self.paper_trading = paper_trading
        self.ai_provider = ai_provider
        self.model_name = model_name
        self.max_daily_loss = max_daily_loss
        self.max_weekly_loss = max_weekly_loss
        self.allowed_symbols = allowed_symbols or []
        self.min_reward_to_risk = min_reward_to_risk
        self.max_api_calls_per_cycle = max_api_calls_per_cycle
        self.rate_limit_backoff_factor = rate_limit_backoff_factor
        self.rate_limit_max_retries = rate_limit_max_retries

    def to_context_dict(self) -> Dict[str, Any]:
        """Convert config to a context dict for risk verification.

        Returns:
            Dict with risk context parameters.
        """
        return {
            "max_position_size": self.max_position_size,
            "max_daily_loss": self.max_daily_loss,
            "max_weekly_loss": self.max_weekly_loss,
            "min_confidence": self.min_confidence,
            "max_confidence": 0.9,
            "allowed_symbols": self.allowed_symbols,
            "current_time": datetime.now(),
            "equity": 10000.0,  # default; will be overridden from snapshot
        }


class Orchestrator:
    """Orchestrator that wires all 6 ATLAS layers together.

    Runs one complete cycle: data → analysis → decision → risk → execution → ledger

    Two-AI Architecture:
    - Research AI produces regime flags, event alerts (NO order placement)
    - Agent AI (via DecisionProposal + RiskVerdict) decides on orders
    - Communication only through ledger/structured data

    The orchestrator is model-agnostic and config-driven - changing the AI
    provider or model only requires updating the config, not the logic.
    """

    def __init__(
        self,
        config: OrchestratorConfig,
        research_ai: Optional[ResearchAI] = None,
        rag_corpus: Optional[RAGCorpus] = None,
        kite_adapter: Optional[KiteAdapter] = None,
    ) -> None:
        """Initialize the Orchestrator.

        Args:
            config: Orchestrator configuration.
            research_ai: ResearchAI instance (defaults to ConfigDrivenResearchAI).
            rag_corpus: RAGCorpus instance (defaults to empty corpus).
            kite_adapter: KiteAdapter instance (defaults to paper trading mode).
        """
        self.config = config
        self.research_ai = research_ai or ConfigDrivenResearchAI(
            min_confidence=config.min_confidence,
            ai_provider=config.ai_provider,
            model_name=config.model_name,
        )
        self.rag_corpus = rag_corpus or RAGCorpus()
        self.kite_adapter = kite_adapter or KiteAdapter(
            api_key="",
            access_token="",
            paper_trading=config.paper_trading,
        )

        # Journal (ledger) - stores completed cycle results
        self.journal: list[Dict[str, Any]] = []

        logger.info(
            f"Orchestrator initialized: paper_trading={config.paper_trading}, "
            f"ai_provider={config.ai_provider}, min_confidence={config.min_confidence}"
        )

    def run_cycle(
        self,
        market_data: list[list[float]],
        news_context: str,
        context_dict: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run one complete orchestration cycle.

        The complete cycle follows these steps:
        1. Compute StateSnapshot from market_data
        2. Research AI analyzes + RAG corpus → regime flags, event alerts
        3. DecisionProposal generated (action, confidence, size_hint, etc.)
        4. RiskVerdict checks → approved/final_qty/final_stop
        5. If approved, place order via KiteAdapter (paper trading)
        6. Update Journal with call details
        7. Return result dict with all step outputs

        Args:
            market_data: Raw market bars [[timestamp, open, high, low, close, volume], ...]
            news_context: String summarizing recent news context.
            context_dict: Additional context dict (symbol, timeframe, etc.)

        Returns:
            Dict with all step outputs:
            {
                "step1_snapshot": StateSnapshot or None,
                "step2_regime_flags": List[str],
                "step2_event_alerts": List[str],
                "step3_decision_proposal": DecisionProposal or None,
                "step4_risk_verdict": RiskVerdict or None,
                "step5_order_placed": bool,
                "step5_order_details": Dict or None,
                "step6_journal_entry": Dict or None,
                "step7_success": bool,
                "step7_error": str or None,
            }
        """
        result: Dict[str, Any] = {
            "step1_snapshot": None,
            "step2_regime_flags": [],
            "step2_event_alerts": [],
            "step3_decision_proposal": None,
            "step4_risk_verdict": None,
            "step5_order_placed": False,
            "step5_order_details": None,
            "step6_journal_entry": None,
            "step7_success": False,
            "step7_error": None,
        }

        # Rate limit tracking per cycle
        api_call_count = 0
        max_api_calls = self.config.max_api_calls_per_cycle

        try:
            # =========================================================================
            # Step 1: Compute StateSnapshot from market_data
            # =========================================================================
            logger.info("Step 1: Computing StateSnapshot from market_data")
            try:
                symbol = context_dict.get("symbol", "BTC-USD")
                timeframe = context_dict.get("timeframe", "1h")

                snapshot: StateSnapshot = compute_from_bars(
                    symbol=symbol,
                    timeframe=timeframe,
                    bars=market_data,
                )
                result["step1_snapshot"] = snapshot
                logger.info(f"Step 1 complete: snapshot_id={snapshot.snapshot_id}")
            except Exception as e:
                error_msg = f"Step 1 failed: {str(e)}"
                logger.error(error_msg)
                result["step7_error"] = error_msg
                result["step7_success"] = False
                return result

            # =========================================================================
            # Step 2: Research AI analyzes + RAG corpus → regime flags, event alerts
            # =========================================================================
            logger.info("Step 2: Research AI analysis")
            try:
                regime_flags, event_alerts = self._run_research_ai(
                    snapshot, news_context, context_dict
                )
                result["step2_regime_flags"] = regime_flags
                result["step2_event_alerts"] = event_alerts
                logger.info(
                    f"Step 2 complete: regime_flags={regime_flags}, "
                    f"event_alerts={event_alerts}"
                )
            except Exception as e:
                error_msg = f"Step 2 failed: {str(e)}"
                logger.error(error_msg)
                result["step7_error"] = error_msg
                result["step7_success"] = False
                return result

            # =========================================================================
            # Step 3: DecisionProposal generated (action, confidence, size_hint, etc.)
            # =========================================================================
            logger.info("Step 3: Generating DecisionProposal")
            try:
                decision_proposal = self._generate_decision_proposal(
                    snapshot, regime_flags, event_alerts, context_dict
                )
                result["step3_decision_proposal"] = decision_proposal
                logger.info(
                    f"Step 3 complete: action={decision_proposal.action}, "
                    f"confidence={decision_proposal.confidence:.2f}, "
                    f"size_hint={decision_proposal.size_hint:.2f}"
                )
            except Exception as e:
                error_msg = f"Step 3 failed: {str(e)}"
                logger.error(error_msg)
                result["step7_error"] = error_msg
                result["step7_success"] = False
                return result

            # =========================================================================
            # Step 4: RiskVerdict checks → approved/final_qty/final_stop
            # =========================================================================
            logger.info("Step 4: Risk verification")
            try:
                risk_context = self._build_risk_context(snapshot, decision_proposal)
                risk_verdict: RiskVerdict = verify(
                    proposal=decision_proposal,
                    snapshot=snapshot,
                    context=risk_context,
                )
                result["step4_risk_verdict"] = risk_verdict
                logger.info(
                    f"Step 4 complete: approved={risk_verdict.approved}, "
                    f"veto_reason={risk_verdict.veto_reason}, "
                    f"final_qty={risk_verdict.final_qty:.2f}"
                )
            except Exception as e:
                error_msg = f"Step 4 failed: {str(e)}"
                logger.error(error_msg)
                result["step7_error"] = error_msg
                result["step7_success"] = False
                return result

            # If not approved, skip execution and ledger update
            if not risk_verdict.approved:
                logger.info(
                    f"Trade rejected by risk: {risk_verdict.veto_reason}"
                )
                result["step6_journal_entry"] = {
                    "step": "risk_rejection",
                    "timestamp": datetime.utcnow().isoformat(),
                    "veto_reason": risk_verdict.veto_reason,
                    "decision_proposal": {
                        "action": decision_proposal.action,
                        "confidence": decision_proposal.confidence,
                        "size_hint": decision_proposal.size_hint,
                    },
                    "risk_verdict": {
                        "approved": risk_verdict.approved,
                        "veto_reason": risk_verdict.veto_reason,
                        "checks": risk_verdict.checks,
                    },
                }
                journal_entry = self._create_journal_entry(
                    snapshot=snapshot,
                    decision_proposal=decision_proposal,
                    risk_verdict=risk_verdict,
                    order_details={},
                    regime_flags=regime_flags,
                    event_alerts=event_alerts,
                    step="risk_rejection",
                )
                self.journal.append(journal_entry)
                result["step6_journal_entry"] = journal_entry
                result["step7_success"] = True
                result["step7_error"] = None
                return result

            # =========================================================================
            # Step 5: If approved, place order via KiteAdapter (paper trading)
            # =========================================================================
            logger.info("Step 5: Placing order via KiteAdapter")
            try:
                order_details = self._place_order(risk_verdict, snapshot, decision_proposal.action)
                result["step5_order_placed"] = True
                result["step5_order_details"] = order_details
                logger.info(
                    f"Step 5 complete: order placed, "
                    f"order_id={order_details.get('order_id', 'N/A')}"
                )
            except Exception as e:
                error_msg = f"Step 5 failed: {str(e)}"
                logger.error(error_msg)
                result["step7_error"] = error_msg
                result["step7_success"] = False
                return result

            # =========================================================================
            # Step 6: Update Journal with call details
            # =========================================================================
            logger.info("Step 6: Updating Journal")
            try:
                journal_entry = self._create_journal_entry(
                    snapshot=snapshot,
                    decision_proposal=decision_proposal,
                    risk_verdict=risk_verdict,
                    order_details=order_details,
                    regime_flags=regime_flags,
                    event_alerts=event_alerts,
                )
                self.journal.append(journal_entry)
                result["step6_journal_entry"] = journal_entry
                logger.info(f"Step 6 complete: journal entry added (id={len(self.journal)})")
            except Exception as e:
                error_msg = f"Step 6 failed: {str(e)}"
                logger.error(error_msg)
                # Step 6 failure doesn't prevent cycle success, but we log it
                result["step7_error"] = error_msg
                result["step7_success"] = False
                return result

            # =========================================================================
            # Step 7: Return result dict with all step outputs
            # =========================================================================
            logger.info("Step 7: Cycle complete - returning result")
            result["step7_success"] = True
            result["step7_error"] = None
            return result

        except Exception as e:
            # Final fallback - should not reach here if individual steps handle errors
            error_msg = f"Unexpected error in orchestrator cycle: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result["step7_error"] = error_msg
            result["step7_success"] = False
            return result

    # -------------------------------------------------------------------------
    # Internal helper methods
    # -------------------------------------------------------------------------

    def _run_research_ai(
        self,
        snapshot: StateSnapshot,
        news_context: str,
        context_dict: Dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        """Run the Research AI analysis and return regime flags and event alerts.

        Args:
            snapshot: StateSnapshot with current market state.
            news_context: String summarizing recent news.
            context_dict: Additional context from orchestrator.

        Returns:
            Tuple of (regime_flags, event_alerts).
        """
        result = self.research_ai.analyze(
            snapshot=snapshot,
            news_context=news_context,
            rag_corpus=self.rag_corpus,
            context_dict=context_dict,
        )
        return result["regime_flags"], result["event_alerts"]

    def _generate_decision_proposal(
        self,
        snapshot: StateSnapshot,
        regime_flags: list[str],
        event_alerts: list[str],
        context_dict: Dict[str, Any],
    ) -> DecisionProposal:
        """Generate a DecisionProposal based on Research AI output and market data.

        This is the "Agent AI" part of the Two-AI architecture. The Research AI
        produces regime flags and event alerts (no order placement), and the Agent
        AI generates a DecisionProposal based on those flags plus the market state.

        The DecisionProposal is generated using:
        - Regime flags from Research AI
        - Event alerts from Research AI
        - Market indicators from StateSnapshot
        - Config parameters (min_confidence, max_position_size, etc.)

        Args:
            snapshot: StateSnapshot with current market state.
            regime_flags: List of regime flag strings from Research AI.
            event_alerts: List of event alert strings from Research AI.
            context_dict: Additional context from orchestrator.

        Returns:
            DecisionProposal with action, confidence, size_hint, stop_hint, and rationale.
        """
        # Determine action from regime flags and event alerts
        action = "HOLD"
        confidence = 0.5
        size_hint = self.config.max_position_size * 0.5  # default 50% of max
        stop_hint = None
        rationale_parts: list[str] = []

        # --- Action determination from regime flags ---
        if "trending_up" in regime_flags:
            action = "BUY"
            confidence = 0.75
            size_hint = self.config.max_position_size * 0.8
            rationale_parts.append("trending_up regime")
            stop_hint = None  # will be set by risk checks
        elif "trending_down" in regime_flags:
            action = "SELL"
            confidence = 0.75
            size_hint = self.config.max_position_size * 0.8
            rationale_parts.append("trending_down regime")
            stop_hint = None
        elif "overbought" in regime_flags:
            action = "SELL"  # mean reversion
            confidence = 0.55
            size_hint = self.config.max_position_size * 0.5
            rationale_parts.append("overbought - mean reversion")
        elif "oversold" in regime_flags:
            action = "BUY"  # mean reversion
            confidence = 0.55
            size_hint = self.config.max_position_size * 0.5
            rationale_parts.append("oversold - mean reversion")

        # --- Event alert adjustments ---
        if "earnings_announcement" in event_alerts:
            # Reduce confidence around earnings - higher uncertainty
            confidence *= 0.8
            rationale_parts.append("earnings_announcement - reduced confidence")
        if "breakout" in event_alerts:
            if action == "BUY":
                confidence = min(1.0, confidence * 1.1)
            rationale_parts.append("breakout event")

        # --- Indicator-based adjustments ---
        indicators = getattr(snapshot, "indicators", {})
        rsi = indicators.get("rsi", 50.0)

        # Override action if RSI gives strong signal
        if rsi > 70 and action == "BUY":
            action = "SELL"
            rationale_parts.append("RSI overbought overrides regime")
            confidence = 0.6
        elif rsi < 30 and action == "SELL":
            action = "BUY"
            rationale_parts.append("RSI oversold overrides regime")
            confidence = 0.6

        # --- Size hint adjustment based on confidence ---
        size_hint = self.config.max_position_size * max(
            0.1, min(1.0, confidence)
        )  # clamp between 10% and max

        # --- Finalize rationale ---
        rationale = "; ".join(rationale_parts) if rationale_parts else "no specific rationale"

        # Ensure confidence is within [0.0, 1.0]
        confidence = max(0.0, min(1.0, confidence))

        # Create and return DecisionProposal
        proposal = DecisionProposal(
            action=action,
            confidence=confidence,
            size_hint=size_hint,
            stop_hint=stop_hint,
            rationale=rationale,
        )

        logger.debug(
            f"DecisionProposal generated: action={action}, "
            f"confidence={confidence:.2f}, size_hint={size_hint:.2f}, "
            f"rationale={rationale}"
        )

        return proposal

    def _build_risk_context(
        self, snapshot: StateSnapshot, decision_proposal: DecisionProposal
    ) -> Dict[str, Any]:
        """Build the risk verification context dict from config and snapshot.

        Args:
            snapshot: StateSnapshot with current market state.
            decision_proposal: DecisionProposal to verify.

        Returns:
            Dict with risk context parameters.
        """
        equity = snapshot.account.get("equity", 10000.0)

        context: Dict[str, Any] = {
            "max_position_size": self.config.max_position_size,
            "max_daily_loss": self.config.max_daily_loss,
            "max_weekly_loss": self.config.max_weekly_loss,
            "min_confidence": self.config.min_confidence,
            "max_confidence": 0.9,
            "allowed_symbols": self.config.allowed_symbols,
            "current_time": datetime.now(),
            "equity": equity,
            "symbol": snapshot.symbol,
        }

        return context

    def _place_order(
        self, risk_verdict: RiskVerdict, snapshot: StateSnapshot, proposal_action: str
    ) -> Dict[str, Any]:
        """Place an order via KiteAdapter if approved.

        Args:
            risk_verdict: RiskVerdict from risk checks (must be approved).
            snapshot: StateSnapshot with current market state.
            proposal_action: "BUY" or "SELL" action to place.

        Returns:
            Dict with order placement details (order_id, quantity, price, etc.).
        """
        if not risk_verdict.approved:
            raise ValueError("Cannot place order: risk verdict not approved")

        # Use final_qty from risk verdict as the order quantity
        quantity = risk_verdict.final_qty

        # Determine price - use current market price from quote
        # In a real implementation, we'd get the current quote
        # For now, use the snapshot's last close as proxy
        current_price = snapshot.indicators.get("ema_fast", 0.0) or \
            (snapshot.ohlcv_tail[-1] if snapshot.ohlcv_tail else 0.0)

        # Use final_stop from risk verdict as the stop price
        stop_price = risk_verdict.final_stop

        # Validate symbol with kite adapter
        try:
            self.kite_adapter._validate_symbol(snapshot.symbol)
        except Exception as e:
            logger.warning(f"Symbol validation warning: {str(e)}")

        # Place the order via KiteAdapter with rate limit protection
        max_retries = self.config.rate_limit_max_retries
        backoff_factor = self.config.rate_limit_backoff_factor
        retry_count = 0

        while retry_count <= max_retries:
            api_call_count += 1
            if api_call_count > self.config.max_api_calls_per_cycle:
                wait_time = backoff_factor ** retry_count
                logger.warning(
                    f"API call limit reached ({api_call_count}/{self.config.max_api_calls_per_cycle}). "
                    f"Backing off for {wait_time}s (retry {retry_count}/{max_retries})"
                )
                time.sleep(wait_time)
                api_call_count = 0  # reset after backoff

            try:
                order_result = self.kite_adapter.place_order(
                    symbol=snapshot.symbol,
                    action=proposal_action,
                    quantity=quantity,
                    price=current_price,
                )
                logger.info(f"Order placed successfully: {order_result}")
                return {
                    "order_id": order_result.get("order_id", "N/A"),
                    "quantity": quantity,
                    "price": current_price,
                    "stop_price": stop_price,
                    "action": proposal_action,
                }
            except RateLimitError:
                retry_count += 1
                if retry_count > max_retries:
                    logger.error(
                        f"Max retries ({max_retries}) exceeded for rate limit handling"
                    )
                    raise
                wait_time = backoff_factor ** retry_count
                logger.info(
                    f"Rate limit hit. Waiting {wait_time}s before retry {retry_count}/{max_retries}"
                )
                time.sleep(wait_time)
            except Exception as e:
                logger.error(f"Order placement failed: {str(e)}")
                raise

        # Should not reach here, but just in case
        raise RateLimitError(
            f"Max retries ({max_retries}) exceeded for rate limit handling"
        )

    def _create_journal_entry(
        self,
        snapshot: StateSnapshot,
        decision_proposal: DecisionProposal,
        risk_verdict: RiskVerdict,
        order_details: Dict[str, Any],
        regime_flags: list[str],
        event_alerts: list[str],
        step: str = "approved_trade",
    ) -> Dict[str, Any]:
        """Create a journal entry for the completed cycle.

        The journal serves as the ledger - all communication between layers
        is recorded here through structured data.

        Args:
            snapshot: The StateSnapshot at the time of the cycle.
            decision_proposal: The DecisionProposal that was generated.
            risk_verdict: The RiskVerdict from risk checks.
            order_details: The order placement details.
            regime_flags: Regime flags from Research AI.
            event_alerts: Event alerts from Research AI.
            step: Cycle step identifier - "approved_trade", "risk_rejection", or "execution_failure".

        Returns:
            Dict representing the journal entry.
        """
        entry: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat(),
            "snapshot_id": snapshot.snapshot_id,
            "symbol": snapshot.symbol,
            "timeframe": snapshot.timeframe,
            "step": step,
            "decision_proposal": {
                "action": decision_proposal.action,
                "confidence": decision_proposal.confidence,
                "size_hint": decision_proposal.size_hint,
                "stop_hint": decision_proposal.stop_hint,
                "rationale": decision_proposal.rationale,
            },
            "risk_verdict": {
                "approved": risk_verdict.approved,
                "final_qty": risk_verdict.final_qty,
                "final_stop": risk_verdict.final_stop,
                "veto_reason": risk_verdict.veto_reason.value
                if risk_verdict.veto_reason
                else None,
                "checks": risk_verdict.checks,
            },
            "order_details": order_details,
            "regime_flags": regime_flags,
            "event_alerts": event_alerts,
            "config": {
                "min_confidence": self.config.min_confidence,
                "min_rr": self.config.min_rr,
                "max_position_size": self.config.max_position_size,
                "paper_trading": self.config.paper_trading,
            },
        }

        return entry