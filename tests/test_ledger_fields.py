"""Spec 016 FR-001/FR-002 (#36): optional ledger fields and run_id on return rows.

Supervisor-owned acceptance tests. Temp workspaces only.
"""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agents_inc import ledger


class _Base(unittest.TestCase):
    store_mode = "jsonl"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self._old = os.environ.get("WORKERBEES_STORE")
        os.environ["WORKERBEES_STORE"] = self.store_mode

    def tearDown(self):
        if self._old is None:
            os.environ.pop("WORKERBEES_STORE", None)
        else:
            os.environ["WORKERBEES_STORE"] = self._old
        self.tmp.cleanup()

    def dispatch(self, node_id="n1", run_id="run-1", **extra):
        return ledger.record_dispatch(self.ws, node_id=node_id, run_id=run_id, model="haiku", tier="grunt",
                                      task="extract", provider="claude", parent_id=None, edge_type=None, **extra)

    def lines(self):
        path = self.ws / ".workerbees" / "ledger.jsonl"
        return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


class LedgerFieldsJsonlTest(_Base):
    def test_new_fields_persist_through_load(self):
        self.assertTrue(self.dispatch(effort="medium", cwd="/repo", source="supervisor"))
        self.assertTrue(ledger.record_return(
            self.ws, node_id="n1", status="verified", seconds=3.5, subscription_calls=1,
            input_tokens=1200, output_tokens=340, cache_read=9000, cache_write=0,
            files_created=["a.py", "b.py"], verdict="pass"))
        node = ledger.load(self.ws).nodes["n1"]
        self.assertEqual(node.effort, "medium")
        self.assertEqual(node.cwd, "/repo")
        self.assertEqual(node.source, "supervisor")
        self.assertEqual((node.input_tokens, node.output_tokens, node.cache_read, node.cache_write),
                         (1200, 340, 9000, 0))
        self.assertEqual(tuple(node.files_created), ("a.py", "b.py"))
        self.assertEqual(node.verdict, "pass")
        self.assertEqual(node.status, "verified")

    # SC-001
    def test_return_row_carries_dispatch_run_id_by_lookup(self):
        self.dispatch(node_id="n2", run_id="run-xyz")
        ledger.record_return(self.ws, node_id="n2", status="verified", seconds=1.0, subscription_calls=1)
        returns = [r for r in self.lines() if r["id"] == "n2" and r["status"] == "verified"]
        self.assertEqual(len(returns), 1)
        self.assertEqual(returns[0]["run_id"], "run-xyz")

    def test_return_row_uses_explicit_run_id(self):
        ledger.record_return(self.ws, node_id="n3", status="red", seconds=1.0, subscription_calls=1,
                             run_id="run-explicit", verdict="fail")
        self.assertEqual(self.lines()[-1]["run_id"], "run-explicit")

    def test_unknown_stays_unknown_not_zero(self):
        self.dispatch(node_id="n4")
        ledger.record_return(self.ws, node_id="n4", status="returned", seconds=1.0, subscription_calls=1)
        row = self.lines()[-1]
        for field in ("input_tokens", "output_tokens", "cache_read", "cache_write", "verdict", "files_created"):
            self.assertIn(field, row)
            self.assertIsNone(row[field], field)
        node = ledger.load(self.ws).nodes["n4"]
        self.assertIsNone(node.input_tokens)
        self.assertIsNone(node.verdict)

    # SC-002
    def test_pre_change_ledger_loads_with_unknown_fields(self):
        d = self.ws / ".workerbees"
        d.mkdir()
        old = {"id": "old1", "run_id": "r", "model": "sonnet", "tier": "workhorse", "task": "x", "provider": "claude",
               "parent_id": None, "edge_type": None, "status": "dispatched", "seconds": None,
               "subscription_calls": None, "gate_reason": None, "artifact_hash": None,
               "timestamp": "2026-09-01T00:00:00.000000Z"}
        ret = {"id": "old1", "run_id": None, "model": None, "tier": None, "task": None, "provider": None,
               "parent_id": None, "edge_type": None, "status": "returned", "seconds": 2.0,
               "subscription_calls": 1, "gate_reason": None, "timestamp": "2026-09-01T00:00:01.000000Z"}
        (d / "ledger.jsonl").write_text(json.dumps(old) + "\n" + json.dumps(ret) + "\n")
        loaded = ledger.load(self.ws)
        self.assertEqual(loaded.warnings, [])
        node = loaded.nodes["old1"]
        self.assertEqual(node.run_id, "r")
        self.assertEqual(node.status, "returned")
        for field in ("effort", "input_tokens", "output_tokens", "cache_read", "cache_write",
                      "files_created", "verdict", "cwd", "source"):
            self.assertIsNone(getattr(node, field), field)

    def test_invalid_verdict_rejected_without_write(self):
        self.dispatch(node_id="n5")
        before = len(self.lines())
        self.assertFalse(ledger.record_return(self.ws, node_id="n5", status="verified", seconds=1.0,
                                              subscription_calls=1, verdict="PASS-by-delegate"))
        self.assertEqual(len(self.lines()), before)

    def test_negative_tokens_rejected_without_write(self):
        self.dispatch(node_id="n6")
        before = len(self.lines())
        self.assertFalse(ledger.record_return(self.ws, node_id="n6", status="verified", seconds=1.0,
                                              subscription_calls=1, input_tokens=-5))
        self.assertEqual(len(self.lines()), before)

    def test_existing_positional_style_calls_still_work(self):
        self.assertTrue(ledger.record_dispatch(self.ws, node_id="n7", run_id="r7", model="opus",
                                               tier="orchestrator", task="t", provider="claude",
                                               parent_id=None, edge_type=None, gate_reason="g"))
        self.assertTrue(ledger.record_return(self.ws, node_id="n7", status="returned", seconds=1.0,
                                             subscription_calls=1))

    def test_json_round_trip_keeps_new_fields(self):
        self.dispatch(node_id="n8", effort="low")
        ledger.record_return(self.ws, node_id="n8", status="verified", seconds=1.0, subscription_calls=1,
                             output_tokens=7, files_created=["x"], verdict="pass")
        again = ledger.from_json(ledger.to_json(ledger.load(self.ws))).nodes["n8"]
        self.assertEqual(again.effort, "low")
        self.assertEqual(again.output_tokens, 7)
        self.assertEqual(tuple(again.files_created), ("x",))
        self.assertEqual(again.verdict, "pass")

    def test_seconds_and_calls_optional(self):
        self.dispatch(node_id="n9")
        self.assertTrue(ledger.record_return(self.ws, node_id="n9", status="verified", verdict="pass"))
        row = self.lines()[-1]
        self.assertIsNone(row["seconds"])
        self.assertIsNone(row["subscription_calls"])


class LedgerFieldsSqliteTest(_Base):
    store_mode = "both"

    def test_sqlite_usage_row_carries_input_output_tokens(self):
        self.dispatch(node_id="s1", run_id="run-s")
        self.assertTrue(ledger.record_return(self.ws, node_id="s1", status="verified", seconds=2.0,
                                             subscription_calls=1, input_tokens=111, output_tokens=22,
                                             verdict="pass"))
        conn = sqlite3.connect(str(self.ws / ".workerbees" / "workerbees.db"))
        try:
            row = conn.execute(
                "SELECT u.input_tokens, u.output_tokens FROM usage u JOIN node_event ne ON ne.event_id=u.event_id "
                "WHERE ne.node_id='s1' ORDER BY ne.event_seq DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        self.assertEqual(row, (111, 22))
        self.assertEqual(self.lines()[-1]["run_id"], "run-s")

    def test_sqlite_unknown_tokens_stay_null(self):
        self.dispatch(node_id="s2", run_id="run-s")
        ledger.record_return(self.ws, node_id="s2", status="verified", seconds=2.0, subscription_calls=1)
        conn = sqlite3.connect(str(self.ws / ".workerbees" / "workerbees.db"))
        try:
            row = conn.execute(
                "SELECT u.input_tokens, u.output_tokens FROM usage u JOIN node_event ne ON ne.event_id=u.event_id "
                "WHERE ne.node_id='s2' ORDER BY ne.event_seq DESC LIMIT 1").fetchone()
        finally:
            conn.close()
        self.assertEqual(row, (None, None))

    def test_store_argument_overrides_env(self):
        self.assertTrue(self.dispatch(node_id="s3", store="jsonl"))
        self.assertTrue(ledger.record_return(self.ws, node_id="s3", status="verified", seconds=1.0,
                                             subscription_calls=1, store="jsonl"))
        self.assertFalse((self.ws / ".workerbees" / "workerbees.db").exists())
        self.assertEqual(len(self.lines()), 2)
        with self.assertRaises(ValueError):
            self.dispatch(node_id="s4", store="bogus")

    def test_optional_seconds_in_sqlite_mode(self):
        self.dispatch(node_id="s5")
        self.assertTrue(ledger.record_return(self.ws, node_id="s5", status="verified", verdict="pass"))


if __name__ == "__main__":
    unittest.main()
