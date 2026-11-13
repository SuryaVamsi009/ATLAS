# ATLAS Copilot Instructions

## Commands

- Run the scheduled market scan locally: `python scripts/daily_market_scan.py`. It requires the scan dependencies listed in `README.md`.
- Validate custom agent frontmatter: `python validate_agents.py` (requires PyYAML). The script checks `.github/agents/`.
- No test files or repository test/lint configuration are present. When a pytest test exists, run one with `pytest path/to/test_file.py::test_name`.

## Architecture

`StateSnapshot` (`atlas/state_snapshot.py`) is the model-facing market representation. Its indicators and regime features are computed in Python from bars shaped as `[timestamp, open, high, low, close, volume]`. `DecisionProposal` (`atlas/decision_proposal.py`) is the structured hand-off between analysis and execution.

`atlas/journal.py` stores JSONL records under `.journal/ledger.jsonl`; retain an audit trail for rejected as well as approved cycles. The `atlas/quant/` modules provide separate bar loaders (`data.py`), feature calculations (`features.py`), and strategy signals (`strategies.py`). The daily news/market scan in `scripts/daily_market_scan.py` is a separate workflow, scheduled by `.github/workflows/daily-market-scan.yml` to publish reports under `market-scan/`. Evaluation and backtesting are in `atlas/eval_set.py`.

## Conventions

- Keep provider selection config-driven; `rule_based` is the default fallback.
- Use `Asia/Kolkata` for market-time logic and timestamps.
- Preserve research-only and paper-trading behavior.
- For the broader project roadmap and existing contributor context, consult the root `copilot-instructions.md` and `ATLAS_NEXT_STEPS.md`; the README is the reference for setup and the system overview.
