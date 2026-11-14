# ATLAS

## Purpose

ATLAS ranks a fixed stock universe before the market opens and writes a shortlist (JSON) for STYX. Research only, no order placement.

ATLAS is a fast stock-screener/research agent focused on the Indian market. The scheduled entry point is `scripts/daily_market_scan.py`, which publishes daily reports under `market-scan/` via `.github/workflows/daily-market-scan.yml` (9:00 AM IST, Monday–Friday).

Terminology (from the former GLOSSARY.md): a **cycle** is one complete pass from market-state assessment through risk verification and any approved execution attempt; a **cycle record** is the audit account of one cycle; the **journal ledger** (`atlas/journal.py`, `.journal/ledger.jsonl`) is the chronological record of cycle records used for audit and evaluation.

## Layout

```
atlas/
  state_snapshot.py      # Frozen dataclass - the model's only input
  decision_proposal.py   # DecisionProposal dataclass
  eval_set.py            # Outcome grading (grade_outcome, compute_metrics)
  journal.py             # Journal-ledger protocol (append-only JSONL)
  quant/
    data.py              # Bar loaders (yfinance) and Nifty 50 collector
    features.py          # Pure functions on bars (RSI, EMA, ATR, VWAP, ...)
    strategies.py        # Strategies emitting Signal(symbol, direction, conviction, ...)
scripts/
  daily_market_scan.py   # Scheduled market scan automation
market-scan/             # Generated daily scans and reviews
tests/                   # pytest suite
.github/
  agents/                # Custom agent definitions
  workflows/             # ci.yml, daily-market-scan.yml
docs/agents/             # Issue tracker, triage labels, domain docs conventions
validate_agents.py       # Agent frontmatter validation
pyproject.toml           # Package + tool configuration
```

The former 6-layer trading core (orchestrator, research_ai, risk_verdict, rag_corpus, brokers) is archived at tag `archive/pre-cleanup-2026-11-14` and removed from this branch.

## Setup

```bash
git clone https://github.com/SuryaVamsi009/ATLAS.git
cd ATLAS
pip install -e ".[dev]"     # Python 3.11+; deps include requests, beautifulsoup4,
                            # lxml, python-dateutil, pytz, pandas, numpy, yfinance
```

Run the market scan locally:

```bash
python scripts/daily_market_scan.py
```

Validate agent frontmatter:

```bash
python validate_agents.py
```

## Running tests

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

CI (`.github/workflows/ci.yml`) runs pytest with coverage, `ruff check .`, `ruff format --check .`, and mypy on `atlas/`.

## Roadmap

- Issues and specs live in GitHub Issues for `SuryaVamsi009/ATLAS` (use the `gh` CLI; see `docs/agents/issue-tracker.md`).
- Triage labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` (see `docs/agents/triage-labels.md`).
- Domain docs: single-context repo; use the terminology above and `docs/adr/` when present (see `docs/agents/domain.md`).

### Screener Enhancements
- Extend `atlas/quant/strategies.py` with additional signal generators (ORB, VWAP reversion, gap fade).
- Add purged walk-forward validation in `atlas/eval_set.py` with hold-out periods and trial log (`quant/trials.jsonl`).
- Implement deflated Sharpe and 2× cost stress testing for strategy validation.
- Connect `eval_set.py` to read from journal ledger (`.journal/ledger.jsonl`) for confidence calibration (hit rates by confidence bin, R-multiple averages).

### Data Quality
- Complete 1-minute collector for Nifty 50 → partitioned parquet in `atlas/quant/data.py`.
- Add quality checks: gap detection, duplicate removal, timezone validation.

### Monitoring & Observability
- Add per-cycle metrics tracking (duration, API calls, veto reason distribution, P&L summary).
- CLI summary and JSON output for scheduled job health.

## Recovery

- **Canonical restore point:** Git tag `archive/pre-cleanup-2026-11-14` contains the full 6-layer trading core (orchestrator, research_ai, risk_verdict, rag_corpus, brokers/kite_adapter) before cleanup.
- **Journal ledger:** Local JSONL at `.journal/ledger.jsonl` — back up daily to encrypted storage outside GitHub; not committed to repo.
- **Market-scan reports:** Committed under `market-scan/`; retained in Git history and any repository mirror.
- **GitHub Actions:** Schedules defined in `.github/workflows/` (ci.yml, daily-market-scan.yml); recreate via workflow dispatch if Actions outage.
- **Rebuild:** Python 3.11+, `pip install -e ".[dev]"`, then `pytest -q` and `python scripts/daily_market_scan.py`.
- **Paper-trading invariant:** `OrchestratorConfig` (when present) defaults to `paper_trading=True`; risk checks must remain in the execution path; no recovery test enables live orders.
