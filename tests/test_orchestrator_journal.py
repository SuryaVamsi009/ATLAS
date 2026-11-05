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
        return [
            json.loads(line)
            for line in self.ledger_file.read_text(encoding="utf-8").splitlines()
        ]

    def test_completed_cycles_are_durably_recorded_once_with_unique_ids(self):
        orchestrator = self.make_orchestrator()
        first = orchestrator.run_cycle(MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"})
        second = orchestrator.run_cycle(MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"})

        records = self.read_entries()
        self.assertTrue(first["step7_success"])
        self.assertTrue(second["step7_success"])
        self.assertEqual(len(records), 2)
        self.assertNotEqual(records[0]["entry_id"], records[1]["entry_id"])
        self.assertEqual(first["step6_journal_entry"]["entry_id"], records[0]["entry_id"])
        self.assertEqual(second["step6_journal_entry"]["entry_id"], records[1]["entry_id"])
        self.assertEqual(records[0]["status"], "completed")
        self.assertEqual(records[0]["step"], "approved_trade")
        self.assertEqual(records[0]["timestamp_ist"], records[0]["timestamp"])
        self.assertEqual(datetime.fromisoformat(records[0]["timestamp_ist"]).utcoffset().total_seconds(), 19800)
        self.assertIn("order_result", records[0])
        self.assertNotIn("order_details", records[0])
        self.assertEqual(records[0]["thesis"], records[0]["decision_proposal"]["rationale"])
        self.assertIsNone(records[0]["pnl"])
        self.assertIsNone(records[0]["confidence_calibration"])
        self.assertEqual(self.broker.order_attempts, 2)
        self.assertFalse(hasattr(orchestrator, "journal"))

    def test_risk_rejections_are_recorded_without_order_attempt(self):
        orchestrator = self.make_orchestrator(allowed_symbols=[])
        result = orchestrator.run_cycle(MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"})

        record = self.read_entries()[0]
        self.assertTrue(result["step7_success"])
        self.assertEqual(record["status"], "rejected")
        self.assertEqual(record["step"], "risk_rejection")
        self.assertFalse(record["risk_verdict"]["approved"])
        self.assertIsNotNone(record["risk_verdict"]["veto_reason"])
        self.assertEqual(self.broker.order_attempts, 0)

    def test_snapshot_failure_is_recorded_with_available_fields_only(self):
        with self.assertLogs("atlas.orchestrator", level="ERROR"):
            result = self.make_orchestrator().run_cycle([], "", {"symbol": "NIFTY"})

        record = self.read_entries()[0]
        self.assertFalse(result["step7_success"])
        self.assertIsNone(record["snapshot_id"])
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["failure_stage"], "snapshot")
        self.assertEqual(record["error"], "Step 1 failed: ohlcv_tail must have at least 2 bars")

    def test_research_failure_is_recorded(self):
        with self.assertLogs("atlas.orchestrator", level="ERROR"):
            result = self.make_orchestrator(research_fails=True).run_cycle(
                MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"}
            )

        record = self.read_entries()[0]
        self.assertFalse(result["step7_success"])
        self.assertEqual(record["failure_stage"], "research")
        self.assertEqual(record["status"], "failed")
        self.assertIn("research unavailable", record["error"])

    def test_proposal_failure_is_recorded(self):
        with self.assertLogs("atlas.orchestrator", level="ERROR"):
            result = self.make_orchestrator(
                research_flags=FailingRegimeFlags(["unusable"]),
            ).run_cycle(MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"})

        record = self.read_entries()[0]
        self.assertFalse(result["step7_success"])
        self.assertEqual(record["failure_stage"], "proposal")
        self.assertIn("proposal unavailable", record["error"])

    def test_risk_verification_failure_is_recorded(self):
        with self.assertLogs("atlas.orchestrator", level="ERROR"):
            result = self.make_orchestrator(invalid_daily_pnl=True).run_cycle(
                MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"}
            )

        record = self.read_entries()[0]
        self.assertFalse(result["step7_success"])
        self.assertEqual(record["failure_stage"], "risk")
        self.assertIn("unsupported operand type", record["error"])

    def test_order_failure_is_recorded(self):
        with self.assertLogs("atlas.orchestrator", level="ERROR"):
            result = self.make_orchestrator(broker_fails=True).run_cycle(
                MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"}
            )

        record = self.read_entries()[0]
        self.assertFalse(result["step7_success"])
        self.assertEqual(record["step"], "execution_failure")
        self.assertEqual(record["failure_stage"], "execution")
        self.assertIn("broker unavailable", record["error"])

    def test_journal_failure_is_reported_without_repeating_order(self):
        orchestrator = self.make_orchestrator()
        with (
            self.assertLogs("atlas.orchestrator", level="ERROR"),
            patch.object(journal, "_append_entry", side_effect=OSError("disk full")),
        ):
            result = orchestrator.run_cycle(
                MARKET_BARS, "", {"symbol": "NIFTY", "timeframe": "1d"}
            )

        self.assertFalse(result["step7_success"])
        self.assertIn("Journal persistence failed: disk full", result["step7_error"])
        self.assertEqual(result["step5_order_details"]["order_id"], "paper-1")
        self.assertEqual(result["step6_journal_entry"]["status"], "persistence_failed")
        self.assertEqual(self.broker.order_attempts, 1)
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
