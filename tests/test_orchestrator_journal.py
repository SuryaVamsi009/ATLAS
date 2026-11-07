import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from atlas import journal
from atlas.orchestrator import Orchestrator, OrchestratorConfig
from atlas.research_ai import ResearchAI


IST = ZoneInfo("Asia/Kolkata")
MARKET_TIME = datetime(2026, 11, 6, 11, 0, tzinfo=IST)
MARKET_BARS = [
    [1730428800000, 100.0, 102.0, 99.0, 101.0, 1500.0],
    [1730515200000, 101.0, 103.0, 100.0, 102.0, 1800.0],
    [1730601600000, 102.0, 104.0, 101.0, 103.0, 2000.0],
]


class StaticResearchAI(ResearchAI):
    def __init__(self, *, fail=False, regime_flags=None, invalid_daily_pnl=False):
        self.fail = fail
        self.regime_flags = regime_flags or ["trending_up"]
        self.invalid_daily_pnl = invalid_daily_pnl

    def analyze(self, snapshot, news_context, rag_corpus, context_dict):
        if self.fail:
            raise RuntimeError("research unavailable")
        if self.invalid_daily_pnl:
            snapshot.account["daily_pnl"] = "invalid"
        return {"regime_flags": self.regime_flags, "event_alerts": []}


class FailingRegimeFlags(list):
    def __contains__(self, item):
        raise RuntimeError("proposal unavailable")


class FakeKiteAdapter:
    def __init__(self, fail=False):
        self.fail = fail
        self.order_attempts = 0

    def _validate_symbol(self, symbol):
        return True

    def place_order(self, **order):
        self.order_attempts += 1
        if self.fail:
            raise RuntimeError("broker unavailable")
        return {"order_id": "paper-1"}


class OrchestratorJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.ledger_file = Path(self.temp_dir.name) / "ledger.jsonl"
        self.ledger_dir_patch = patch.object(journal, "LEDGER_DIR", self.temp_dir.name)
        self.ledger_file_patch = patch.object(journal, "LEDGER_FILE", str(self.ledger_file))
        self.ledger_dir_patch.start()
        self.ledger_file_patch.start()
        self.addCleanup(self.ledger_dir_patch.stop)
        self.addCleanup(self.ledger_file_patch.stop)
        self.clock_patch = patch("atlas.orchestrator.datetime")
        self.clock = self.clock_patch.start()
        self.clock.now.return_value = MARKET_TIME
        self.addCleanup(self.clock_patch.stop)

    def make_orchestrator(
        self,
        *,
        allowed_symbols=None,
        research_fails=False,
        broker_fails=False,
        research_flags=None,
        invalid_daily_pnl=False,
    ):
        self.broker = FakeKiteAdapter(fail=broker_fails)
        return Orchestrator(
            OrchestratorConfig(
                allowed_symbols=allowed_symbols if allowed_symbols is not None else ["NIFTY"],
            ),
            research_ai=StaticResearchAI(
                fail=research_fails,
                regime_flags=research_flags,
                invalid_daily_pnl=invalid_daily_pnl,
            ),
            kite_adapter=self.broker,
        )

    def read_entries(self):
        if not self.ledger_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.ledger_file.read_text(encoding="utf-8").splitlines()
        ]

    def test_completed_cycles_write_regime_and_proposal_entries(self):
        """Test that completed cycles write regime and proposal entries (Two-AI protocol).
        
        The journal protocol:
        - Regime entry (new): Research AI writes regime_flags, event_alerts, thesis, confidence
        - Proposal entry (new): Agent AI writes DecisionProposal, linked to regime_entry_id
        - Risk verdict: Updates the proposal entry with risk_verdict
        - Order result: Updates the proposal entry with order_result and P&L
        """
        orchestrator = self.make_orchestrator()
        first = orchestrator.run_cycle(MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"})
        second = orchestrator.run_cycle(MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"})

        records = self.read_entries()
        self.assertTrue(first["step7_success"])
        self.assertTrue(second["step7_success"])
        
        # Each cycle writes 2 entries: regime + proposal (which gets updated with risk+order)
        self.assertEqual(len(records), 4)
        
        # Check first cycle entries
        first_regime = records[0]
        first_proposal = records[1]
        
        # Regime entry (Research AI writes)
        self.assertTrue(first_regime["entry_id"].startswith("regime_"))
        self.assertIn("regime_flags", first_regime)
        self.assertIn("event_alerts", first_regime)
        self.assertIn("thesis", first_regime)
        self.assertIn("confidence", first_regime)
        
        # Proposal entry (Agent AI writes) - gets updated with risk_verdict and order_result
        self.assertTrue(first_proposal["entry_id"].startswith("proposal_"))
        self.assertIn("decision_proposal", first_proposal)
        self.assertEqual(first_proposal["regime_entry_id"], first_regime["entry_id"])
        self.assertIn("risk_verdict", first_proposal)
        self.assertIn("order_result", first_proposal)
        self.assertTrue(first_proposal["risk_verdict"]["approved"])
        self.assertEqual(first_proposal["order_result"]["order_id"], "paper-1")
        
        # Verify order was placed
        self.assertEqual(self.broker.order_attempts, 2)
        self.assertFalse(hasattr(orchestrator, "journal"))

    def test_risk_rejections_write_regime_and_proposal_entries(self):
        """Test that risk rejections write regime and proposal entries (proposal updated with risk)."""
        orchestrator = self.make_orchestrator(allowed_symbols=[])
        result = orchestrator.run_cycle(MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"})

        records = self.read_entries()
        self.assertTrue(result["step7_success"])
        
        # Should have 2 entries: regime + proposal (updated with risk_verdict, no order_result)
        self.assertEqual(len(records), 2)
        
        regime_entry = records[0]
        proposal_entry = records[1]
        
        self.assertTrue(regime_entry["entry_id"].startswith("regime_"))
        self.assertTrue(proposal_entry["entry_id"].startswith("proposal_"))
        self.assertEqual(proposal_entry["regime_entry_id"], regime_entry["entry_id"])
        self.assertIn("risk_verdict", proposal_entry)
        self.assertFalse(proposal_entry["risk_verdict"]["approved"])
        self.assertIsNotNone(proposal_entry["risk_verdict"]["veto_reason"])
        self.assertNotIn("order_result", proposal_entry)  # No order for rejected trades
        self.assertEqual(self.broker.order_attempts, 0)

    def test_snapshot_failure_writes_no_entries(self):
        """Test that snapshot failures write no journal entries (cycle fails before journal)."""
        with self.assertLogs("atlas.orchestrator", level="ERROR"):
            result = self.make_orchestrator().run_cycle([], "", {"symbol": "NIFTY"})

        records = self.read_entries()
        self.assertFalse(result["step7_success"])
        self.assertEqual(len(records), 0)  # No entries written for snapshot failure

    def test_research_failure_writes_no_entries(self):
        """Test that research failures write no journal entries."""
        with self.assertLogs("atlas.orchestrator", level="ERROR"):
            result = self.make_orchestrator(research_fails=True).run_cycle(
                MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"}
            )

        records = self.read_entries()
        self.assertFalse(result["step7_success"])
        self.assertEqual(len(records), 0)  # No entries written for research failure

    def test_proposal_failure_writes_regime_entry_only(self):
        """Test that proposal failures write regime entry but not proposal/risk/order."""
        with self.assertLogs("atlas.orchestrator", level="ERROR"):
            result = self.make_orchestrator(
                research_flags=FailingRegimeFlags(["unusable"]),
            ).run_cycle(MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"})

        records = self.read_entries()
        self.assertFalse(result["step7_success"])
        # Only regime entry should be written
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["entry_id"].startswith("regime_"))

    def test_risk_verification_failure_writes_regime_and_proposal(self):
        """Test that risk verification failures write regime and proposal entries."""
        with self.assertLogs("atlas.orchestrator", level="ERROR"):
            result = self.make_orchestrator(invalid_daily_pnl=True).run_cycle(
                MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"}
            )

        records = self.read_entries()
        self.assertFalse(result["step7_success"])
        # Should have 2 entries: regime + proposal (updated with risk_verdict)
        self.assertEqual(len(records), 2)
        self.assertTrue(records[0]["entry_id"].startswith("regime_"))
        self.assertTrue(records[1]["entry_id"].startswith("proposal_"))
        self.assertIn("risk_verdict", records[1])

    def test_order_failure_writes_regime_and_proposal_with_error(self):
        """Test that order failures write regime and proposal entries with order error."""
        with self.assertLogs("atlas.orchestrator", level="ERROR"):
            result = self.make_orchestrator(broker_fails=True).run_cycle(
                MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"}
            )

        records = self.read_entries()
        self.assertFalse(result["step7_success"])
        # Should have 2 entries: regime + proposal (updated with risk_verdict and order_result with error)
        self.assertEqual(len(records), 2)
        self.assertTrue(records[0]["entry_id"].startswith("regime_"))
        self.assertTrue(records[1]["entry_id"].startswith("proposal_"))
        self.assertIn("risk_verdict", records[1])
        self.assertIn("order_result", records[1])
        self.assertIn("error", records[1]["order_result"])

    def test_journal_failure_is_reported_without_repeating_order(self):
        """Test that journal write failures are logged but order is not repeated.

        In the new Two-AI architecture, journal writes happen at each step
        (regime, proposal, risk_verdict, order_result) and are non-blocking.
        If all journal writes fail, the trading cycle still completes but
        errors are logged. The order is placed exactly once.
        """
        orchestrator = self.make_orchestrator()
        with (
            self.assertLogs("atlas.orchestrator", level="ERROR"),
            patch.object(journal, "_append_entry", side_effect=OSError("disk full")),
        ):
            result = orchestrator.run_cycle(
                MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"}
            )

        # Cycle succeeds because trading logic completed; journal failures are non-blocking
        self.assertTrue(result["step7_success"])
        self.assertIsNone(result["step7_error"])
        # Order was placed exactly once
        self.assertIsNotNone(result["step5_order_details"])
        self.assertEqual(result["step5_order_details"]["order_id"], "paper-1")
        self.assertEqual(self.broker.order_attempts, 1)
        # No ledger file created because all writes failed
        self.assertFalse(self.ledger_file.exists())

    def test_time_filter_handles_ist_offsets_and_legacy_naive_timestamps(self):
        self.ledger_file.write_text(
            "\n".join(
                json.dumps(entry)
                for entry in (
                    {"timestamp_ist": "2026-11-06T10:30:00+05:30"},
                    {"timestamp": "2026-11-06T05:30:00"},
                    {"timestamp_ist": "2026-11-06T10:29:00+05:30"},
                )
            )
            + "\n",
            encoding="utf-8",
        )

        entries = journal.get_ledger_entries(
            filter_start=datetime(2026, 11, 6, 5, 0, tzinfo=timezone.utc),
            filter_end=datetime(2026, 11, 6, 6, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["timestamp_ist"], "2026-11-06T10:30:00+05:30")
        self.assertEqual(entries[1]["timestamp"], "2026-11-06T05:30:00")


if __name__ == "__main__":
    unittest.main()
