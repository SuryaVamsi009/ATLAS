# ATLAS: Next 5–7 Steps to Move Forward
## Prioritized list, most urgent first

---

## Step 1: Integrate Journal Ledger with Orchestrator `run_cycle`
**What to build:** Connect the existing `atlas/journal.py` module to the `Orchestrator.run_cycle()` method so that every complete cycle (Research → Decision → Risk → Order → Fill → P&L) writes a structured ledger entry. The orchestrator currently computes and processes all steps but discards the results without journal persistence.

**Why it matters now:** The Two-AI journal-ledger protocol (Step 3 of the forward plan) is the backbone of the Research/Agent boundary. Without journal entries, there is no audit trail, no confidence calibration data, and no mechanism for weekly review (Step 5). The user mentioned "a call journal for learning from past results" — this step actualizes that.

**Dependencies and rough effort:**
- Modify `atlas/orchestrator.py`: `_create_journal_entry()` call at the end of `run_cycle()` after order fill
- Import `write_regime_entry`, `write_decision_proposal_entry`, `write_risk_verdict_entry`, `write_order_result_entry` from `atlas/journal`
- Estimated effort: 2-3 hours

**Risk of doing it too early (or skipping it):** No audit trail for past trades; impossible to surface calibration drift; no learning loop from past results. The system becomes stateless between cycles.

**Concrete question before starting:** Should the journal entry be written only for approved trades, or for all cycles including risk-rejected ones? (Recommended: write all, with a "step" field indicating "risk_rejection", "approved_trade", or "execution_failure")

---

## Step 2: Add Rate Limit Handling & Retry Logic to Scheduled Orchestrator
**What to build:** Implement exponential backoff with jitter and a maximum retry count in the orchestrator's scheduled execution path. Track API call counts per cycle and surface rate-limit errors in the journal. Add a `max_api_calls_per_cycle` config and a `rate_limit_backoff_factor` config.

**Why it matters now:** The user explicitly stated "rate limits hit on scheduled jobs" as the current pain point. Without rate limit handling, the scheduled job will continue to fail, causing downtime in the research-agent deployment on Oracle/AMD cloud.

**Dependencies and rough effort:**
- Add config fields to `OrchestratorConfig`: `max_api_calls_per_cycle` (default 10), `rate_limit_backoff_factor` (default 2.0), `rate_limit_max_retries` (default 3)
- Modify `Orchestrator.run_cycle()` to count API calls (KiteAdapter, ResearchAI, RAG) and trigger backoff on 429 responses
- Add `atlas/scheduler.py` new module or extend existing orchestrator with `execute_with_rate_limit_protection()` helper
- Estimated effort: 3-4 hours

**Risk of doing it too early (or skipping it):** Recurring scheduled job failures; potential account restrictions from Kite/CLOUD API; wasted compute cycles on retry storms.

**Concrete question before starting:** Should rate limit protection be per-cycle (reset each run) or cumulative (track across runs within a day)? (Recommended: per-cycle reset for simplicity, with daily reset option via cron)

---

## Step 3: Enhance Research AI with LLM Provider Integration
**What to build:** Extend `atlas/research_ai.py`'s `ConfigDrivenResearchAI` to support actual LLM providers (OpenAI, Anthropic, Gemini) through a common interface, while keeping the rule-based fallback. Add `ai_provider` and `model_name` config options that map to provider-specific API calls. The `analyze()` method should first attempt RAG-augmented generation, then fall back to rule-based regime detection.

**Why it matters now:** Currently the Research AI is purely rule-based (`rsi > 70 → overbought`, etc.). The user mentioned "research agent deployed via free LLM services on cloud (Oracle/AMD)" — this step actualizes the LLM integration while maintaining the model-agnostic design pattern already established in the codebase.

**Dependencies and rough effort:**
- Add `ai_provider` enum ("openai", "anthropic", "gemini", "rule_based") to `ConfigDrivenResearchAI.__init__()`
- Add provider-specific API key/config handling
- Modify `analyze()` to use provider LLM for regime/thesis generation when provider != "rule_based"
- Keep rule-based fallback as default for robustness
- Estimated effort: 4-5 hours

**Risk of doing it too early (or skipping it):** System remains stuck in rule-based regime detection only; cannot leverage LLM reasoning for complex market analysis; user's Oracle/AMD LLM deployment goes unused.

**Concrete question before starting:** Which LLM provider should be the first supported? (Recommended: OpenAI gpt-4o-minimum for cost-effectiveness, with Gemini 1.5 Flash as alternative)

---

## Step 4: Complete Paper Trading End-to-End Verification
**What to build:** Build a verification script that runs one full orchestrator cycle in paper trading mode, capturing all outputs: StateSnapshot, regime flags, DecisionProposal, RiskVerdict, KiteAdapter order result, and journal entry. The script should validate that: (a) RiskVerdict approved → order placed; (b) order result (filled/partial/cancelled) written to journal; (c) P&L calculated and stored.

**Why it matters now:** The KiteAdapter, RiskVerdict, and orchestrator all exist in isolation. There is no verified end-to-end flow from RiskVerdict → KiteAdapter → journal. The user needs confidence that the full 6-layer architecture works before moving to live trading (which is prohibited by the research-only constraint).

**Dependencies and rough effort:**
- Create `atlas/tests/test_paper_trade.py` new test file
- Instantiate `Orchestrator` with paper_trading=True
- Run `run_cycle()` with sample market data and news context
- Validate journal entry written and P&L computed
- Estimated effort: 3-4 hours

**Risk of doing it too early (or skipping it):** Unknown failure points in the full cycle; cannot trust the system for even paper trading; debugging distributed across 6 modules instead of one integrated flow.

**Concrete question before starting:** What sample market data should the verification use? (Recommended: 6 months of Nifty 1-hour yfinance data, pre-computed into StateSnapshot format)

---

## Step 5: Implement Confidence Calibration Pipeline
**What to build:** Connect the `atlas/eval_pipeline.py` `run_evaluation_pipeline()` to read from the journal ledger (instead of generating fresh yfinance data). Surface confidence calibration drift per bin, hit rates by confidence range, and r_multiple averages. Output a weekly calibration report that answers: "Is the system over-confident or under-confident, and which confidence bins are miscalibrated?"

**Why it matters now:** This is Step 5 of the ATLAS forward plan. The user wants "confidence calibration" for learning from past results. Without this, there is no mechanism to detect when the Research AI's confidence scores don't match actual hit rates — a critical failure mode for any trading system.

**Dependencies and rough effort:**
- Modify `run_evaluation_pipeline()` to accept `use_fresh_data=False` and read from journal ledger
- Add `atlas/journal.py` `get_ledger_entries()` and `get_ledger_stats()` (already exist)
- Connect eval pipeline to read regime_flags, confidence, and outcomes from journal
- Generate weekly calibration report format
- Estimated effort: 3-4 hours

**Risk of doing it too early (or skipping it):** No visibility into confidence calibration drift; system may be over-confident (common in trading) without detection; inability to adjust confidence binning for improved decision-making.

**Concrete question before starting:** Should calibration use journal P&L as the ground truth, or the `grade_outcome()` mechanical grading from eval_set.py? (Recommended: use journal P&L for real-world calibration, with eval_set mechanical grading as a secondary cross-check)

---

## Step 6: Add Indian Market Pattern Query to Research AI
**What to build:** Integrate the pre-seeded Indian market patterns and regimes from `atlas/rag_corpus.py` into the `ConfigDrivenResearchAI.analyze()` method. When the RAG corpus is queried, the research AI should incorporate pattern-matched regime descriptions and event templates into its output regime_flags and event_alerts. The current rule-based detection should be supplemented (not replaced) by RAG-informed flags.

**Why it matters now:** The RAG corpus has 12+ Indian market regimes and patterns pre-seeded (trending_up, choppy, reversal, breakout, high_vol_panic, mean_reversion_oversold, sector_rotation_it_leading, earnings_volatility, etc.), but the Research AI never queries them. This step bridges the gap between the corpus and the agent, making the research agent "India-aware" without hard-coding market specifics.

**Dependencies and rough effort:**
- Modify `ConfigDrivenResearchAI.analyze()` to call `rag_corpus.get_regime_profile()` and `rag_corpus.get_event_template()`
- Weight RAG results with `rag_weight` config (0.0-1.0, default 0.3 to keep rule-based dominance)
- Ensure rule-based fallback remains when RAG returns None
- Estimated effort: 2-3 hours

**Risk of doing it too early (or skipping it):** RAG corpus remains unused "shelfware"; research agent doesn't benefit from 12+ pre-seeded Indian market patterns; missed opportunity to improve regime detection with historical context.

**Concrete question before starting:** What should the default `rag_weight` be? (Recommended: 0.3 — rule-based dominant, RAG as supplementary enhancement; user can increase to 0.7+ once comfortable)

---

## Step 7: Create Monitoring & Alerting for Scheduled Orchestration Cycles
**What to build:** Implement a monitoring dashboard (or CLI output) that tracks per-cycle metrics: cycle duration, API call counts, success/failure rates, rate-limit triggers, veto reasons distribution, and P&L summary. Output should be writable to journal and also displayable as a short CLI summary. Add alerts for: (a) consecutive cycle failures; (b) increasing veto_reason frequency (e.g., size_ok violations growing); (c) confidence calibration drift exceeding threshold.

**Why it matters now:** The user mentioned "rate limits hit on scheduled jobs" and this step provides the observability to diagnose, alert, and optimize. Without monitoring, the system operates as a black box — each scheduled run either succeeds or fails silently, with no insight into why or how to improve.

**Dependencies and rough effort:**
- Add metrics tracking to `Orchestrator.run_cycle()`: start_time, end_time, api_call_count, risk_verdict.approved rate, veto_reason distribution
- Modify `atlas/journal.py` `get_ledger_stats()` to include cycle-level metrics
- Add `atlas/monitor.py` new module or extend orchestrator with `get_cycle_metrics()` 
- Estimated effort: 3-4 hours

**Risk of doing it too early (or skipping it):** No observability into scheduled job health; failures go undetected until user complaints; cannot distinguish between "market conditions bad" vs "code bugs" vs "API rate limits".

**Concrete question before starting:** Should monitoring output be a JSON file, a CLI summary, or both? (Recommended: both — JSON file for programmatic analysis, CLI summary for quick checks)

---

## Summary: Recommended Order of Execution

Given the research-only constraint and the need to surface real-market failure modes, the recommended order is:

1. **Step 1** — Journal ledger (foundation for all subsequent steps; enables learning)
2. **Step 2** — Rate limit handling (immediate pain point; prevents recurring failures)
3. **Step 5** — Confidence calibration (critical feedback loop for system improvement)
4. **Step 6** — Indian market patterns (leverages existing RAG corpus investment)
5. **Step 3** — LLM provider integration (enhance but not replace rule-based foundation)
6. **Step 4** — Paper trading verification (validate end-to-end before any live consideration)
7. **Step 7** — Monitoring & alerting (observability for sustained operation)

**Most urgent concrete question to answer first:** *Should the journal write entries for all cycles (including risk-rejected ones), or only for approved trades?* This determines the data model for Step 1 and cascades through all subsequent steps.
