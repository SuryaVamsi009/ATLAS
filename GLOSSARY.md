# ATLAS

ATLAS is a research and decision system for Indian market analysis. Its cycles turn market state into a risk-checked trading proposal and an auditable outcome.

## Language

**Cycle**:
One complete ATLAS pass from market-state assessment through risk verification and any approved execution attempt.
_Avoid_: Run

**Cycle record**:
The audit account of one Cycle, including its analysis, proposal, risk outcome, and execution outcome when applicable.
_Avoid_: Log entry

**Journal ledger**:
The chronological record of Cycle records used for audit and evaluation.
_Avoid_: Trade log

**Universe**:
The set of eligible symbols for trading (e.g., Nifty 200 constituents). Fetched from NSE archives and cached locally.
_Avoid_: Watchlist

**Call**:
A registered, immutable trading proposal with side, stop, target, horizon, and confidence. Stored append-only in the call registry.
_Avoid_: Signal, prediction

**Call Registry**:
Append-only JSONL file storing registered calls. No mutation functions (update/edit/delete).
_Avoid_: Signal database

**Grade**:
Mechanical outcome of a call against real price bars: TARGET_HIT, STOP_HIT, EXPIRED, NOT_TRIGGERED, or INVALID.
_Avoid_: Result, evaluation

**Eval Set**:
Collection of eval entries built from registered calls and real replayed bars (not synthetic). Each entry links a decision proposal to its ground truth.
_Avoid_: Test set, synthetic eval

**R-multiple**:
Risk-normalized return: (exit - entry) / (entry - stop) for longs, (entry - exit) / (stop - entry) for shorts. Net version subtracts round-trip costs.
_Avoid_: Return, PnL

**Calibration**:
Observed success rate per confidence bin. No hardcoded expected rate (e.g., 70%) - only report what the data shows.
_Avoid_: Accuracy, confidence score

**Cost Drag**:
Reduction in r-multiple from round-trip costs: (entry * cost_pct / 100) / risk_per_share.
_Avoid_: Slippage, fees

**Deflated Sharpe**:
Sharpe ratio adjusted for multiple testing (trial log). Accounts for the number of strategies tried.
_Avoid_: Sharpe ratio

**Purged Walk-Forward**:
Validation split that purges embargo periods between train and test to prevent leakage.
_Avoid_: Cross-validation, backtest split
