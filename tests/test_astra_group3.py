import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from workerbees import ledger
from workerbees.control import Control
from workerbees.envelope import Decision
from workerbees.store import Store


class AstraGroup3Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.old_mode = os.environ.get("WORKERBEES_STORE")
        os.environ["WORKERBEES_STORE"] = "both"

    def tearDown(self):
        if self.old_mode is None:
            os.environ.pop("WORKERBEES_STORE", None)
        else:
            os.environ["WORKERBEES_STORE"] = self.old_mode
        self.tmp.cleanup()

    def db(self):
        return sqlite3.connect(self.workspace / ".workerbees" / "workerbees.db")

    def test_row12_decision_creates_request_and_full_audit(self):
        control = Control(self.workspace)
        decision = Decision(True, "d1", "ALLOWED", "ok", "p1", ["r1", "r2"])
        self.assertTrue(control.record_decision(
            decision, "run1", "node1", "hash1", "sender1", "recipient1", "request"))
        with self.db() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM request WHERE request_id='node1'").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM decision WHERE decision_id='d1'").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM decision_rule WHERE decision_id='d1'").fetchone()[0], 2)
            self.assertEqual(conn.execute("SELECT authenticated_sender_id,recipient_id FROM decision_identity WHERE decision_id='d1'").fetchone(), ("sender1", "recipient1"))

    def test_row13_transitions_and_frontier_reason_are_mirrored(self):
        control = Control(self.workspace)
        self.assertTrue(control.reserve("run1", "node1", 1, 2.0))
        self.assertTrue(control.release("run1", "node1"))
        approval = control.request_approval("run1", "alice", "ship", "repo", "abc", "high", ["r1"], "2099-01-01T00:00:00Z")
        self.assertTrue(control.decide_approval(approval, "bob", "approved", "2026-01-01T00:00:00Z"))
        self.assertTrue(control.acquire_lease("run1"))
        self.assertTrue(control.release_lease("run1"))
        self.assertTrue(ledger.record_dispatch(self.workspace, node_id="frontier", run_id="run1", model="m", tier="frontier", task="review", provider="p", parent_id=None, edge_type=None, gate_reason="quality gate"))
        with self.db() as conn:
            self.assertEqual(conn.execute("SELECT released FROM reservation WHERE request_id='node1'").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT approver,decision FROM approval WHERE approval_id=?", (approval,)).fetchone(), ("bob", "approved"))
            self.assertEqual(conn.execute("SELECT count(*) FROM approval_rule WHERE approval_id=?", (approval,)).fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT count(*) FROM lease").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT reason FROM frontier_gate WHERE node_id='frontier'").fetchone()[0], "quality gate")

    def test_row14_sqlite_mode_ignores_stale_jsonl(self):
        os.environ["WORKERBEES_STORE"] = "jsonl"
        ledger.record_dispatch(self.workspace, node_id="old", run_id="r", model="m", tier="cheap", task="t", provider="p", parent_id=None, edge_type=None)
        os.environ["WORKERBEES_STORE"] = "sqlite"
        ledger.record_dispatch(self.workspace, node_id="new", run_id="r", model="m", tier="cheap", task="t", provider="p", parent_id=None, edge_type=None)
        self.assertEqual(set(ledger.load(self.workspace).nodes), {"new"})

    def test_row15_null_model_route_is_idempotent(self):
        with Store(":memory:") as store:
            store.ensure_provider("openrouter")
            first = store.ensure_route("openrouter", "auto", None)
            second = store.ensure_route("openrouter", "auto", None)
            self.assertEqual(first, second)
            self.assertEqual(store.conn.execute("SELECT count(*) FROM route").fetchone()[0], 1)

    def test_row16_review_is_graph_edge_not_spawn_and_binds_artifact(self):
        os.environ["WORKERBEES_STORE"] = "sqlite"
        ledger.record_dispatch(self.workspace, node_id="worker", run_id="r", model="m1", tier="cheap", task="extract", provider="p1", parent_id=None, edge_type=None)
        ledger.record_dispatch(self.workspace, node_id="review", run_id="r", model="m2", tier="mid", task="review", provider="p2", parent_id="worker", edge_type="reviews", artifact_hash="a" * 64, artifact_size=12)
        with self.db() as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM lineage WHERE child_id='review'").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT edge_type FROM graph_edge WHERE source_id='review'").fetchone()[0], "reviews")
            self.assertEqual(conn.execute("SELECT sha256,role FROM edge_artifact WHERE source_id='review'").fetchone(), ("a" * 64, "candidate"))


if __name__ == "__main__":
    unittest.main()
