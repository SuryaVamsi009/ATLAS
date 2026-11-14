"""ATLAS - stock-screener/research package.

Ranks a fixed stock universe before the market opens and writes a shortlist
(JSON) for STYX. Research only, no order placement.

The main components are:
- StateSnapshot: Immutable market state snapshot
- DecisionProposal: Structured trading proposal dataclass
- RiskVerdict / VetoReason: Risk verdict record (defined in atlas.journal)
- EvalSet: Outcome grading (grade_outcome, compute_metrics)
- Journal: Append-only JSONL ledger
"""

from atlas.decision_proposal import DecisionProposal
from atlas.eval_set import EvalEntry, Outcome, grade_outcome
from atlas.journal import RiskVerdict, VetoReason
from atlas.state_snapshot import StateSnapshot, compute_from_bars

__all__ = [
    "StateSnapshot",
    "compute_from_bars",
    "DecisionProposal",
    "Outcome",
    "grade_outcome",
    "EvalEntry",
    "RiskVerdict",
    "VetoReason",
]
