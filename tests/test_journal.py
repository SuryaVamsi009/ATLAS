"""Tests for atlas.journal module."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from atlas import journal
from atlas.decision_proposal import DecisionProposal
from atlas.journal import RiskVerdict, VetoReason

IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture
def temp_ledger():
    """Create a temporary ledger directory and patch journal module."""
    temp_dir = tempfile.TemporaryDirectory()
    ledger_file = Path(temp_dir.name) / "ledger.jsonl"

    with patch.object(journal, "LEDGER_DIR", temp_dir.name):
        with patch.object(journal, "LEDGER_FILE", str(ledger_file)):
            yield ledger_file

    temp_dir.cleanup()


def read_entries(ledger_file):
    if not ledger_file.exists():
        return []
    return [
        json.loads(line)
        for line in ledger_file.read_text(encoding="utf-8").splitlines()
    ]


class TestJournal:
    def test_append_entry_creates_file(self, temp_ledger):
        entry = {"test": "data", "timestamp": "2026-11-06T11:00:00+05:30"}
        journal._append_entry(entry)
        assert temp_ledger.exists()
        entries = read_entries(temp_ledger)
        assert len(entries) == 1
        assert entries[0]["test"] == "data"

    def test_append_entry_appends_multiple(self, temp_ledger):
        journal._append_entry({"id": 1})
        journal._append_entry({"id": 2})
        entries = read_entries(temp_ledger)
        assert len(entries) == 2
        assert entries[0]["id"] == 1
        assert entries[1]["id"] == 2

    def test_write_regime_entry(self, temp_ledger):
        entry_id = journal.write_regime_entry(
            snapshot_id="test_snapshot_1",
            regime_flags=["trending_up", "neutral"],
            event_alerts=["breakout"],
            thesis="Nifty above 50-DMA with FII buying, trending market conditions",
            confidence=0.78,
            news_context="Q2 earnings season starting; IT sector AI revenue beats; FII buying observed",
        )
        assert entry_id.startswith("regime_test_snapshot_1_")
        entries = read_entries(temp_ledger)
        assert len(entries) == 1
        assert entries[0]["entry_id"] == entry_id
        assert entries[0]["regime_flags"] == ["trending_up", "neutral"]
        assert entries[0]["event_alerts"] == ["breakout"]
        assert entries[0]["thesis"] == "Nifty above 50-DMA with FII buying, trending market conditions"
        assert entries[0]["confidence"] == 0.78
        assert entries[0]["news_context"] == "Q2 earnings season starting; IT sector AI revenue beats; FII buying observed"
        assert entries[0]["agent_action"] is None
        assert entries[0]["risk_verdict"] is None
        assert entries[0]["order_result"] is None
        assert entries[0]["pnl"] is None

    def test_read_latest_regime_entry(self, temp_ledger):
        journal.write_regime_entry(
            snapshot_id="test_snapshot_1",
            regime_flags=["trending_up"],
            event_alerts=[],
            thesis="Test thesis",
            confidence=0.75,
            news_context="Test news",
        )
        latest = journal.read_latest_regime_entry()
        assert latest is not None
        assert latest["regime_flags"] == ["trending_up"]
        assert latest["thesis"] == "Test thesis"

    def test_read_latest_regime_entry_empty(self, temp_ledger):
        latest = journal.read_latest_regime_entry()
        assert latest is None

    def test_read_all_regime_entries(self, temp_ledger):
        journal.write_regime_entry(
            snapshot_id="test_snapshot_1",
            regime_flags=["trending_up"],
            event_alerts=[],
            thesis="Test thesis 1",
            confidence=0.75,
            news_context="Test news",
        )
        journal.write_regime_entry(
            snapshot_id="test_snapshot_2",
            regime_flags=["ranging"],
            event_alerts=[],
            thesis="Test thesis 2",
            confidence=0.65,
            news_context="Test news",
        )
        entries = journal.read_all_regime_entries()
        assert len(entries) == 2
        assert entries[0]["regime_flags"] == ["trending_up"]
        assert entries[1]["regime_flags"] == ["ranging"]

    def test_write_decision_proposal_entry(self, temp_ledger):
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test rationale",
        )
        entry_id = journal.write_decision_proposal_entry(
            snapshot_id="test_snapshot_1",
            decision_proposal=proposal,
            regime_entry_id="regime_test_123",
        )
        assert entry_id == "proposal_regime_test_123"
        entries = read_entries(temp_ledger)
        assert len(entries) == 1
        assert entries[0]["entry_id"] == entry_id
        assert entries[0]["decision_proposal"]["action"] == "BUY"
        assert entries[0]["decision_proposal"]["confidence"] == 0.85
        assert entries[0]["decision_proposal"]["size_hint"] == 0.5
        assert entries[0]["decision_proposal"]["stop_hint"] == 19300.0
        assert entries[0]["decision_proposal"]["rationale"] == "Test rationale"
        assert entries[0]["agent_action"] == "generate_decision_proposal"
        assert entries[0]["risk_verdict"] is None
        assert entries[0]["order_result"] is None
        assert entries[0]["pnl"] is None

    def test_write_risk_verdict_entry(self, temp_ledger):
        # First write a proposal entry
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test rationale",
        )
        journal.write_decision_proposal_entry(
            snapshot_id="test_snapshot_1",
            decision_proposal=proposal,
            regime_entry_id="regime_test_123",
        )

        # Now write risk verdict
        verdict = RiskVerdict(
            approved=True,
            final_qty=50,
            final_stop=19300.0,
            veto_reason=VetoReason.NONE,
            checks={"size_ok": True, "loss_ok": True, "hours_ok": True, "symbol_ok": True, "confidence_ok": True},
        )
        entry_id = journal.write_risk_verdict_entry("proposal_regime_test_123", verdict)
        assert entry_id == "proposal_regime_test_123"

        entries = read_entries(temp_ledger)
        assert len(entries) == 1
        assert entries[0]["risk_verdict"]["approved"] is True
        assert entries[0]["risk_verdict"]["final_qty"] == 50
        assert entries[0]["risk_verdict"]["final_stop"] == 19300.0
        assert entries[0]["risk_verdict"]["veto_reason"] is None
        assert entries[0]["risk_verdict"]["checks"]["size_ok"] is True

    def test_write_risk_verdict_entry_rejected(self, temp_ledger):
        # First write a proposal entry
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test rationale",
        )
        journal.write_decision_proposal_entry(
            snapshot_id="test_snapshot_1",
            decision_proposal=proposal,
            regime_entry_id="regime_test_123",
        )

        # Now write risk verdict (rejected)
        verdict = RiskVerdict(
            approved=False,
            final_qty=0,
            final_stop=0.0,
            veto_reason=VetoReason.SIZE_OK,
            checks={"size_ok": False, "loss_ok": True, "hours_ok": True, "symbol_ok": True, "confidence_ok": True},
        )
        journal.write_risk_verdict_entry("proposal_regime_test_123", verdict)

        entries = read_entries(temp_ledger)
        assert len(entries) == 1
        assert entries[0]["risk_verdict"]["approved"] is False
        assert entries[0]["risk_verdict"]["veto_reason"] == "size_ok"

    def test_write_order_result_entry(self, temp_ledger):
        # First write a proposal entry
        proposal = DecisionProposal(
            action="BUY",
            confidence=0.85,
            size_hint=0.5,
            stop_hint=19300.0,
            rationale="Test rationale",
        )
        journal.write_decision_proposal_entry(
            snapshot_id="test_snapshot_1",
            decision_proposal=proposal,
            regime_entry_id="regime_test_123",
        )

        # Now write order result
        order_result = {
            "order_id": "paper-1",
            "fill_price": 19550.0,
            "quantity": 50,
            "status": "filled",
        }
        journal.write_order_result_entry("proposal_regime_test_123", order_result)

        entries = read_entries(temp_ledger)
        assert len(entries) == 1
        assert entries[0]["order_result"]["order_id"] == "paper-1"
        assert entries[0]["order_result"]["fill_price"] == 19550.0
        assert entries[0]["order_result"]["quantity"] == 50
        assert entries[0]["pnl"] is not None  # P&L should be calculated

    def test_get_ledger_entries_empty(self, temp_ledger):
        entries = journal.get_ledger_entries()
        assert entries == []

    def test_get_ledger_entries_with_filter(self, temp_ledger):
        journal.write_regime_entry(
            snapshot_id="test_1",
            regime_flags=["trending_up"],
            event_alerts=[],
            thesis="Test",
            confidence=0.75,
            news_context="Test",
        )
        journal.write_regime_entry(
            snapshot_id="test_2",
            regime_flags=["ranging"],
            event_alerts=[],
            thesis="Test",
            confidence=0.65,
            news_context="Test",
        )

        entries = journal.get_ledger_entries(filter_regime=["trending_up"])
        assert len(entries) == 1
        assert entries[0]["regime_flags"] == ["trending_up"]

    def test_get_ledger_entries_time_filter(self, temp_ledger):
        # Write entries with different timestamps
        journal.write_regime_entry(
            snapshot_id="test_1",
            regime_flags=["trending_up"],
            event_alerts=[],
            thesis="Test",
            confidence=0.75,
            news_context="Test",
        )
        journal.write_regime_entry(
            snapshot_id="test_2",
            regime_flags=["ranging"],
            event_alerts=[],
            thesis="Test",
            confidence=0.65,
            news_context="Test",
        )

        # Filter by time - use a wide range in UTC to capture entries
        # Entries are written with IST timestamps (UTC+5:30), so use a wide UTC range
        entries = journal.get_ledger_entries(
            filter_start=datetime(2020, 1, 1, tzinfo=UTC),
            filter_end=datetime(2030, 1, 1, tzinfo=UTC),
        )
        assert len(entries) >= 1

    def test_get_ledger_stats(self, temp_ledger):
        journal.write_regime_entry(
            snapshot_id="test_1",
            regime_flags=["trending_up"],
            event_alerts=[],
            thesis="Test",
            confidence=0.75,
            news_context="Test",
        )
        journal.write_regime_entry(
            snapshot_id="test_2",
            regime_flags=["trending_up"],
            event_alerts=[],
            thesis="Test",
            confidence=0.85,
            news_context="Test",
        )

        stats = journal.get_ledger_stats()
        assert stats["total_entries"] == 2
        assert stats["regime_distribution"]["trending_up"] == 2
        assert stats["most_common_regime"] == "trending_up"
        assert stats["confidence_range"] == "0.75-0.85"
        assert stats["total_pnl"] == 0.0
        assert stats["completed_trades"] == 0
