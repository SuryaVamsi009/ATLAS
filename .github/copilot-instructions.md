# ATLAS Copilot Instructions

## Commands

- Run the scheduled market scan locally: `python scripts/daily_market_scan.py`. It requires the scan dependencies listed in `README.md`.
- Validate custom agent frontmatter: `python validate_agents.py` (requires PyYAML). The script checks `.github/agents/`.
- No test files or repository test/lint configuration are present. When a pytest test exists, run one with `pytest path/to/test_file.py::test_name`.

## Architecture

The core ATLAS flow is coordinated by `atlas/orchestrator.py`: raw OHLCV bars become a `StateSnapshot`; `ResearchAI` combines snapshot indicators, optional RAG context, and news into regime flags and event alerts; the orchestrator creates a `DecisionProposal`; `RiskVerdict` applies five checks; approved proposals go to `KiteAdapter`; and cycle results are recorded in the journal. Keep the Research AI separate from order placement, and preserve the risk gate between proposals and the broker adapter.

`StateSnapshot` is the model-facing market representation. Its indicators and regime features are computed in Python from bars shaped as `[timestamp, open, high, low, close, volume]`. `DecisionProposal` and `RiskVerdict` are the structured hand-offs between analysis, risk, and execution; all five checks (`size_ok`, `loss_ok`, `hours_ok`, `symbol_ok`, `confidence_ok`) must pass before execution.

`atlas/journal.py` stores JSONL records under `.journal/ledger.jsonl`; retain an audit trail for rejected as well as approved cycles. The `atlas/quant/` modules provide separate bar loaders, feature calculations, and strategy signals. The daily news/market scan in `scripts/daily_market_scan.py` is a separate workflow, scheduled by `.github/workflows/daily-market-scan.yml` to publish reports under `market-scan/`.

## Conventions

- Keep provider selection config-driven; `rule_based` is the default fallback. Provider-specific keys are read from environment variables in `atlas/research_ai.py`.
- Use `Asia/Kolkata` for market-time logic and timestamps; risk checks are constrained to NSE hours (09:15–15:30 IST).
- Preserve research-only and paper-trading behavior. `OrchestratorConfig` defaults `paper_trading` to `True`; changes to execution paths must continue to honor the risk verdict and this boundary.
- For the broader project roadmap and existing contributor context, consult the root `copilot-instructions.md` and `ATLAS_NEXT_STEPS.md`; the README is the reference for setup and the system overview.
