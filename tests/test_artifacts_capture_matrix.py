"""SC-005 (specs/006-bindle-sibling-integration): capture must fire identically
under off/shadow/enforce. WORKERBEES_ARTIFACTS default flipped off -> local by
operator ruling (D38, 2026-09-07: manual purge, no encryption, no backup
exclusion) -- unset now stores; WORKERBEES_ARTIFACTS=off is still honored
explicitly for anyone who opts out."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from workerbees.pipeline import brief
from workerbees.adapters.base import WorkerResult
from workerbees.registry import Registry
from workerbees.gateway import Gateway

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def fake_runner_factory(payload: dict, status="returned"):
    def runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
        return WorkerResult(status, json.dumps(payload), "", 0 if status == "returned" else 1)
    return runner


def _node_artifact_rows(ws: Path):
    db = ws / ".workerbees" / "workerbees.db"
    if not db.exists():
        return []
    conn = sqlite3.connect(db)
    return conn.execute("SELECT node_id, sha256, role FROM node_artifact").fetchall()


class ArtifactsCaptureMatrixTest(unittest.TestCase):
    def setUp(self):
        self.exp = json.loads((FIX / "sample-b" / "expected.json").read_text())
        self.payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}
        self._saved_env = {k: os.environ.get(k) for k in ("WORKERBEES_ARTIFACTS", "WORKERBEES_GOVERNANCE")}

    def tearDown(self):
        for k, v in self._saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_default_unset_stores_output(self):
        os.environ.pop("WORKERBEES_ARTIFACTS", None)
        ws = Path(tempfile.mkdtemp())
        r = brief(FIX / "sample-b" / "matter.md", "sample-b", "lawyer", ws, available={"claude", "codex"},
                  runner=fake_runner_factory(self.payload), review_enabled=False, governance_mode="off")
        rows = _node_artifact_rows(ws)
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(r.receipt.get("artifacts", {}).get("backend"), "local")
        self.assertTrue((ws / ".workerbees" / "cas").exists())

    def test_explicit_off_stores_nothing(self):
        os.environ["WORKERBEES_ARTIFACTS"] = "off"
        ws = Path(tempfile.mkdtemp())
        r = brief(FIX / "sample-b" / "matter.md", "sample-b", "lawyer", ws, available={"claude", "codex"},
                  runner=fake_runner_factory(self.payload), review_enabled=False, governance_mode="off")
        self.assertEqual(_node_artifact_rows(ws), [])
        self.assertEqual(r.receipt.get("artifacts", {}).get("backend"), "off")
        self.assertFalse((ws / ".workerbees" / "cas").exists())

    def test_local_off_mode_stores_output(self):
        os.environ["WORKERBEES_ARTIFACTS"] = "local"
        ws = Path(tempfile.mkdtemp())
        r = brief(FIX / "sample-b" / "matter.md", "sample-b", "lawyer", ws, available={"claude", "codex"},
                  runner=fake_runner_factory(self.payload), review_enabled=False, governance_mode="off")
        rows = _node_artifact_rows(ws)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][2], "output")
        self.assertEqual(r.receipt["artifacts"]["stored"], 1)

    def test_local_shadow_mode_stores_output(self):
        os.environ["WORKERBEES_ARTIFACTS"] = "local"
        ws = Path(tempfile.mkdtemp())
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(ws, registry=registry, mode="shadow")
        r = brief(FIX / "sample-b" / "matter.md", "sample-b", "lawyer", ws, available={"claude", "codex"},
                  runner=fake_runner_factory(self.payload), review_enabled=False, governance_mode="shadow",
                  gateway=gateway, registry=registry)
        rows = _node_artifact_rows(ws)
        # C1 (pipeline: parsed draft) and C3 (gateway: raw worker_result.output, which is
        # the JSON envelope claims+draft came from) are distinct capture points per
        # spec 006 S5.1's table -- different byte spans of the same node, hence >=1
        # row and NOT necessarily deduped to one.
        self.assertGreaterEqual(len(rows), 1)
        self.assertTrue(all(role == "output" for _, _, role in rows))


if __name__ == "__main__":
    unittest.main()
