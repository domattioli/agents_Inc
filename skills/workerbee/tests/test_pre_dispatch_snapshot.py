"""Regression tests for pre_dispatch_snapshot.py path resolution."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = os.environ.get(
    "SNAPSHOT_SCRIPT",
    str(Path(__file__).resolve().parents[1] / "scripts" / "pre_dispatch_snapshot.py"),
)


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _run(cwd, *args):
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=cwd,
                          capture_output=True, text=True)


class SnapshotPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "t")
        _git(self.repo, "config", "core.quotepath", "true")
        self.snap = str(self.repo.parent / (self.repo.name + "-snap.json"))

    def tearDown(self):
        self.tmp.cleanup()
        if os.path.exists(self.snap):
            os.remove(self.snap)

    def _commit(self, rel):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("v1\n", encoding="utf-8")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "init")
        return p

    def test_subdir_capture_detects_second_edit(self):
        f = self._commit("sub/f")
        f.write_text("v2\n", encoding="utf-8")
        cwd = self.repo / "sub"
        self.assertEqual(_run(cwd, "capture", self.snap).returncode, 0)
        f.write_text("v3\n", encoding="utf-8")
        r = _run(cwd, "verify", self.snap)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CHANGED sub/f", r.stdout)

    def test_non_ascii_dirty_file_detected(self):
        f = self._commit("café.txt")
        f.write_text("v2\n", encoding="utf-8")
        self.assertEqual(_run(self.repo, "capture", self.snap).returncode, 0)
        f.write_text("v3\n", encoding="utf-8")
        r = _run(self.repo, "verify", self.snap)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("CHANGED café.txt", r.stdout)

    def test_unchanged_tree_verifies_clean(self):
        f = self._commit("café.txt")
        f.write_text("v2\n", encoding="utf-8")
        self.assertEqual(_run(self.repo, "capture", self.snap).returncode, 0)
        r = _run(self.repo, "verify", self.snap)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
