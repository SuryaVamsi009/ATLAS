# Registered-Call Evaluation Architecture

**Status**: accepted

## Context

The original evaluation system used a synthetic `generate_eval_set()` function that created artificial test cases with hardcoded expectations (e.g., 70% hit rate). This was replaced with a registered-call system where:

1. Analysts register immutable calls (side, stop, target, horizon, confidence) append-only to a JSONL registry
2. Real NSE price bars are replayed against these calls to produce mechanical grades
3. Metrics are computed from resolved outcomes only (no hardcoded thresholds)

## Decision

- **Universe** (`atlas/universe.py`): Fetches Nifty 200/500 constituents from NSE archives, caches locally with validation
- **Call Registry** (`atlas/call_registry.py`): Append-only JSONL with frozen `Call` dataclass, validation, atomic fsync writes, no mutation functions
- **Grader v2** (`atlas/eval_set.py`): `grade_call()` with proper entry logic (first bar after created_at), stop-first checking, gap handling, INVALID outcome for impossible entries, cost-adjusted R-multiples
- **Eval Set Builder** (`build_eval_set()`): Replaces `generate_eval_set()`, builds entries from registered calls + real replayed bars
- **Pipeline** (`atlas/eval_pipeline.py`): Rewritten to use `build_eval_set()`, prints observed calibration rates per bin with no hardcoded expectations

## Why

- Synthetic eval sets cannot validate real strategy edge; they only test the grader
- Registered calls create an audit trail: every evaluation traces back to a human decision
- Mechanical grading removes subjective interpretation
- Cost-adjusted R-multiples reflect real Indian market costs (~0.11% round-trip)
- Purged walk-forward splits prevent leakage between train/test
- Deflated Sharpe accounts for multiple testing across strategies

## Consequences

- Requires NSE data access (nsearchives.nseindia.com) for universe fetching
- Call registration is a manual step before evaluation (not automated)
- No mutation of calls means corrections require new call entries
- Evaluation now depends on real bar data availability (yfinance or other sources)