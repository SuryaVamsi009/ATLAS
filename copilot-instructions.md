# ATLAS - Copilot Instructions

## Project Overview
ATLAS is an AI-driven trading system for the Indian market (stocks and F&O) with two agents:
- **Research Agent**: Analyzes markets, news, and sentiment; produces buy/sell/hold calls with confidence scores
- **Acting Agent**: Observes the market and executes trades

**Current State**: Research agent deployed via free LLM services on cloud (Oracle/AMD), call journal for learning from past results, rate limits hit on scheduled jobs.

**Constraint**: Research-only (no live trading)

## Two-AI Architecture Boundary
The system enforces a strict Two-AI boundary:

```
Research AI → Journal Ledger → Agent AI → RiskVerdict → KiteAdapter → Execution
```

Key principles:
- Research AI never places orders directly
- All flow goes through the journal ledger (append-only JSONL)
- RiskVerdict 5 checks must all pass for approval
- StateSnapshot is the ONLY thing the model ever sees; all values computed in Python

## 6-Layer Architecture
| Layer | Component | Description |
|-------|-----------|-------------|
| L1 | Data Ingestion | Market data, news feeds, sentiment sources |
| L2 | RAG Corpus | 12 Indian market regimes + 12 patterns (atlas/rag_corpus.py) |
| L3 | Research AI | ConfigDrivenResearchAI.analyze() - regime/alerts/thesis generation |
| L4 | DecisionProposal + RiskVerdict | Decision proposal + 5-check risk verification |
| L5 | KiteAdapter | ZERODHA Kite Connect order execution |
| L6 | Journal Ledger | Append-only JSONL with complete cycle audit trail |

## Journal-Ledger Protocol
Every complete cycle writes a structured ledger entry with these fields:
- `entry_id`: Unique identifier
- `timestamp_ist`: IST timestamp
- `snapshot_id`: Reference to frozen StateSnapshot
- `regime_flags`: Detected market regimes
- `event_alerts`: Generated event alerts
- `thesis`: Research thesis/rationale
- `decision_proposal`: Buy/sell/hold call with confidence score
- `risk_verdict`: Pass/fail from 5 checks (size_ok, loss_ok, hours_ok, symbol_ok, confidence_ok)
- `order_result`: Filled/partial/cancelled/rejected
- `pnl`: Profit/loss from executed trade
- `confidence_calibration`: Calibration data for learning

## Current Configuration
- **Default rag_weight**: 0.3 (rule-based dominant, RAG supplementary)
- **LLM provider start**: OpenAI gpt-4o-mini (cost-effective)
- **RiskVerdict checks**: 5 must all pass (size_ok, loss_ok, hours_ok, symbol_ok, confidence_ok)
- **Monitoring output**: Both JSON file and CLI summary

## Prioritized Next Steps (from ATLAS_NEXT_STEPS.md)
1. **Step 1**: Journal Integration with Orchestrator.run_cycle()
2. **Step 2**: Rate Limit Handling & Retry Logic
3. **Step 3**: LLM Provider Integration
4. **Step 4**: Paper Trading End-to-End Verification
5. **Step 5**: Confidence Calibration Pipeline
6. **Step 6**: Indian Market Patterns in Research AI
7. **Step 7**: Monitoring & Alerting for Scheduled Orchestration

## Code Ownership
| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `atlas/orchestrator.py` | Wires all 6 layers; `run_cycle()` method | `_create_journal_entry()`, `_build_risk_context()`, `_place_order()` |
| `atlas/journal.py` | Two-AI journal-ledger protocol | `write_regime_entry()`, `write_decision_proposal_entry()`, etc. |
| `atlas/research_ai.py` | ConfigDrivenResearchAI.analyze() | `analyze()`, `rag_weight`, `min_confidence` |
| `atlas/rag_corpus.py` | 12 Indian market regimes + 12 patterns | `_init_indian_regimes()`, `_init_indian_patterns()` |
| `atlas/decision_proposal.py` | DecisionProposal dataclass | The ONLY output Research AI produces |
| `atlas/risk_verdict.py` | 5-check risk verification | `RiskVerdict` - all checks must pass |
| `atlas/state_snapshot.py` | Frozen dataclass - model input | The ONLY thing the model ever sees |
| `atlas/brokers/kite_adapter.py` | Kite Connect adapter | Order placement, status checking |
| `atlas/eval_pipeline.py` | Evaluation pipeline, confidence calibration | `run_evaluation_pipeline()`, `grade_outcome()` |
| `atlas/eval_set.py` | Outcome grading, mechanical call grading | Mechanical call grading logic |

## Development Guidelines
- **Model-agnostic design**: Changing AI provider only requires config update, not logic changes
- **Rule-based fallback**: Always keep rule-based regime detection as default for robustness
- **Journal writes ALL cycles**: Including risk-rejected, for complete audit trail
- **Per-cycle rate limit protection**: Reset each run, with daily reset option via cron
- **Concrete questions before starting**: Each step has a specific question to answer before implementation

## MCP Server Integration
- **Atlassian MCP server**: For Jira issue creation (requires OAuth authentication)
- **GitHub MCP server**: For repository operations and issue artifact attachment
- **Notion MCP server**: For documentation management (if needed)

## Quick Start for New Contributors
1. Read `atlas/orchestrator.py` to understand the cycle flow
2. Read `atlas/journal.py` to understand the ledger protocol
3. Read `atlas/research_ai.py` to understand the research agent design
4. Review `ATLAS_NEXT_STEPS.md` for the prioritized roadmap
5. Start with Step 1: Journal Integration (foundation for all other steps)