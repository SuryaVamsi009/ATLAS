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

The former 6-layer trading core (orchestrator, research_ai, risk_verdict, rag_corpus, brokers) is archived on branch `archive/six-layer-core`, pending removal from main.

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
- `ATLAS_NEXT_STEPS.md` and `DISASTER_RECOVERY.md` describe the archived 6-layer trading core and are outdated; see the final cleanup report for details.
