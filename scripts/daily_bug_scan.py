#!/usr/bin/env python3
"""
Daily Bug Scanner for ATLAS - Implements Pacman's 8 bug class detectors.
Runs in GitHub Actions to find bugs and create issues for Ben.
"""
import os
import sys
import json
import subprocess
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any
from dataclasses import dataclass, asdict

# Add atlas to path
sys.path.insert(0, str(Path(__file__).parent.parent))

@dataclass
class BugReport:
    """Structured bug report for GitHub issue creation."""
    title: str
    body: str
    labels: List[str]
    assignees: List[str]
    layer: str
    bug_class: str
    severity: str
    file_path: str
    line_numbers: List[int]
    evidence: str
    suggested_fix: str

class BugScanner:
    """Pacman's systematic bug scanner - 8 bug class detectors."""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.atlas_root = repo_root / "atlas"
        self.bugs: List[BugReport] = []
        
    def scan_all(self) -> List[BugReport]:
        """Run all 8 bug class detectors across L1-L6."""
        print("🔍 Pacman: Starting systematic bug scan...")
        
        # Layer 1: Data Ingestion
        self._scan_layer1_data_ingestion()
        
        # Layer 2: StateSnapshot
        self._scan_layer2_state_snapshot()
        
        # Layer 3: Research AI
        self._scan_layer3_research_ai()
        
        # Layer 4: Risk & Decisions
        self._scan_layer4_risk_decisions()
        
        # Layer 5: Orchestrator/Execution
        self._scan_layer5_orchestrator()
        
        # Layer 6: Journal/Eval
        self._scan_layer6_journal_eval()
        
        # Cross-cutting: Config & Tests
        self._scan_config_tests_impl()
        
        print(f"✅ Pacman: Scan complete. Found {len(self.bugs)} bugs.")
        return self.bugs
    
    def _add_bug(self, bug: BugReport):
        self.bugs.append(bug)
        print(f"  🐛 Found: {bug.title} [{bug.severity}] in {bug.file_path}")
    
    # ========== BUG CLASS 1: Import & Dependency Bugs ==========
    def _scan_imports(self, file_path: Path, layer: str):
        """Detect non-package imports, sys.path hacks, heavy imports at module level."""
        content = file_path.read_text()
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Non-package imports (from module import vs from atlas.module import)
            if re.match(r'^from\s+(?!atlas\.)\w+\s+import', stripped) and not stripped.startswith('#'):
                if 'atlas' in str(file_path) and not any(x in stripped for x in ['typing', 'datetime', 'dataclasses', 'enum', 'functools', 'collections', 'pathlib', 'json', 'logging', 'zoneinfo']):
                    self._add_bug(BugReport(
                        title=f"Non-package import in {file_path.name}:{i}",
                        body=f"Found non-package import in `{file_path.relative_to(self.repo_root)}` line {i}:\n```python\n{line}\n```\n\n**Fix**: Change to package import `from atlas.module import ...`",
                        labels=["bug", "imports", f"layer-{layer}"],
                        assignees=["SuryaVamsi009"],
                        layer=layer,
                        bug_class="imports",
                        severity="high",
                        file_path=str(file_path.relative_to(self.repo_root)),
                        line_numbers=[i],
                        evidence=line,
                        suggested_fix="Use package imports: `from atlas.module import ...`"
                    ))
            
            # sys.path hacks
            if 'sys.path' in stripped and ('insert' in stripped or 'append' in stripped):
                self._add_bug(BugReport(
                    title=f"sys.path hack in {file_path.name}:{i}",
                    body=f"Found sys.path manipulation in `{file_path.relative_to(self.repo_root)}` line {i}:\n```python\n{line}\n```\n\n**Fix**: Remove sys.path hack, use proper package imports",
                    labels=["bug", "imports", f"layer-{layer}"],
                    assignees=["SuryaVamsi009"],
                    layer=layer,
                    bug_class="imports",
                    severity="high",
                    file_path=str(file_path.relative_to(self.repo_root)),
                    line_numbers=[i],
                    evidence=line,
                    suggested_fix="Remove sys.path hack, use proper package structure"
                ))
            
            # Heavy imports at module level (yfinance, pandas, etc.)
            if any(imp in stripped for imp in ['import yfinance', 'import pandas', 'import pyarrow', 'import numpy']) and i < 50:
                # Check if it's at module level (not inside function)
                indent = len(line) - len(line.lstrip())
                if indent == 0:
                    self._add_bug(BugReport(
                        title=f"Heavy import at module level in {file_path.name}:{i}",
                        body=f"Found heavy import at module level in `{file_path.relative_to(self.repo_root)}` line {i}:\n```python\n{line}\n```\n\n**Fix**: Move import inside the function that uses it",
                        labels=["bug", "imports", "performance", f"layer-{layer}"],
                        assignees=["SuryaVamsi009"],
                        layer=layer,
                        bug_class="imports",
                        severity="medium",
                        file_path=str(file_path.relative_to(self.repo_root)),
                        line_numbers=[i],
                        evidence=line,
                        suggested_fix="Move import inside the function that uses it"
                    ))
    
    # ========== BUG CLASS 2: Timezone Bugs ==========
    def _scan_timezone(self, file_path: Path, layer: str):
        """Detect +5:30 hacks, timestamp_ist, naive datetimes."""
        content = file_path.read_text()
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # +5:30 hack
            if '+5:30' in stripped or '+05:30' in stripped:
                self._add_bug(BugReport(
                    title=f"Hardcoded +5:30 timezone offset in {file_path.name}:{i}",
                    body=f"Found hardcoded timezone offset in `{file_path.relative_to(self.repo_root)}` line {i}:\n```python\n{line}\n```\n\n**Fix**: Use `zoneinfo.ZoneInfo('Asia/Kolkata')` for timezone-aware datetimes",
                    labels=["bug", "timezone", f"layer-{layer}"],
                    assignees=["SuryaVamsi009"],
                    layer=layer,
                    bug_class="timezone",
                    severity="high",
                    file_path=str(file_path.relative_to(self.repo_root)),
                    line_numbers=[i],
                    evidence=line,
                    suggested_fix="Use `zoneinfo.ZoneInfo('Asia/Kolkata')`"
                ))
            
            # timestamp_ist mislabeling
            if 'timestamp_ist' in stripped.lower() and 'zoneinfo' not in content:
                self._add_bug(BugReport(
                    title=f"Mislabelled timestamp_ist without zoneinfo in {file_path.name}:{i}",
                    body=f"Found `timestamp_ist` variable in `{file_path.relative_to(self.repo_root)}` line {i} without proper timezone handling:\n```python\n{line}\n```\n\n**Fix**: Use timezone-aware datetimes with `zoneinfo.ZoneInfo('Asia/Kolkata')`",
                    labels=["bug", "timezone", f"layer-{layer}"],
                    assignees=["SuryaVamsi009"],
                    layer=layer,
                    bug_class="timezone",
                    severity="high",
                    file_path=str(file_path.relative_to(self.repo_root)),
                    line_numbers=[i],
                    evidence=line,
                    suggested_fix="Use timezone-aware datetimes with zoneinfo"
                ))
            
            # datetime.now() without timezone
            if 'datetime.now()' in stripped and 'timezone' not in stripped and 'zoneinfo' not in stripped:
                self._add_bug(BugReport(
                    title=f"Naive datetime.now() in {file_path.name}:{i}",
                    body=f"Found naive `datetime.now()` in `{file_path.relative_to(self.repo_root)}` line {i}:\n```python\n{line}\n```\n\n**Fix**: Use `datetime.now(ZoneInfo('Asia/Kolkata'))`",
                    labels=["bug", "timezone", f"layer-{layer}"],
                    assignees=["SuryaVamsi009"],
                    layer=layer,
                    bug_class="timezone",
                    severity="medium",
                    file_path=str(file_path.relative_to(self.repo_root)),
                    line_numbers=[i],
                    evidence=line,
                    suggested_fix="Use `datetime.now(ZoneInfo('Asia/Kolkata'))`"
                ))
    
    # ========== BUG CLASS 3: StateSnapshot/RSI Bugs ==========
    def _scan_rsi(self, file_path: Path, layer: str):
        """Detect RSI calculation bugs."""
        content = file_path.read_text()
        
        # Check for Wilder RSI over first 14 bars instead of latest 14
        if 'rsi' in content.lower() and 'state_snapshot' in str(file_path).lower():
            if '[:14]' in content or '[0:14]' in content:
                self._add_bug(BugReport(
                    title="RSI computed over first 14 bars instead of latest 14",
                    body=f"RSI calculation in `{file_path.relative_to(self.repo_root)}` uses first 14 bars (`[:14]`) instead of latest 14 bars (`[-14:]`).\n\n**Fix**: Change slice to `[-14:]` for Wilder RSI over latest bars.",
                    labels=["bug", "rsi", "state_snapshot", f"layer-{layer}"],
                    assignees=["SuryaVamsi009"],
                    layer=layer,
                    bug_class="rsi",
                    severity="critical",
                    file_path=str(file_path.relative_to(self.repo_root)),
                    line_numbers=[],
                    evidence="RSI slice uses `[:14]` (first bars) instead of `[-14:]` (latest bars)",
                    suggested_fix="Change `closes[:14]` to `closes[-14:]` for Wilder RSI"
                ))
            
            # Check for avg_loss == 0 returning 0 instead of 100
            if 'avg_loss == 0' in content or 'average_loss == 0' in content:
                if 'return 0' in content or 'return 0.0' in content:
                    self._add_bug(BugReport(
                        title="RSI returns 0 when avg_loss is 0 (should return 100)",
                        body=f"RSI calculation in `{file_path.relative_to(self.repo_root)}` returns 0 when average loss is 0. Correct Wilder RSI should return 100.\n\n**Fix**: Return 100 when avg_loss == 0",
                        labels=["bug", "rsi", "state_snapshot", f"layer-{layer}"],
                        assignees=["SuryaVamsi009"],
                        layer=layer,
                        bug_class="rsi",
                        severity="critical",
                        file_path=str(file_path.relative_to(self.repo_root)),
                        line_numbers=[],
                        evidence="avg_loss == 0 returns 0 instead of 100",
                        suggested_fix="Return 100 when average loss is 0"
                    ))
    
    # ========== BUG CLASS 4: RiskVerdict Bugs ==========
    def _scan_risk_verdict(self, file_path: Path, layer: str):
        """Detect RiskVerdict bugs: VetoReason.__bool__, risk calc, final_qty."""
        content = file_path.read_text()
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Inverted VetoReason.__bool__
            if '__bool__' in stripped and 'VetoReason' in content:
                if 'return self != VetoReason.NONE' in stripped or 'return self is not VetoReason.NONE' in stripped:
                    # This is actually correct - but check for inverted
                    pass
                elif 'return self == VetoReason.NONE' in stripped:
                    self._add_bug(BugReport(
                        title="Inverted VetoReason.__bool__ implementation",
                        body=f"Found inverted `__bool__` in `VetoReason` enum in `{file_path.relative_to(self.repo_root)}` line {i}:\n```python\n{line}\n```\n\n**Fix**: `__bool__` should return `self != VetoReason.NONE`",
                        labels=["bug", "risk_verdict", "veto", f"layer-{layer}"],
                        assignees=["SuryaVamsi009"],
                        layer=layer,
                        bug_class="risk_verdict",
                        severity="critical",
                        file_path=str(file_path.relative_to(self.repo_root)),
                        line_numbers=[i],
                        evidence=line,
                        suggested_fix="Change `__bool__` to return `self != VetoReason.NONE`"
                    ))
            
            # Risk calculation: (entry - stop) * quantity
            if 'risk' in stripped.lower() and 'entry' in stripped and 'stop' in stripped:
                if '*' not in stripped and 'quantity' not in stripped and 'qty' not in stripped:
                    self._add_bug(BugReport(
                        title="Risk calculation missing quantity multiplier",
                        body=f"Risk calculation in `{file_path.relative_to(self.repo_root)}` line {i} appears to compute `(entry - stop)` without multiplying by quantity:\n```python\n{line}\n```\n\n**Fix**: Risk should be `(entry - stop) * quantity`",
                        labels=["bug", "risk_verdict", "risk_calc", f"layer-{layer}"],
                        assignees=["SuryaVamsi009"],
                        layer=layer,
                        bug_class="risk_verdict",
                        severity="high",
                        file_path=str(file_path.relative_to(self.repo_root)),
                        line_numbers=[i],
                        evidence=line,
                        suggested_fix="Multiply by quantity: `(entry - stop) * quantity`"
                    ))
            
            # final_qty as rupee amount instead of whole shares
            if 'final_qty' in stripped or 'final_quantity' in stripped:
                if '/' in stripped and 'price' in stripped.lower():
                    if 'floor' not in stripped and 'int(' not in stripped:
                        self._add_bug(BugReport(
                            title="final_qty computed as rupee amount instead of whole shares",
                            body=f"Quantity calculation in `{file_path.relative_to(self.repo_root)}` line {i} divides notional by price without flooring:\n```python\n{line}\n```\n\n**Fix**: Use `floor(notional / price)` for whole shares",
                            labels=["bug", "risk_verdict", "quantity", f"layer-{layer}"],
                            assignees=["SuryaVamsi009"],
                            layer=layer,
                            bug_class="risk_verdict",
                            severity="high",
                            file_path=str(file_path.relative_to(self.repo_root)),
                            line_numbers=[i],
                            evidence=line,
                            suggested_fix="Use `math.floor(notional / price)` for whole shares"
                        ))
    
    # ========== BUG CLASS 5: Journal Bugs ==========
    def _scan_journal(self, file_path: Path, layer: str):
        """Detect Journal bugs: in-memory only, missing JSONL, timezone."""
        content = file_path.read_text()
        
        # Check if journal writes to JSONL
        if 'journal' in str(file_path).lower() or 'Journal' in content:
            if 'jsonl' not in content.lower() and '.jsonl' not in content:
                self._add_bug(BugReport(
                    title="Journal missing JSONL persistence",
                    body=f"Journal in `{file_path.relative_to(self.repo_root)}` appears to only use in-memory storage without JSONL persistence.\n\n**Fix**: Add JSONL file writing for append-only ledger",
                    labels=["bug", "journal", "persistence", f"layer-{layer}"],
                    assignees=["SuryaVamsi009"],
                    layer=layer,
                    bug_class="journal",
                    severity="high",
                    file_path=str(file_path.relative_to(self.repo_root)),
                    line_numbers=[],
                    evidence="No JSONL file writing found in journal",
                    suggested_fix="Add append-only JSONL ledger writing"
                ))
    
    # ========== BUG CLASS 6: Orchestrator Bugs ==========
    def _scan_orchestrator(self, file_path: Path, layer: str):
        """Detect Orchestrator bugs: api_call_count, missing imports, stop_price."""
        content = file_path.read_text()
        lines = content.split('\n')
        
        # Check for missing import time once per file
        if ('time.sleep' in content or 'time.time' in content) and 'import time' not in content:
            self._add_bug(BugReport(
                title="Missing `import time` for time.sleep/time.time usage",
                body=f"File `{file_path.relative_to(self.repo_root)}` uses `time.` functions but missing `import time`",
                labels=["bug", "orchestrator", "imports", f"layer-{layer}"],
                assignees=["SuryaVamsi009"],
                layer=layer,
                bug_class="orchestrator",
                severity="medium",
                file_path=str(file_path.relative_to(self.repo_root)),
                line_numbers=[],
                evidence="time.sleep or time.time used without import",
                suggested_fix="Add `import time` at module level"
            ))
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # api_call_count NameError
            if 'api_call_count' in stripped and 'self.api_call_count' not in stripped:
                if 'api_call_count' in content and 'self.api_call_count' not in content:
                    self._add_bug(BugReport(
                        title="api_call_count used as local variable (NameError risk)",
                        body=f"Found `api_call_count` used without `self.` prefix in `{file_path.relative_to(self.repo_root)}` line {i}:\n```python\n{line}\n```\n\n**Fix**: Make it an instance attribute `self.api_call_count`",
                        labels=["bug", "orchestrator", "api_call_count", f"layer-{layer}"],
                        assignees=["SuryaVamsi009"],
                        layer=layer,
                        bug_class="orchestrator",
                        severity="high",
                        file_path=str(file_path.relative_to(self.repo_root)),
                        line_numbers=[i],
                        evidence=line,
                        suggested_fix="Use `self.api_call_count` as instance attribute"
                    ))
            
            # Missing stop_price in _place_order
            if '_place_order' in content and 'stop_price' not in content and 'stop_hint' not in content:
                self._add_bug(BugReport(
                    title="_place_order missing stop_price/stop_hint parameter",
                    body=f"Orchestrator's `_place_order` method in `{file_path.relative_to(self.repo_root)}` doesn't accept or pass `stop_price` for ATR-based stops.\n\n**Fix**: Add `stop_price` parameter and pass to broker adapter",
                    labels=["bug", "orchestrator", "stops", f"layer-{layer}"],
                    assignees=["SuryaVamsi009"],
                    layer=layer,
                    bug_class="orchestrator",
                    severity="high",
                    file_path=str(file_path.relative_to(self.repo_root)),
                    line_numbers=[],
                    evidence="No stop_price parameter in _place_order",
                    suggested_fix="Add stop_price parameter to _place_order and pass to broker"
                ))
    
    # ========== BUG CLASS 7: Eval/Metrics Bugs ==========
    def _scan_eval_metrics(self, file_path: Path, layer: str):
        """Detect eval_set bugs: hits/total_r not incremented, wrong denominators."""
        content = file_path.read_text()
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # hits/total_r not incremented in loop
            if 'compute_metrics' in content or 'hits' in content:
                if 'for ' in content and 'hits' in content:
                    # Check if hits is incremented inside loop
                    loop_start = -1
                    for j, l in enumerate(lines):
                        if 'for ' in l and 'in ' in l:
                            loop_start = j
                        if loop_start >= 0 and j > loop_start:
                            if 'hits' in l and ('+=' in l or 'hits =' in l):
                                break
                            if j - loop_start > 20:  # loop too long without increment
                                self._add_bug(BugReport(
                                    title="hits/total_r not incremented inside compute_metrics loop",
                                    body=f"In `{file_path.relative_to(self.repo_root)}`, `hits` and `total_r` counters appear not to be incremented inside the evaluation loop.\n\n**Fix**: Increment `hits` and `total_r` inside the loop for each evaluated proposal",
                                    labels=["bug", "eval_set", "metrics", f"layer-{layer}"],
                                    assignees=["SuryaVamsi009"],
                                    layer=layer,
                                    bug_class="eval_metrics",
                                    severity="high",
                                    file_path=str(file_path.relative_to(self.repo_root)),
                                    line_numbers=[],
                                    evidence="Counters not incremented in loop",
                                    suggested_fix="Increment hits and total_r inside evaluation loop"
                                ))
                                break
            
            # Wrong denominators for intraday/swing averages
            if 'intraday' in content.lower() and 'swing' in content.lower():
                if '/ len(' in content:
                    # Check if both use same denominator
                    pass
    
    # ========== BUG CLASS 8: Test & Config Gaps ==========
    def _scan_config_tests(self, file_path: Path = None, layer: str = "config"):
        """Detect missing pyproject.toml, .gitignore, CI, tests."""
        # Prevent recursion - only run once
        if hasattr(self, '_config_tests_scanned'):
            return
        self._config_tests_scanned = True
        
        # Check pyproject.toml
        if not (self.repo_root / "pyproject.toml").exists():
            self._add_bug(BugReport(
                title="Missing pyproject.toml with dependencies",
                body="Repository lacks `pyproject.toml` listing dependencies (yfinance, pandas, pyarrow, pytest, etc.)\n\n**Fix**: Create pyproject.toml with all runtime and dev dependencies",
                labels=["task", "config", "dependencies"],
                assignees=["SuryaVamsi009"],
                layer="config",
                bug_class="config",
                severity="medium",
                file_path="pyproject.toml (missing)",
                line_numbers=[],
                evidence="No pyproject.toml found in repo root",
                suggested_fix="Create pyproject.toml with [project] dependencies"
            ))
        
        # Check .gitignore
        gitignore = self.repo_root / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text()
            for pattern in ['__pycache__/', '.journal/', '.DS_Store']:
                if pattern not in content:
                    self._add_bug(BugReport(
                        title=f".gitignore missing {pattern}",
                        body=f"`.gitignore` does not contain `{pattern}` pattern\n\n**Fix**: Add `{pattern}` to .gitignore",
                        labels=["task", "config", "gitignore"],
                        assignees=["SuryaVamsi009"],
                        layer="config",
                        bug_class="config",
                        severity="low",
                        file_path=".gitignore",
                        line_numbers=[],
                        evidence=f"Missing {pattern} in .gitignore",
                        suggested_fix=f"Add `{pattern}` to .gitignore"
                    ))
        else:
            self._add_bug(BugReport(
                title="Missing .gitignore file",
                body="Repository lacks `.gitignore` file\n\n**Fix**: Create .gitignore with standard Python patterns",
                labels=["task", "config", "gitignore"],
                assignees=["SuryaVamsi009"],
                layer="config",
                bug_class="config",
                severity="low",
                file_path=".gitignore (missing)",
                line_numbers=[],
                evidence="No .gitignore found",
                suggested_fix="Create .gitignore with __pycache__/, .journal/, .DS_Store"
            ))
        
        # Check CI workflow
        ci_workflow = self.repo_root / ".github" / "workflows" / "ci.yml"
        if not ci_workflow.exists():
            # Check for any pytest workflow
            workflows = list((self.repo_root / ".github" / "workflows").glob("*.yml"))
            has_pytest = any("pytest" in w.read_text() for w in workflows)
            if not has_pytest:
                self._add_bug(BugReport(
                    title="Missing CI workflow for pytest",
                    body="No GitHub Actions workflow runs pytest on push\n\n**Fix**: Add `.github/workflows/ci.yml` with pytest job",
                    labels=["task", "ci", "testing"],
                    assignees=["SuryaVamsi009"],
                    layer="config",
                    bug_class="config",
                    severity="medium",
                    file_path=".github/workflows/ci.yml (missing)",
                    line_numbers=[],
                    evidence="No pytest workflow found",
                    suggested_fix="Create CI workflow running pytest on push"
                ))
        
        # Check Phase 0 tests
        test_files = list(self.repo_root.glob("**/test*.py")) + list(self.repo_root.glob("**/*_test.py"))
        has_rsi_test = any("rsi" in f.read_text().lower() for f in test_files)
        has_compute_metrics_test = any("compute_metrics" in f.read_text().lower() for f in test_files)
        has_veto_test = any("veto" in f.read_text().lower() for f in test_files)
        
        if not has_rsi_test:
            self._add_bug(BugReport(
                title="Missing Phase 0 test: RSI on rising series equals 100",
                body="No pytest test verifying RSI returns 100 on a continuously rising price series\n\n**Fix**: Add test in `tests/test_state_snapshot.py`",
                labels=["task", "tests", "phase0", "rsi"],
                assignees=["SuryaVamsi009"],
                layer="tests",
                bug_class="tests",
                severity="medium",
                file_path="tests/test_state_snapshot.py (missing)",
                line_numbers=[],
                evidence="No RSI=100 test found",
                suggested_fix="Add test_rsi_rising_series_returns_100"
            ))
        
        if not has_compute_metrics_test:
            self._add_bug(BugReport(
                title="Missing Phase 0 test: compute_metrics hit rate on known set",
                body="No pytest test verifying compute_metrics calculates correct hit rate on known proposals\n\n**Fix**: Add test in `tests/test_eval_set.py`",
                labels=["task", "tests", "phase0", "eval_set"],
                assignees=["SuryaVamsi009"],
                layer="tests",
                bug_class="tests",
                severity="medium",
                file_path="tests/test_eval_set.py (missing)",
                line_numbers=[],
                evidence="No compute_metrics hit rate test found",
                suggested_fix="Add test_compute_metrics_hit_rate"
            ))
        
        if not has_veto_test:
            self._add_bug(BugReport(
                title="Missing Phase 0 test: rejected proposal journals veto reason",
                body="No pytest test verifying that a risk-rejected proposal records its veto reason in the journal\n\n**Fix**: Add test in `tests/test_risk_verdict.py` or `tests/test_journal.py`",
                labels=["task", "tests", "phase0", "risk_verdict", "journal"],
                assignees=["SuryaVamsi009"],
                layer="tests",
                bug_class="tests",
                severity="medium",
                file_path="tests/test_risk_verdict.py (missing)",
                line_numbers=[],
                evidence="No veto reason journaling test found",
                suggested_fix="Add test_veto_reason_journaled"
            ))
    
    # ========== LAYER SCANNERS ==========
    def _scan_layer1_data_ingestion(self):
        """Scan L1: Data Ingestion (kite_adapter, data loaders)."""
        print("  📥 Scanning Layer 1: Data Ingestion...")
        for file_path in (self.atlas_root / "brokers").glob("*.py"):
            self._scan_imports(file_path, "L1")
            self._scan_timezone(file_path, "L1")
        # New quant data module
        quant_data = self.repo_root / "atlas" / "quant" / "data.py"
        if quant_data.exists():
            self._scan_imports(quant_data, "L1")
            self._scan_timezone(quant_data, "L1")
    
    def _scan_layer2_state_snapshot(self):
        """Scan L2: StateSnapshot (RSI, indicators)."""
        print("  📊 Scanning Layer 2: StateSnapshot...")
        file_path = self.atlas_root / "state_snapshot.py"
        if file_path.exists():
            self._scan_imports(file_path, "L2")
            self._scan_timezone(file_path, "L2")
            self._scan_rsi(file_path, "L2")
    
    def _scan_layer3_research_ai(self):
        """Scan L3: Research AI (logger, model name)."""
        print("  🧠 Scanning Layer 3: Research AI...")
        file_path = self.atlas_root / "research_ai.py"
        if file_path.exists():
            self._scan_imports(file_path, "L3")
            content = file_path.read_text()
            if 'gpt-4o-minimum' in content:
                self._add_bug(BugReport(
                    title="Research AI uses incorrect model name 'gpt-4o-minimum'",
                    body=f"Found incorrect model name `gpt-4o-minimum` in `{file_path.relative_to(self.repo_root)}`\n\n**Fix**: Change to `gpt-4o-mini`",
                    labels=["bug", "research_ai", "model", "L3"],
                    assignees=["SuryaVamsi009"],
                    layer="L3",
                    bug_class="research_ai",
                    severity="medium",
                    file_path=str(file_path.relative_to(self.repo_root)),
                    line_numbers=[],
                    evidence="Model name 'gpt-4o-minimum' found",
                    suggested_fix="Change to 'gpt-4o-mini'"
                ))
            if 'logger = logging.getLogger(__name__)' not in content and 'import logging' not in content:
                self._add_bug(BugReport(
                    title="Research AI missing logger",
                    body=f"Research AI in `{file_path.relative_to(self.repo_root)}` missing `import logging` and `logger = logging.getLogger(__name__)`\n\n**Fix**: Add logger initialization",
                    labels=["bug", "research_ai", "logging", "L3"],
                    assignees=["SuryaVamsi009"],
                    layer="L3",
                    bug_class="research_ai",
                    severity="medium",
                    file_path=str(file_path.relative_to(self.repo_root)),
                    line_numbers=[],
                    evidence="No logger found",
                    suggested_fix="Add `import logging` and `logger = logging.getLogger(__name__)`"
                ))
    
    def _scan_layer4_risk_decisions(self):
        """Scan L4: Risk & Decisions (risk_verdict, rag_corpus)."""
        print("  ⚖️ Scanning Layer 4: Risk & Decisions...")
        for file_path in [self.atlas_root / "risk_verdict.py", self.atlas_root / "rag_corpus.py"]:
            if file_path.exists():
                self._scan_imports(file_path, "L4")
                self._scan_timezone(file_path, "L4")
                if file_path.name == "risk_verdict.py":
                    self._scan_risk_verdict(file_path, "L4")
                if file_path.name == "rag_corpus.py":
                    content = file_path.read_text()
                    if 'DecisionProposal' in content and 'TYPE_CHECKING' not in content:
                        self._add_bug(BugReport(
                            title="rag_corpus imports DecisionProposal at runtime (should be TYPE_CHECKING)",
                            body=f"`rag_corpus.py` imports `DecisionProposal` at runtime instead of under `TYPE_CHECKING`\n\n**Fix**: Move import under `if TYPE_CHECKING:`",
                            labels=["bug", "rag_corpus", "imports", "L4"],
                            assignees=["SuryaVamsi009"],
                            layer="L4",
                            bug_class="imports",
                            severity="medium",
                            file_path=str(file_path.relative_to(self.repo_root)),
                            line_numbers=[],
                            evidence="DecisionProposal imported at runtime",
                            suggested_fix="Move import under `if TYPE_CHECKING:`"
                        ))
    
    def _scan_layer5_orchestrator(self):
        """Scan L5: Orchestrator/Execution."""
        print("  🎭 Scanning Layer 5: Orchestrator...")
        file_path = self.atlas_root / "orchestrator.py"
        if file_path.exists():
            self._scan_imports(file_path, "L5")
            self._scan_timezone(file_path, "L5")
            self._scan_orchestrator(file_path, "L5")
    
    def _scan_layer6_journal_eval(self):
        """Scan L6: Journal/Eval."""
        print("  📓 Scanning Layer 6: Journal/Eval...")
        for file_path in [self.atlas_root / "journal.py", self.atlas_root / "eval_set.py"]:
            if file_path.exists():
                self._scan_imports(file_path, "L6")
                self._scan_timezone(file_path, "L6")
                if file_path.name == "journal.py":
                    self._scan_journal(file_path, "L6")
                if file_path.name == "eval_set.py":
                    self._scan_eval_metrics(file_path, "L6")
    
    def _scan_config_tests_impl(self):
        """Scan config and test gaps."""
        print("  ⚙️ Scanning Config & Tests...")
        self._scan_config_tests()


def create_github_issues(bugs: List[BugReport], dry_run: bool = False) -> List[Dict]:
    """Create GitHub issues for each bug using gh CLI."""
    created = []
    
    for bug in bugs:
        # Check if issue already exists (by title)
        check_cmd = ["gh", "issue", "list", "--search", f'"{bug.title}"', "--json", "number,title", "--limit", "5"]
        result = subprocess.run(check_cmd, capture_output=True, text=True)
        existing = json.loads(result.stdout) if result.stdout else []
        
        if existing:
            print(f"  ⏭️  Skipping (already exists): {bug.title}")
            continue
        
        # Build issue body with Pacman's structured format
        body = f"""{bug.body}

---
**Pacman Bug Report**
- **Layer**: {bug.layer}
- **Bug Class**: {bug.bug_class}
- **Severity**: {bug.severity}
- **File**: `{bug.file_path}`
- **Lines**: {bug.line_numbers if bug.line_numbers else 'N/A'}
- **Evidence**: {bug.evidence}
- **Suggested Fix**: {bug.suggested_fix}

**Assignment**: @SuryaVamsi009 (Ben - Bug Fix Specialist)
**Verification**: Pacman will verify fix after PR merge.

*Auto-generated by Pacman daily bug scan on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*
"""
        
        labels_str = ",".join(bug.labels)
        assignees_str = ",".join(bug.assignees) if bug.assignees else ""
        
        cmd = ["gh", "issue", "create", 
               "--title", bug.title,
               "--body", body,
               "--label", labels_str]
        
        if assignees_str:
            cmd.extend(["--assignee", assignees_str])
        
        if dry_run:
            print(f"  📝 [DRY RUN] Would create: {bug.title}")
            print(f"      Labels: {labels_str}")
            print(f"      Assignees: {assignees_str}")
            created.append({"title": bug.title, "dry_run": True})
        else:
            print(f"  📝 Creating issue: {bug.title}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                issue_url = result.stdout.strip()
                print(f"     ✅ Created: {issue_url}")
                created.append({"title": bug.title, "url": issue_url})
            else:
                print(f"     ❌ Failed: {result.stderr}")
                created.append({"title": bug.title, "error": result.stderr})
    
    return created


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pacman Daily Bug Scanner")
    parser.add_argument("--dry-run", action="store_true", help="Don't create issues, just report")
    parser.add_argument("--output", help="Output JSON file for bug reports")
    args = parser.parse_args()
    
    repo_root = Path(__file__).parent.parent
    scanner = BugScanner(repo_root)
    bugs = scanner.scan_all()
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump([asdict(b) for b in bugs], f, indent=2)
        print(f"\n📄 Bug reports saved to {args.output}")
    
    # Create GitHub issues
    if not args.dry_run:
        print("\n📝 Creating GitHub issues...")
        created = create_github_issues(bugs)
        print(f"\n✅ Created {len([c for c in created if 'url' in c])} new issues")
    else:
        print("\n📝 Dry run - no issues created")
        create_github_issues(bugs, dry_run=True)
    
    # Summary
    print("\n" + "="*60)
    print("PACMAN DAILY BUG SCAN SUMMARY")
    print("="*60)
    print(f"Total bugs found: {len(bugs)}")
    by_severity = {}
    by_layer = {}
    by_class = {}
    for bug in bugs:
        by_severity[bug.severity] = by_severity.get(bug.severity, 0) + 1
        by_layer[bug.layer] = by_layer.get(bug.layer, 0) + 1
        by_class[bug.bug_class] = by_class.get(bug.bug_class, 0) + 1
    
    print(f"\nBy Severity: {by_severity}")
    print(f"By Layer: {by_layer}")
    print(f"By Class: {by_class}")
    
    return 0 if bugs else 1


if __name__ == "__main__":
    sys.exit(main())