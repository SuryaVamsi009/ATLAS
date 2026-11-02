"""Journal ledger module for the ATLAS Two-AI architecture.

This module implements the journal-ledger protocol defined in the ATLAS forward plan
(Step 3: Two-AI Journal-Ledger Protocol). It defines the exact structured hand-off
between Research AI and Agent AI through an append-only ledger.

Two-AI boundary enforcement:
- Research AI writes: regime_flags, event_alerts, thesis, confidence_score
- Agent AI reads: DecisionProposal (action, confidence, size_hint, stop_hint, rationale)
- Full cycle captured: state → proposal → verdict → order → fill → P&L
- No direct communication between agents; all data flows through ledger

Ledger entry format (JSON-compatible, append-only):
{
  "entry_id": str,           # Unique identifier
  "timestamp_ist": str,      # IST timestamp
  "snapshot_id": str,        # StateSnapshot identifier
  "regime_flags": [str],     # From Research AI
  "event_alerts": [str],     # From Research AI
  "thesis": str,             # Research AI's analysis thesis
  "decision_proposal": dict, # Agent AI's DecisionProposal
  "risk_verdict": dict,      # RiskVerdict result
  "order_result": dict,      # KiteAdapter order result (filled/partial/cancelled)
  "pnl": float,              # Profit & Loss from the trade
  "confidence_calibration": str  # Binned confidence for review
}
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from atlas.decision_proposal import DecisionProposal
from atlas.risk_verdict import RiskVerdict, VetoReason


# --- Ledger file path ---

LEDGER_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".journal")
LEDGER_FILE = os.path.join(LEDGER_DIR, "ledger.jsonl")


def _ensure_ledger_dir() -> None:
    """Ensure the journal ledger directory exists."""
    os.makedirs(LEDGER_DIR, exist_ok=True)


def _append_entry(entry: Dict[str, Any]) -> None:
    """Append a single entry to the JSONL ledger file."""
    _ensure_ledger_dir()
    with open(LEDGER_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --- Research AI write: what Research AI produces ---

def write_regime_entry(
    snapshot_id: str,
    regime_flags: List[str],
    event_alerts: List[str],
    thesis: str,
    confidence: float,
    news_context: str,
) -> str:
    """Write a Research AI output entry to the ledger.

    This is what Research AI writes - regime flags, event alerts, thesis,
    and confidence. Does NOT place orders.

    Args:
        snapshot_id: StateSnapshot identifier
        regime_flags: List of regime flag strings (e.g., ["trending_up"])
        event_alerts: List of event alert strings (e.g., ["breakout"])
        thesis: Research AI's analysis thesis/rationale
        confidence: Confidence score [0.0, 1.0]
        news_context: String summarizing recent news

    Returns:
        entry_id of the written ledger entry
    """
    entry_id = f"regime_{snapshot_id}_{int(datetime.utcnow().timestamp())}"
    entry = {
        "entry_id": entry_id,
        "timestamp_ist": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        "snapshot_id": snapshot_id,
        "regime_flags": regime_flags,
        "event_alerts": event_alerts,
        "thesis": thesis,
        "confidence": confidence,
        "news_context": news_context,
        "agent_action": None,  # Filled in later by Agent AI
        "risk_verdict": None,  # Filled in later
        "order_result": None,  # Filled in later
        "pnl": None,  # Filled in later
    }
    _append_entry(entry)
    return entry_id


# --- Agent AI read: what Agent AI consumes ---

def read_latest_regime_entry() -> Optional[Dict[str, Any]]:
    """Read the latest Research AI entry from the ledger.

    Agent AI reads this to get the regime flags, event alerts, thesis,
    and confidence before generating a DecisionProposal.

    Returns:
        Latest ledger entry dict, or None if no entries exist.
    """
    if not os.path.exists(LEDGER_FILE):
        return None
    with open(LEDGER_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if not lines:
        return None
    # Return the last entry
    return json.loads(lines[-1].strip())


def read_all_regime_entries() -> List[Dict[str, Any]]:
    """Read all Research AI entries from the ledger.

    Useful for weekly calibration review (Step 5: Confidence Calibration).

    Returns:
        List of all ledger entries in chronological order.
    """
    if not os.path.exists(LEDGER_FILE):
        return []
    with open(LEDGER_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    entries = []
    for line in lines:
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


# --- Agent AI write: DecisionProposal hand-off ---

def write_decision_proposal_entry(
    snapshot_id: str,
    decision_proposal: DecisionProposal,
    regime_entry_id: str,
) -> str:
    """Write a DecisionProposal entry to the ledger, hand-off from Agent AI.

    This is what Agent AI writes after reading the Research AI entry.
    The DecisionProposal is the agent's order proposal that will flow
    through RiskVerdict → KiteAdapter.

    Args:
        snapshot_id: StateSnapshot identifier
        decision_proposal: The DecisionProposal from Agent AI
        regime_entry_id: The regime entry ID from the ledger this proposal relates to

    Returns:
        entry_id of the written ledger entry
    """
    entry_id = f"proposal_{regime_entry_id}"
    # Convert DecisionProposal to dict for JSON serialization
    proposal_dict = {
        "action": decision_proposal.action,
        "confidence": decision_proposal.confidence,
        "size_hint": decision_proposal.size_hint,
        "stop_hint": decision_proposal.stop_hint,
        "rationale": decision_proposal.rationale,
    }

    entry = {
        "entry_id": entry_id,
        "timestamp_ist": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        "snapshot_id": snapshot_id,
        "regime_entry_id": regime_entry_id,
        "decision_proposal": proposal_dict,
        "agent_action": "generate_decision_proposal",
        "risk_verdict": None,  # Filled in later by RiskVerdict
        "order_result": None,  # Filled in later by KiteAdapter
        "pnl": None,  # Filled in later
    }
    _append_entry(entry)
    return entry_id


# --- RiskVerdict write: verdict hand-off ---

def write_risk_verdict_entry(
    proposal_entry_id: str,
    risk_verdict: RiskVerdict,
) -> str:
    """Write a RiskVerdict entry to the ledger, hand-off from Risk verification.

    Args:
        proposal_entry_id: The DecisionProposal entry ID this verdict relates to
        risk_verdict: The RiskVerdict result

    Returns:
        entry_id of the written ledger entry (updated with verdict)
    """
    # Read the latest entry and update it
    entries = read_all_regime_entries()
    if entries:
        # Find the latest proposal entry and update with verdict
        latest = entries[-1]
        if latest.get("entry_id") == proposal_entry_id:
            latest["risk_verdict"] = {
                "approved": risk_verdict.approved,
                "final_qty": risk_verdict.final_qty,
                "final_stop": risk_verdict.final_stop,
                "veto_reason": risk_verdict.veto_reason.value if risk_verdict.veto_reason else None,
                "checks": risk_verdict.checks,
            }
            # Rewrite the file with updated entry
            _rewrite_ledger(entries)
    return proposal_entry_id


# --- KiteAdapter write: order result hand-off ---

def write_order_result_entry(
    proposal_entry_id: str,
    order_result: Dict[str, Any],
) -> str:
    """Write an order result entry to the ledger, hand-off from KiteAdapter.

    Args:
        proposal_entry_id: The DecisionProposal entry ID this order result relates to
        order_result: Dict with order fill information

    Returns:
        entry_id of the written ledger entry (updated with order result)
    """
    entries = read_all_regime_entries()
    if entries:
        latest = entries[-1]
        if latest.get("entry_id") == proposal_entry_id:
            latest["order_result"] = order_result
            # Recalculate P&L if we have entry and exit prices
            _calculate_pnl(latest)
            _rewrite_ledger(entries)
    return proposal_entry_id


def _calculate_pnl(entry: Dict[str, Any]) -> None:
    """Calculate and store P&L for a completed trade.

    P&L = (exit_price - entry_price) * quantity for long,
    or (entry_price - exit_price) * quantity for short.

    If order_result has fill data, compute P&L; otherwise set to None.
    """
    order_result = entry.get("order_result")
    if not order_result:
        entry["pnl"] = None
        return

    # Try to extract prices from order result
    fill_price = order_result.get("fill_price")
    exit_price = order_result.get("exit_price") or fill_price
    quantity = order_result.get("quantity", 0)
    action = entry.get("decision_proposal", {}).get("action", "BUY")
    decision_conf = entry.get("decision_proposal", {}).get("confidence", 0.5)

    if fill_price is None or exit_price is None:
        entry["pnl"] = None
        return

    if action == "BUY":
        entry["pnl"] = (exit_price - fill_price) * quantity
    elif action == "SELL":
        entry["pnl"] = (fill_price - exit_price) * quantity
    else:
        entry["pnl"] = None


def _rewrite_ledger(entries: List[Dict[str, Any]]) -> None:
    """Rewrite the entire ledger file from a list of entries."""
    _ensure_ledger_dir()
    with open(LEDGER_FILE, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --- Ledger query: read for evaluation and review ---

def get_ledger_entries(
    filter_regime: Optional[List[str]] = None,
    filter_start: Optional[datetime] = None,
    filter_end: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Read ledger entries with optional filtering.

    Args:
        filter_regime: Only include entries with these regime_flags
        filter_start: Only include entries from this datetime (UTC)
        filter_end: Only include entries until this datetime (UTC)

    Returns:
        Filtered list of ledger entries.
    """
    if not os.path.exists(LEDGER_FILE):
        return []

    with open(LEDGER_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)

        # Apply regime filter
        if filter_regime:
            entry_regimes = entry.get("regime_flags", [])
            if not any(r in entry_regimes for r in filter_regime):
                continue

        # Apply time filter
        if filter_start or filter_end:
            ts_str = entry.get("timestamp_ist", "")
            try:
                entry_dt = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S")
                if filter_start and entry_dt < filter_start:
                    continue
                if filter_end and entry_dt > filter_end:
                    continue
            except (ValueError, TypeError):
                pass  # Include entries with unparseable timestamps

        entries.append(entry)

    return entries


def get_ledger_stats() -> Dict[str, Any]:
    """Get statistics about the ledger.

    Returns:
        Dict with entry count, regime distribution, confidence stats, P&L summary.
    """
    if not os.path.exists(LEDGER_FILE):
        return {
            "total_entries": 0,
            "regime_distribution": {},
            "confidence_range": "0.0-1.0",
            "total_pnl": 0.0,
            "completed_trades": 0,
        }

    entries = read_all_regime_entries()
    total = len(entries)

    # Regime distribution
    regime_dist: Dict[str, int] = {}
    for entry in entries:
        for regime in entry.get("regime_flags", []):
            regime_dist[regime] = regime_dist.get(regime, 0) + 1

    # Confidence range
    confidences = []
    for entry in entries:
        conf = entry.get("confidence")
        if conf is not None:
            confidences.append(conf)

    # P&L summary
    pnl_total = 0.0
    completed = 0
    for entry in entries:
        pnl = entry.get("pnl")
        if pnl is not None:
            pnl_total += pnl
            completed += 1

    # Find most common regime
    most_common_regime = max(regime_dist, key=regime_dist.get) if regime_dist else "none"

    return {
        "total_entries": total,
        "regime_distribution": regime_dist,
        "most_common_regime": most_common_regime,
        "confidence_range": f"{min(confidences):.2f}-{max(confidences):.2f}" if confidences else "0.0-1.0",
        "total_pnl": pnl_total,
        "completed_trades": completed,
        "avg_pnl": pnl_total / completed if completed > 0 else 0.0,
    }


if __name__ == "__main__":
    # Quick test: write and read a regime entry
    import tempfile
    import os

    # Test writing a regime entry
    entry_id = write_regime_entry(
        snapshot_id="test_snapshot_1",
        regime_flags=["trending_up", "neutral"],
        event_alerts=["breakout"],
        thesis="Nifty above 50-DMA with FII buying, trending market conditions",
        confidence=0.78,
        news_context="Q2 earnings season starting; IT sector AI revenue beats; FII buying observed",
    )
    print(f"Wrote regime entry: {entry_id}")

    # Read it back
    latest = read_latest_regime_entry()
    if latest:
        print(f"Read back entry: {latest['entry_id']}")
        print(f"  Regime flags: {latest['regime_flags']}")
        print(f"  Thesis: {latest['thesis'][:60]}...")
        print(f"  Confidence: {latest['confidence']}")

    # Test ledger stats
    stats = get_ledger_stats()
    print(f"\nLedger stats: {stats}")

    # Clean up test file
    test_file = "/tmp/test_ledger.jsonl"
    if os.path.exists(test_file):
        os.remove(test_file)
