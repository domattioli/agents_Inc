"""SQLite lint parity and cycle safety."""
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from workerbees import ledger


class SQLiteLintTest(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(tempfile.mkdtemp())

    def _node(self, node_id, run_id, model, tier, provider, parent_id, edge_type,
              gate_reason=None):
        ledger.record_dispatch(
            self.workspace, node_id=node_id, run_id=run_id, model=model, tier=tier,
            task="review" if edge_type == "reviews" else "extract", provider=provider,
            parent_id=parent_id, edge_type=edge_type, gate_reason=gate_reason,
        )
        ledger.record_return(
            self.workspace, node_id=node_id, status="returned", seconds=1.0,
            subscription_calls=1,
        )

    def _fixture(self, name):
        os.environ["WORKERBEES_STORE"] = "jsonl"
        try:
            if name == "tim":
                self._node("tim-root", "tim-run", "opus", "cheap", "anthropic", None, None)
                self._node("tim-review", "tim-run", "sonnet", "mid", "anthropic",
                           "tim-root", "reviews")
            else:
                self._node("dom-root", "dom-run", "opus", "mid", "anthropic", None, None)
                self._node("dom-correct", "dom-run", "sonnet", "mid", "anthropic",
                           "dom-root", "corrects")
                self._node("dom-review", "dom-run", "haiku", "cheap", "anthropic",
                           "dom-correct", "reviews")
        finally:
            os.environ.pop("WORKERBEES_STORE", None)
        subprocess.run(
            [sys.executable, "tools/migrate_to_3nf.py", str(self.workspace)],
            cwd=Path(__file__).parent.parent, check=True, capture_output=True, text=True,
        )

    @staticmethod
    def _verdicts(findings):
        return sorted((f.rule, tuple(f.node_ids)) for f in findings)

    def test_tim_and_dom_jsonl_sqlite_verdicts_match(self):
        for name in ("tim", "dom"):
            with self.subTest(name=name):
                self._fixture(name)
                jsonl = ledger.lint(workspace=self.workspace)
                sqlite = ledger.lint(source="sqlite", workspace=self.workspace)
                self.assertEqual(self._verdicts(jsonl), self._verdicts(sqlite))
                self.tearDown()
                self.setUp()

    def test_jsonl_depth_cycle_terminates_and_fails(self):
        a = ledger.Node("a", "r", "m", "cheap", "t", "p", "b", "corrects",
                        "returned", 1, 1, None, "t")
        b = ledger.Node("b", "r", "m", "cheap", "t", "p", "a", "corrects",
                        "returned", 1, 1, None, "t")
        findings = ledger.lint(ledger.Ledger({"a": a, "b": b}, []))
        self.assertEqual(["depth", "depth"], [f.rule for f in findings])

    def test_sqlite_depth_cycle_terminates_and_fails(self):
        self._fixture("dom")
        db = self.workspace / ".workerbees" / "workerbees.db"
        with sqlite3.connect(db) as conn:
            conn.execute(
                "INSERT INTO lineage(child_id, parent_id) VALUES (?, ?)",
                ("dom-root", "dom-correct"),
            )
        findings = ledger.lint(source="sqlite", workspace=self.workspace)
        cycle_nodes = {f.node_ids[0] for f in findings if f.rule == "depth"}
        self.assertEqual({"dom-root", "dom-correct", "dom-review"}, cycle_nodes)

    def test_source_validation(self):
        with self.assertRaisesRegex(ValueError, "Invalid lint source"):
            ledger.lint(source="bogus", workspace=self.workspace)
        with self.assertRaisesRegex(ValueError, "workspace is required"):
            ledger.lint(source="sqlite")


if __name__ == "__main__":
    unittest.main()
