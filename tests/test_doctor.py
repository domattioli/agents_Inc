import json, tempfile, unittest
from pathlib import Path
from workerbees import doctor
from workerbees.adapters.base import WorkerResult

def fake(status, out="", err=""):
    def r(cmd, stdin_text, timeout=300, cwd=None): return WorkerResult(status, out, err, 0 if status=="returned" else 1)
    return r

class DoctorTest(unittest.TestCase):
    def setUp(self): self.ws = Path(tempfile.mkdtemp())
    def test_pong_is_ok(self):
        self.assertEqual(doctor.probe_cli("claude", runner=fake("returned", "PONG"))["status"], "ok")
    def test_not_logged_in(self):
        self.assertEqual(doctor.probe_cli("claude", runner=fake("returned", "Not logged in · Please run /login"))["status"], "WB_AUTH_REQUIRED")
    def test_missing_cli(self):
        self.assertEqual(doctor.probe_cli("codex", runner=fake("failed", "", "WB_CLI_NOT_FOUND: x"))["status"], "WB_CLI_NOT_FOUND")
    def test_quota(self):
        self.assertEqual(doctor.probe_cli("codex", runner=fake("paused", "", "usage limit"))["status"], "WB_QUOTA_EXHAUSTED")
    def test_run_writes_cache_and_available_skips_failed(self):
        calls = {"n": 0}
        def r(cmd, stdin_text, timeout=300, cwd=None):
            calls["n"] += 1
            return WorkerResult("returned", "PONG" if cmd[0] == "claude" else "Not logged in", "", 0)
        doctor.run(self.ws, runner=r)
        cache = json.loads((self.ws / ".workerbees" / "doctor.json").read_text())
        self.assertEqual(cache["results"]["codex"]["status"], "WB_AUTH_REQUIRED")
        self.assertEqual(doctor.available(self.ws, env_path=self.ws / "no.env"), {"claude"})
    def test_quota_paused_listed(self):
        def r(cmd, stdin_text, timeout=300, cwd=None):
            if cmd[0] == "claude": return WorkerResult("paused", "", "usage limit", 1)
            else: return WorkerResult("returned", "PONG", "", 0)
        result = doctor.run(self.ws, runner=r)
        self.assertIn("paused", result)
        self.assertEqual(result["paused"], ["claude"])
        paused = doctor.quota_paused(self.ws)
        self.assertEqual(paused, ["claude"])

class DoctorLedgerTest(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def test_doctor_run_creates_ledger_with_probe_nodes(self):
        """T022: doctor.run() records N probe nodes with edge_type='probes'."""
        from workerbees.ledger import load
        
        calls = {"n": 0}
        def r(cmd, stdin_text, timeout=300, cwd=None):
            calls["n"] += 1
            return WorkerResult("returned", "PONG", "", 0)
        
        doctor.run(self.ws, runner=r)
        ledger = load(self.ws)
        
        # Should have 2 nodes (claude and codex probes)
        self.assertEqual(len(ledger.nodes), 2)
        
        # All should have edge_type="probes" and parent_id=None
        for node in ledger.nodes.values():
            self.assertEqual(node.edge_type, "probes")
            self.assertIsNone(node.parent_id)
            self.assertEqual(node.task, "probe")
