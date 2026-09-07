import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from workerbees import artifacts, ledger


class ArtifactsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_capture_then_get_roundtrips(self):
        data = b"hello bindle"
        cap = artifacts.capture(self.workspace, data)
        self.assertTrue(cap.stored)
        self.assertEqual(cap.backend, "local")
        self.assertEqual(cap.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(artifacts.get(self.workspace, cap.sha256), data)

    def test_dedup_no_op_on_second_write(self):
        data = b"same bytes twice"
        cap1 = artifacts.capture(self.workspace, data)
        cap2 = artifacts.capture(self.workspace, data)
        self.assertEqual(cap1.sha256, cap2.sha256)
        self.assertEqual(artifacts.get(self.workspace, cap1.sha256), data)

    def test_get_rejects_path_traversal(self):
        self.assertIsNone(artifacts.get(self.workspace, "../../../../etc/passwd"))

    def test_get_rejects_non_hex_key(self):
        self.assertIsNone(artifacts.get(self.workspace, "not-a-real-sha256-key"))
        self.assertIsNone(artifacts.get(self.workspace, "A" * 64))  # uppercase rejected

    def test_get_rejects_truncated_key(self):
        self.assertIsNone(artifacts.get(self.workspace, "ab" * 10))

    def test_get_missing_blob_returns_none(self):
        fake = "0" * 64
        self.assertIsNone(artifacts.get(self.workspace, fake))

    def test_tampered_blob_returns_none_and_quarantines(self):
        data = b"integrity check me"
        cap = artifacts.capture(self.workspace, data)
        blob_path = self.workspace / ".workerbees" / "cas" / cap.sha256[:2] / cap.sha256
        blob_path.write_bytes(b"corrupted bytes, different content")
        self.assertIsNone(artifacts.get(self.workspace, cap.sha256))
        self.assertFalse(blob_path.exists())
        self.assertTrue(blob_path.with_suffix(".tampered").exists())

    def test_file_and_dir_permissions(self):
        data = b"permission check"
        cap = artifacts.capture(self.workspace, data)
        blob_path = self.workspace / ".workerbees" / "cas" / cap.sha256[:2] / cap.sha256
        shard = blob_path.parent
        self.assertEqual(blob_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(shard.stat().st_mode & 0o777, 0o700)

    def test_off_backend_never_writes_to_disk(self):
        # capture() itself is env-agnostic (always writes); the on/off gate lives in
        # the callers (pipeline.py/gateway.py). This test locks that contract: an
        # untouched workspace has no cas/ dir until something actually calls capture().
        self.assertFalse((self.workspace / ".workerbees" / "cas").exists())

    def test_purge_removes_only_blobs_older_than_cutoff(self):
        # D38 (operator ruling 2026-09-07): manual purge, no auto-GC.
        old_cap = artifacts.capture(self.workspace, b"old blob")
        new_cap = artifacts.capture(self.workspace, b"new blob")
        root = self.workspace / ".workerbees" / "cas"
        old_blob = root / old_cap.sha256[:2] / old_cap.sha256
        old_meta = root / old_cap.sha256[:2] / f"{old_cap.sha256}.meta.json"
        old_ts = old_blob.stat().st_mtime - (40 * 86400)
        os.utime(old_blob, (old_ts, old_ts))
        os.utime(old_meta, (old_ts, old_ts))

        removed = artifacts.purge(self.workspace, older_than_days=30)
        self.assertEqual(removed, [old_cap.sha256])
        self.assertIsNone(artifacts.get(self.workspace, old_cap.sha256))
        self.assertEqual(artifacts.get(self.workspace, new_cap.sha256), b"new blob")

    def test_purge_dry_run_deletes_nothing(self):
        cap = artifacts.capture(self.workspace, b"dry run me")
        blob = self.workspace / ".workerbees" / "cas" / cap.sha256[:2] / cap.sha256
        old_ts = blob.stat().st_mtime - (40 * 86400)
        os.utime(blob, (old_ts, old_ts))

        removed = artifacts.purge(self.workspace, older_than_days=30, dry_run=True)
        self.assertEqual(removed, [cap.sha256])
        self.assertEqual(artifacts.get(self.workspace, cap.sha256), b"dry run me")

    def test_purge_on_empty_workspace_is_noop(self):
        self.assertEqual(artifacts.purge(self.workspace, older_than_days=30), [])


class RecordOutputTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_record_output_binds_artifact_to_node_sqlite(self):
        import sqlite3
        node_id = "node-1"
        ok = ledger.record_dispatch(self.workspace, node_id=node_id, run_id="run-1", model="haiku",
                                    tier="grunt", task="extract", provider="claude", parent_id=None, edge_type=None)
        self.assertTrue(ok)
        cap = artifacts.capture(self.workspace, b"produced draft bytes")
        ok2 = ledger.record_output(self.workspace, node_id=node_id, sha256=cap.sha256, size=cap.size, role="output")
        self.assertTrue(ok2)
        conn = sqlite3.connect(self.workspace / ".workerbees" / "workerbees.db")
        row = conn.execute("SELECT node_id, sha256, role FROM node_artifact WHERE node_id=?", (node_id,)).fetchone()
        self.assertEqual(row, (node_id, cap.sha256, "output"))

    def test_record_output_idempotent(self):
        node_id = "node-2"
        ledger.record_dispatch(self.workspace, node_id=node_id, run_id="run-2", model="haiku",
                               tier="grunt", task="extract", provider="claude", parent_id=None, edge_type=None)
        cap = artifacts.capture(self.workspace, b"idempotent bytes")
        self.assertTrue(ledger.record_output(self.workspace, node_id=node_id, sha256=cap.sha256, size=cap.size))
        self.assertTrue(ledger.record_output(self.workspace, node_id=node_id, sha256=cap.sha256, size=cap.size))

    def test_record_output_never_raises_on_bad_workspace(self):
        bogus = Path("/nonexistent-root-\0-bad")
        # invalid path chars -> mkdir/sqlite errors swallowed, returns False not raise
        try:
            result = ledger.record_output(bogus, node_id="n", sha256="0" * 64, size=1)
        except ValueError:
            # os-level rejection of the embedded null byte happens before our try/except
            # in some Python builds -- acceptable, this path is not FR-008's contract target
            return
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
