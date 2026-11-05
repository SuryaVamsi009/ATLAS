"""Utility functions for the ATLAS 6-layer trading architecture.

This module provides convenient helper functions that tie together
the various ATLAS modules (orchestrator, research_ai, eval_pipeline,
journal, etc.) for automation tasks and routine operations.

It supports all 5 prioritized steps from the forward plan:
1. Journal ledger integration
2. Rate limit handling
3. Confidence calibration pipeline
4. Indian market pattern queries
5. LLM provider integration
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from atlas.orchestrator import (
    _create_journal_entry,
    OrchestratorConfig,
    RateLimitError as OrchestratorRateLimitError,
)
from atlas.research_ai import ConfigDrivenResearchAI
from atlas.eval_pipeline import run_evaluation_pipeline
from atlas.journal import (
    write_regime_entry,
    read_all_regime_entries,
    read_latest_regime_entry,
    get_ledger_stats,
)
from atlas.risk_verdict import RiskVerdict, VetoReason


# =============================================================================
# Step 1: Journal Ledger Utilities
# =============================================================================

def create_approved_trade_entry(
    snapshot_id: str,
    regime_flags: List[str],
    event_alerts: List[str],
    thesis: str,
    confidence: float,
    news_context: str,
    trade_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a journal entry for an approved trade (Step 1).

    Args:
        snapshot_id: StateSnapshot identifier
        regime_flags: List of regime flag strings
        event_alerts: List of event alert strings
        thesis: Trade thesis/rationale
        confidence: Confidence score [0.0, 1.0]
        news_context: String summarizing recent news
        trade_data: Additional trade data (symbol, entry_price, etc.)

    Returns:
        entry_id of the written ledger entry
    """
    extra_data = {}
    if trade_data:
        extra_data.update(trade_data)

    return _create_journal_entry(
        step="approved_trade",
        trade_data={
            "snapshot_id": snapshot_id,
            "regime_flags": regime_flags,
            "event_alerts": event_alerts,
            "thesis": thesis,
            "confidence": confidence,
            "news_context": news_context,
            **extra_data,
        },
    )


def create_risk_rejection_entry(
    snapshot_id: str,
    regime_flags: List[str],
    event_alerts: List[str],
    thesis: str,
    confidence: float,
    news_context: str,
    veto_reason: VetoReason,
    trade_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Create a journal entry for a risk rejection (Step 1).

    Args:
        snapshot_id: StateSnapshot identifier
        regime_flags: List of regime flag strings
        event_alerts: List of event alert strings
        thesis: Trade thesis/rationale
        confidence: Confidence score [0.0, 1.0]
        news_context: String summarizing recent news
        veto_reason: The VetoReason that caused the rejection
        trade_data: Additional trade data (symbol, entry_price, etc.)

    Returns:
        entry_id of the written ledger entry
    """
    extra_data = {}
    if trade_data:
        extra_data.update(trade_data)

    return _create_journal_entry(
        step="risk_rejection",
        trade_data={
            "snapshot_id": snapshot_id,
            "regime_flags": regime_flags,
            "event_alerts": event_alerts,
            "thesis": thesis,
            "confidence": confidence,
            "news_context": news_context,
            "veto_reason": veto_reason.value,
            **extra_data,
        },
    )


# =============================================================================
# Step 2: Rate Limit Handling Utilities
# =============================================================================

def check_rate_limit(
    config: OrchestratorConfig,
    api_calls_this_cycle: int,
) -> Tuple[bool, float]:
    """Check if we're within rate limit and compute backoff if needed.

    Args:
        config: OrchestratorConfig with rate limit settings
        api_calls_this_cycle: Number of API calls made in current cycle

    Returns:
        Tuple of (within_limit, backoff_wait_seconds)
    """
    max_calls = config.max_api_calls_per_cycle
    backoff_factor = config.rate_limit_backoff_factor
    max_retries = config.rate_limit_max_retries

    if api_calls_this_cycle >= max_calls:
        # Calculate exponential backoff wait time
        # wait_time = backoff_factor ** retry_count
        retry_count = min(api_calls_this_cycle - max_calls + 1, max_retries)
        wait_time = backoff_factor ** retry_count
        return False, wait_time

    return True, 0.0


def rate_limit_backoff(
    retry_count: int,
    backoff_factor: float = 2.0,
) -> float:
    """Calculate exponential backoff wait time.

    Args:
        retry_count: Number of retries attempted (0-indexed)
        backoff_factor: Base for exponential backoff (default 2.0)

    Returns:
        Wait time in seconds
    """
    return backoff_factor ** retry_count


def should_retry(
    api_calls_this_cycle: int,
    max_calls: int,
    retry_count: int,
    max_retries: int = 3,
) -> bool:
    """Determine if another retry is appropriate.

    Args:
        api_calls_this_cycle: Current cycle API call count
        max_calls: Maximum allowed per cycle
        retry_count: How many retries have been attempted
        max_retries: Maximum retries allowed

    Returns:
        True if another retry should be attempted
    """
    if retry_count >= max_retries:
        return False
    if api_calls_this_cycle >= max_calls and retry_count > 0:
        return False
    return api_calls_this_cycle < max_calls


# =============================================================================
# Step 3: Confidence Calibration Pipeline Utilities
# =============================================================================

def calibrate_confidence_from_ledger(
    min_entries: int = 10,
    regime_filter: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Calibrate confidence thresholds from journal ledger entries (Step 3).

    Reads from the Journal ledger to analyze confidence calibration
    across historical trades.

    Args:
        min_entries: Minimum number of entries needed for calibration
        regime_filter: Optional filter for specific regime flags

    Returns:
        Dict with calibration statistics
    """
    entries = read_all_regime_entries()

    if not entries:
        return {
            "status": "no_data",
            "message": "No journal entries found for calibration",
            "entries_analyzed": 0,
        }

    # Filter by regime if specified
    if regime_filter:
        entries = [
            e for e in entries
            if any(r in e.get("regime_flags", []) for r in regime_filter)
        ]

    if len(entries) < min_entries:
        return {
            "status": "insufficient_data",
            "message": f"Only {len(entries)} entries (need {min_entries})",
            "entries_analyzed": len(entries),
        }

    # Calculate calibration stats
    confidences = []
    pnl_values = []
    regime_counts: Dict[str, int] = {}

    for entry in entries:
        conf = entry.get("confidence")
        if conf is not None:
            confidences.append(conf)

        pnl = entry.get("pnl")
        if pnl is not None:
            pnl_values.append(pnl)

        # Count regimes
        for regime in entry.get("regime_flags", []):
            regime_counts[regime] = regime_counts.get(regime, 0) + 1

    # Calculate statistics
    if confidences:
        avg_confidence = sum(confidences) / len(confidences)
        min_confidence = min(confidences)
        max_confidence = max(confidences)
    else:
        avg_confidence = min_confidence = max_confidence = 0.0

    if pnl_values:
        total_pnl = sum(pnl_values)
        avg_pnl = total_pnl / len(pnl_values)
    else:
        total_pnl = 0.0
        avg_pnl = 0.0

    return {
        "status": "calibrated",
        "entries_analyzed": len(entries),
        "average_confidence": round(avg_confidence, 4),
        "confidence_range": {
            "min": round(min_confidence, 4),
            "max": round(max_confidence, 4),
        },
        "total_pnl": round(total_pnl, 4),
        "average_pnl": round(avg_pnl, 4),
        "completed_trades": len(pnl_values),
        "regime_distribution": regime_counts,
        "most_common_regime": max(regime_counts, key=regime_counts.get) if regime_counts else "none",
    }


# =============================================================================
# Step 4 & 5: Research AI & Indian Market Pattern Utilities
# =============================================================================

def create_research_ai(
    min_confidence: float = 0.3,
    ai_provider: str = "rule_based",
    model_name: str = "rule-based",
    rag_weight: float = 0.3,
) -> ConfigDrivenResearchAI:
    """Create a ConfigDrivenResearchAI instance with configured settings (Steps 4-5).

    Args:
        min_confidence: Minimum confidence threshold
        ai_provider: AI provider ("openai", "anthropic", "gemini", "rule_based")
        model_name: Model name/config
        rag_weight: Weight for RAG corpus (0.0 = pure rules, 1.0 = pure RAG)

    Returns:
        Configured ConfigDrivenResearchAI instance
    """
    return ConfigDrivenResearchAI(
        min_confidence=min_confidence,
        ai_provider=ai_provider,
        model_name=model_name,
        rag_weight=rag_weight,
    )


def analyze_market(
    snapshot: Any,
    news_context: str,
    rag_corpus: Any,
    context_dict: Dict[str, Any],
    ai_provider: str = "rule_based",
    rag_weight: float = 0.3,
) -> Dict[str, List[str]]:
    """Analyze market data using Research AI (Steps 4-5).

    Convenience function that creates a research AI instance and runs analysis.

    Args:
        snapshot: StateSnapshot with current market state
        news_context: String summarizing recent news
        rag_corpus: RAGCorpus for pattern matching
        context_dict: Additional context from orchestrator
        ai_provider: AI provider to use
        rag_weight: Weight for RAG corpus results

    Returns:
        Dict with "regime_flags" and "event_alerts" lists
    """
    ai = ConfigDrivenResearchAI(
        min_confidence=0.3,
        ai_provider=ai_provider,
        rag_weight=rag_weight,
    )
    return ai.analyze(snapshot, news_context, rag_corpus, context_dict)


def get_provider_config(provider: str) -> Dict[str, Any]:
    """Get provider configuration for the specified AI provider.

    Args:
        provider: AI provider name ("openai", "anthropic", "gemini", "rule_based")

    Returns:
        Dict with provider configuration (API key, model, endpoint)
    """
    ai = ConfigDrivenResearchAI(ai_provider=provider)
    return ai.ai_provider_config


# =============================================================================
# Cross-Cutting Utilities
# =============================================================================

def get_market_hours_ist() -> Tuple[bool, str]:
    """Check if current time is within Indian market hours (9:15 AM - 3:30 PM IST).

    NSE (National Stock Exchange) trading hours:
    - Normal session: 9:15 AM to 3:30 PM IST
    - Pre-market: 9:00 AM to 9:15 AM IST
    - Post-market: 3:30 PM to 4:00 PM IST (orders only)

    Returns:
        Tuple of (is_market_hours, message)
    """
    now = datetime.now()
    # IST offset = +5:30 from UTC
    ist_offset = timedelta(hours=5, minutes=30)
    ist_time = now + ist_offset

    # Market hours: 9:15 AM to 3:30 PM IST
    market_open = datetime(ist_time.year, ist_time.month, ist_time.day, 9, 15)
    market_close = datetime(ist_time.year, ist_time.month, ist_time.day, 15, 30)

    is_market_hours = market_open <= ist_time <= market_close

    if is_market_hours:
        return True, f"Market hours: {ist_time.strftime('%H:%M:%S')} IST"
    else:
        # Determine if before open or after close
        if ist_time < market_open:
            time_to_open = market_open - ist_time
            minutes = time_to_open.seconds // 60
            return False, f"Market closed. Opens in {minutes} minutes at {market_open.strftime('%H:%M:%S')} IST"
        else:
            time_since_close = ist_time - market_close
            minutes = time_since_close.seconds // 60
            return False, f"Market closed {minutes} minutes ago at {market_close.strftime('%H:%M:%S')} IST"


def get_ist_timestamp() -> str:
    """Get current timestamp in Indian Standard Time (IST).

    IST = UTC + 5:30

    Returns:
        Timestamp string in ISO format (YYYY-MM-DDTHH:MM:SS)
    """
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    return now.strftime("%Y-%m-%dT%H:%M:%S")


def format_regime_flags(flags: List[str]) -> str:
    """Format regime flags into a readable string.

    Args:
        flags: List of regime flag strings

    Returns:
        Comma-separated string of regime flags
    """
    if not flags:
        return "no_regime"
    return ", ".join(flags)


def calculate_position_size(
    equity: float,
    confidence: float,
    risk_pct: float = 2.0,
    volatility_adjustment: float = 1.0,
) -> float:
    """Calculate position size based on equity, confidence, and risk parameters.

    Position size = equity * (confidence/100) * (risk_pct/100) * volatility_adjustment

    Args:
        equity: Available trading equity
        confidence: Confidence score [0.0, 1.0]
        risk_pct: Risk percentage of equity to allocate [default: 2.0%]
        volatility_adjustment: Volatility-based adjustment factor [default: 1.0]

    Returns:
        Position size as fraction of equity (0.0 to 1.0)
    """
    if equity <= 0:
        return 0.0
    if not (0.0 <= confidence <= 1.0):
        confidence = max(0.0, min(1.0, confidence))

    position_fraction = (confidence * risk_pct / 100.0) * volatility_adjustment
    return min(position_fraction, 1.0)


def export_ledger_for_analysis(
    output_path: str,
    regime_filter: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Export ledger entries for analysis (Step 3 calibration).

    Reads all journal entries (with optional filtering) and writes them
    to a specified output path for external analysis.

    Args:
        output_path: Path to write the exported entries
        regime_filter: Optional list of regime flags to include
        start_date: Optional start date filter (ISO format YYYY-MM-DD)
        end_date: Optional end date filter (ISO format YYYY-MM-DD)

    Returns:
        Path to the exported file
    """
    from atlas.journal import get_ledger_entries

    entries = get_ledger_entries(
        filter_regime=regime_filter,
    )

    # Apply date filters if provided
    if start_date or end_date:
        from datetime import datetime
        start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None

        filtered_entries = []
        for entry in entries:
            ts_str = entry.get("timestamp_ist") or entry.get("timestamp", "")
            try:
                entry_date = datetime.fromisoformat(ts_str).date()
                if start_dt and entry_date < start_dt.date():
                    continue
                if end_dt and entry_date > end_dt.date():
                    continue
            except (ValueError, TypeError):
                pass
            filtered_entries.append(entry)
        entries = filtered_entries

    # Write to output file
    import json
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, default=str)

    return output_path