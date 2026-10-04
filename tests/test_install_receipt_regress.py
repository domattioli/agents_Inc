"""Receipt stays correct after a failed repair (W2 #1) and after rollback (W2 #2)."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _rmtree(path):
    def onerror(func, p, _):
        os.chmod(p, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
        func(p)
    for dirpath, dirnames, _ in os.walk(path):
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), 0o700)
    shutil.rmtree(path, onerror=onerror)


class TestInstallReceiptRegressions(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp()).resolve()
        self.src = self.home / "src"
        for item in ("agents_inc", "skills/workerbee", "skills/codex-bridge"):
            shutil.copytree(ROOT / item, self.src / item, ignore=shutil.ignore_patterns("__pycache__", "*.bak"))
        self.receipt = self.home / ".config/agents-inc/install.json"

    def tearDown(self):
        _rmtree(self.home)

    def _cli(self, *argv):
        env = dict(os.environ, HOME=str(self.home), PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-m", "agents_inc.install.cli", *argv],
                              cwd=self.home, env=env, capture_output=True, text=True)

    def _install(self, command="install"):
        return self._cli(command, "--source", str(self.src), "--without-codex", "--no-host-wiring")

    def _touch_source(self, tag):
        with open(self.src / "agents_inc" / "__init__.py", "a") as fh:
            fh.write(f"# {tag}\n")

    def test_failed_repair_keeps_receipt(self):
        self.assertEqual(self._install().returncode, 0)
        before = json.loads(self.receipt.read_text())
        marker = self.home / ".local/state/agents-inc/source-checkout"
        marker.unlink()
        marker.mkdir()  # makes the source-checkout write fail inside repair
        self._touch_source("change")
        r = self._install("repair")
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(self.receipt.is_file(), r.stderr)
        self.assertEqual(json.loads(self.receipt.read_text())["release_hash"], before["release_hash"])

    def test_rollback_updates_release_hash(self):
        self.assertEqual(self._install().returncode, 0)
        first = json.loads(self.receipt.read_text())["release_hash"]
        self._touch_source("change")
        self.assertEqual(self._install("repair").returncode, 0)
        self.assertNotEqual(json.loads(self.receipt.read_text())["release_hash"], first)
        r = self._cli("rollback")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.receipt.read_text())["release_hash"], first)
        doctor = self._cli("doctor")
        self.assertNotIn("WB_RELEASE_UNTRUSTED", doctor.stdout)

    def test_rollback_restores_prior_receipt_verbatim(self):
        self.assertEqual(self._install().returncode, 0)
        first = self.receipt.read_bytes()
        self._touch_source("change")
        self.assertEqual(self._install("repair").returncode, 0)
        # Change python_path in the live receipt: synthesis would carry this over.
        live = json.loads(self.receipt.read_text()); live["python_path"] = "/usr/bin/other-python"
        self.receipt.write_text(json.dumps(live))
        r = self._cli("rollback")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.receipt.read_bytes(), first)

    def test_verify_failure_rolls_back_install(self):
        self.assertEqual(self._install().returncode, 0)
        before = self.receipt.read_bytes()
        current = os.readlink(self.home / ".local/share/agents-inc/current")
        self._touch_source("change")
        code = ("import sys; from pathlib import Path; import agents_inc.install.cli as c\n"
                "def bad(p): raise RuntimeError('WB_INSTALL_UNVERIFIED: forced')\n"
                "c.verify_installed = bad\n"
                "sys.exit(c.main(['install','--source',sys.argv[1],'--without-codex','--no-host-wiring']))")
        env = dict(os.environ, HOME=str(self.home), PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, "-c", code, str(self.src)], cwd=self.home, env=env, capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.receipt.read_bytes(), before)
        self.assertEqual(os.readlink(self.home / ".local/share/agents-inc/current"), current)


if __name__ == "__main__":
    unittest.main()
