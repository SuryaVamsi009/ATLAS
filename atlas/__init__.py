"""ATLAS - Architecture for Trading, Learning, and Adaptive Systems.

This package implements the ATLAS architecture with multiple layers for
market analysis, decision making, risk verification, and execution.

The main components are:
- StateSnapshot: Immutable market state snapshot (L1)
- DecisionProposal: Trading proposal from analysis layer (L3)
- RiskVerdict: Risk verification result (L4)
- ResearchAI: Regime flag and event alert generation (L3)
- RAGCorpus: Retrieval-augmented generation context (L2)
- KiteAdapter: Broker execution interface (L5)
- EvalSet: Evaluation and backtesting framework

Two-AI Architecture:
- Research AI produces regime flags, event alerts (NO order placement)
- Agent AI (via DecisionProposal + RiskVerdict) decides on orders
- Communication only through ledger/structured data
"""

from atlas.brokers.kite_adapter import KiteAdapter
from atlas.decision_proposal import DecisionProposal
from atlas.eval_set import EvalEntry, Outcome, Grade, grade_call, build_eval_set
from atlas.orchestrator import Orchestrator, OrchestratorConfig
from atlas.rag_corpus import RAGCorpus
from atlas.research_ai import ConfigDrivenResearchAI, ResearchAI
from atlas.risk_verdict import RiskVerdict, verify
from atlas.state_snapshot import StateSnapshot, compute_from_bars

__all__ = [
    "StateSnapshot",
    "compute_from_bars",
    "DecisionProposal",
    "Outcome",
    "Grade",
    "grade_call",
    "build_eval_set",
    "EvalEntry",
    "RiskVerdict",
    "verify",
    "ResearchAI",
    "ConfigDrivenResearchAI",
    "RAGCorpus",
    "Orchestrator",
    "OrchestratorConfig",
    "KiteAdapter",
]
