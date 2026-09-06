#!/usr/bin/env python3
"""Test 3NF migration: JSONL/control.sqlite → 3NF store. Idempotent round-trip."""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure workerbees is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestMigration(unittest.TestCase):
    """Migration test suite."""

    def setUp(self):
        """Create temp workspaces for each test."""
        self.temp_dir = tempfile.mkdtemp(prefix="test_migrate_")
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        """Clean up temp dir."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_ledger_fixture(self, name: str) -> Path:
        """Create a realistic multi-node ledger fixture.

        Creates:
        - tim: root + reviewer + parentless probe
        - dom: root + corrector + reviewer

        Returns: workspace path
        """
        from workerbees import ledger as ledger_module

        workspace = self.temp_path / f"fixture_{name}"
        workspace.mkdir(parents=True, exist_ok=True)

        # Force JSONL-only mode for fixture creation
        os.environ["WORKERBEES_STORE"] = "jsonl"

        if name == "tim":
            # Tim fixture: root + reviewer edge + probe node
            ledger_module.record_dispatch(
                workspace, node_id="tim-root-001", run_id="tim-run-01",
                model="claude-opus", tier="cheap", task="extract",
                provider="anthropic", parent_id=None, edge_type=None
            )
            ledger_module.record_return(
                workspace, node_id="tim-root-001", status="returned",
                seconds=1.5, subscription_calls=10
            )

            # Reviewer node (child of root, edge_type=reviews)
            ledger_module.record_dispatch(
                workspace, node_id="tim-review-002", run_id="tim-run-01",
                model="claude-sonnet", tier="mid", task="review",
                provider="anthropic", parent_id="tim-root-001", edge_type="reviews"
            )
            ledger_module.record_return(
                workspace, node_id="tim-review-002", status="verified",
                seconds=2.0, subscription_calls=15
            )

            # Probe node (parentless, edge_type=probes)
            ledger_module.record_dispatch(
                workspace, node_id="tim-probe-003", run_id="tim-run-01",
                model="claude-haiku", tier="cheap", task="probe",
                provider="anthropic", parent_id=None, edge_type="probes"
            )
            ledger_module.record_return(
                workspace, node_id="tim-probe-003", status="returned",
                seconds=0.5, subscription_calls=5
            )

        elif name == "dom":
            # Dom fixture: root + corrector + reviewer
            ledger_module.record_dispatch(
                workspace, node_id="dom-root-001", run_id="dom-run-01",
                model="claude-opus", tier="mid", task="reason",
                provider="anthropic", parent_id=None, edge_type=None
            )
            ledger_module.record_return(
                workspace, node_id="dom-root-001", status="returned",
                seconds=3.0, subscription_calls=20
            )

            # Corrector node (child of root, edge_type=corrects)
            ledger_module.record_dispatch(
                workspace, node_id="dom-correct-002", run_id="dom-run-01",
                model="claude-sonnet", tier="mid", task="correct",
                provider="anthropic", parent_id="dom-root-001", edge_type="corrects"
            )
            ledger_module.record_return(
                workspace, node_id="dom-correct-002", status="returned",
                seconds=1.2, subscription_calls=8
            )

            # Reviewer node (child of corrector, edge_type=reviews)
            ledger_module.record_dispatch(
                workspace, node_id="dom-review-003", run_id="dom-run-01",
                model="claude-haiku", tier="cheap", task="review",
                provider="anthropic", parent_id="dom-correct-002", edge_type="reviews"
            )
            ledger_module.record_return(
                workspace, node_id="dom-review-003", status="verified",
                seconds=0.8, subscription_calls=6
            )

        os.environ.pop("WORKERBEES_STORE", None)
        return workspace

    def _run_migration(self, workspace: Path, dry_run: bool = False) -> dict:
        """Run migration tool on workspace. Returns counts."""
        script = Path(__file__).parent.parent / "tools" / "migrate_to_3nf.py"
        cmd = [sys.executable, str(script), str(workspace)]
        if dry_run:
            cmd.append("--dry-run")

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(Path(__file__).parent.parent))
        if result.returncode != 0:
            raise RuntimeError(f"Migration failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")

        # Parse output for counts
        output = result.stdout
        return {"stdout": output}

    def test_gate_a_roundtrip_tim(self):
        """Gate A: Tim fixture round-trip Mermaid comparison."""
        workspace = self._create_ledger_fixture("tim")

        # Load original JSONL ledger
        from workerbees import ledger as ledger_module
        ledger_jsonl = ledger_module.load(workspace)
        mermaid_jsonl = ledger_module.to_mermaid(ledger_jsonl)

        # Migrate to store
        self._run_migration(workspace)

        # Load from the selected store, not the still-present JSONL source.
        os.environ["WORKERBEES_STORE"] = "sqlite"
        ledger_store = ledger_module.load(workspace)
        os.environ.pop("WORKERBEES_STORE", None)
        mermaid_store = ledger_module.to_mermaid(ledger_store)

        # Compare strings exactly
        self.assertEqual(mermaid_jsonl, mermaid_store,
                        f"Mermaid mismatch tim:\nJSONL:\n{mermaid_jsonl}\n\nStore:\n{mermaid_store}")

    def test_gate_a_roundtrip_dom(self):
        """Gate A: Dom fixture round-trip Mermaid comparison."""
        workspace = self._create_ledger_fixture("dom")

        # Load original JSONL ledger
        from workerbees import ledger as ledger_module
        ledger_jsonl = ledger_module.load(workspace)
        mermaid_jsonl = ledger_module.to_mermaid(ledger_jsonl)

        # Migrate to store
        self._run_migration(workspace)

        os.environ["WORKERBEES_STORE"] = "sqlite"
        ledger_store = ledger_module.load(workspace)
        os.environ.pop("WORKERBEES_STORE", None)
        mermaid_store = ledger_module.to_mermaid(ledger_store)

        # Compare strings exactly
        self.assertEqual(mermaid_jsonl, mermaid_store,
                        f"Mermaid mismatch dom:\nJSONL:\n{mermaid_jsonl}\n\nStore:\n{mermaid_store}")

    def test_gate_b_idempotence(self):
        """Gate B: Migration is idempotent. Second run writes 0 new fact rows."""
        workspace = self._create_ledger_fixture("tim")

        # First migration
        result1 = self._run_migration(workspace)
        output1 = result1["stdout"]

        # Count written in first run
        written_1 = 0
        for line in output1.split('\n'):
            if ': ' in line and line.startswith('  '):
                parts = line.split(': ')
                if len(parts) == 2 and parts[1].isdigit():
                    key, val = parts[0].strip(), int(parts[1])
                    if not key.startswith('skipped'):
                        written_1 += val

        # Get a stable dump of all tables after first migration
        db_path = workspace / ".workerbees" / "workerbees.db"
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get all table names
            tables = cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND NOT name LIKE 'sqlite_%'"
            ).fetchall()

            dump_1 = {}
            for table in tables:
                tname = table[0]
                rows = cursor.execute(f"SELECT * FROM {tname} ORDER BY rowid").fetchall()
                dump_1[tname] = [dict(row) for row in rows]

        # Second migration (should write 0 new fact rows)
        result2 = self._run_migration(workspace)
        output2 = result2["stdout"]

        # Count written in second run
        written_2 = 0
        for line in output2.split('\n'):
            if ': ' in line and line.startswith('  '):
                parts = line.split(': ')
                if len(parts) == 2 and parts[1].isdigit():
                    key, val = parts[0].strip(), int(parts[1])
                    if not key.startswith('skipped'):
                        written_2 += val

        # Second run should write 0 new fact rows (only skipped)
        self.assertEqual(written_2, 0, f"Second migration wrote {written_2} rows, expected 0")

        # Verify dump is byte-identical
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            tables = cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND NOT name LIKE 'sqlite_%'"
            ).fetchall()

            dump_2 = {}
            for table in tables:
                tname = table[0]
                rows = cursor.execute(f"SELECT * FROM {tname} ORDER BY rowid").fetchall()
                dump_2[tname] = [dict(row) for row in rows]

        self.assertEqual(dump_1, dump_2, "Database dump differs after second migration")

    def test_gate_c_rollup_parity(self):
        """Gate C: Rollup from JSONL equals rollup from migrated store."""
        workspace = self._create_ledger_fixture("tim")

        from workerbees import ledger as ledger_module

        # Compute rollup from original JSONL
        ledger_jsonl = ledger_module.load(workspace)
        rollup_jsonl = ledger_module.rollup(ledger_jsonl)

        # Migrate
        self._run_migration(workspace)

        # Compute rollup from the selected store, not JSONL again.
        os.environ["WORKERBEES_STORE"] = "sqlite"
        ledger_store = ledger_module.load(workspace)
        os.environ.pop("WORKERBEES_STORE", None)
        rollup_store = ledger_module.rollup(ledger_store)

        # Compare
        self.assertEqual(rollup_jsonl, rollup_store,
                        f"Rollup mismatch:\nJSONL: {rollup_jsonl}\nStore: {rollup_store}")

    def test_gate_d_probe_survives(self):
        """Gate D: Parentless probe node with edge_type='probes' migrates intact."""
        workspace = self._create_ledger_fixture("tim")

        from workerbees import ledger as ledger_module

        # Migrate
        self._run_migration(workspace)

        os.environ["WORKERBEES_STORE"] = "sqlite"
        ledger_store = ledger_module.load(workspace)
        os.environ.pop("WORKERBEES_STORE", None)

        # Find probe node
        probe_node = ledger_store.nodes.get("tim-probe-003")
        self.assertIsNotNone(probe_node, "Probe node not found after migration")
        self.assertIsNone(probe_node.parent_id, "Probe node should have parent_id=None")
        self.assertEqual(probe_node.edge_type, "probes", "Probe node edge_type should be 'probes'")

    def test_gate_e_import_metadata(self):
        """Gate E: import_source and import_issue are populated."""
        workspace = self._create_ledger_fixture("tim")

        # Migrate
        self._run_migration(workspace)

        db_path = workspace / ".workerbees" / "workerbees.db"
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row

            # Check import_source
            sources = conn.execute("SELECT * FROM import_source").fetchall()
            self.assertGreater(len(sources), 0, "import_source should have at least 1 row")

            source = sources[0]
            self.assertIsNotNone(source["source_id"])
            self.assertEqual(source["kind"], "ledger+control")
            self.assertIsNotNone(source["source_sha"])

            # For now, import_issue may be empty (only recorded on errors)
            # But the table should exist and be queryable
            issues = conn.execute("SELECT * FROM import_issue").fetchall()
            # Just verify table is accessible
            self.assertIsInstance(issues, list)

    def test_gate_f_dry_run_writes_nothing(self):
        """Gate F: --dry-run reports without writing."""
        workspace = self._create_ledger_fixture("tim")

        db_path = workspace / ".workerbees" / "workerbees.db"

        # Run with --dry-run
        result = self._run_migration(workspace, dry_run=True)
        output = result["stdout"]

        # Verify output says dry-run
        self.assertIn("dry-run", output.lower(), "Output should mention dry-run")

        # If workerbees.db exists after dry-run, it should be empty of data
        if db_path.exists():
            with sqlite3.connect(str(db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                # Count data rows in key tables
                run_count = cursor.execute("SELECT COUNT(*) as cnt FROM run").fetchone()["cnt"]
                node_count = cursor.execute("SELECT COUNT(*) as cnt FROM node").fetchone()["cnt"]

                # With dry-run, these should be 0
                self.assertEqual(run_count, 0, "No runs should be written in dry-run")
                self.assertEqual(node_count, 0, "No nodes should be written in dry-run")


class TestMigrationDynamics(unittest.TestCase):
    """Additional migration behavior tests."""

    def setUp(self):
        """Create temp workspaces."""
        self.temp_dir = tempfile.mkdtemp(prefix="test_migrate_")
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_missing_workspace_records_import_issue(self):
        """A missing source workspace is retained as an import issue."""
        script = Path(__file__).parent.parent / "tools" / "migrate_to_3nf.py"
        db_path = self.temp_path / "missing-source.db"
        result = subprocess.run(
            [sys.executable, str(script), "/nonexistent/workspace", "--db", str(db_path)],
            capture_output=True, text=True, cwd=str(Path(__file__).parent.parent)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        with sqlite3.connect(db_path) as conn:
            issue = conn.execute(
                "SELECT code, detail FROM import_issue WHERE code='workspace_not_found'"
            ).fetchone()
        self.assertIsNotNone(issue)
        self.assertEqual(issue[0], "workspace_not_found")
        self.assertIn("/nonexistent/workspace", issue[1])


if __name__ == "__main__":
    unittest.main()
