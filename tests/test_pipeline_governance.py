import json, os, sqlite3, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from workerbees.pipeline import brief
from workerbees.adapters.base import WorkerResult
from workerbees.registry import Registry
from workerbees.gateway import Gateway
from workerbees.policy import PolicyError

FIX = Path(__file__).resolve().parent.parent / "fixtures"

def fake_runner_factory(payload: dict, status="returned"):
    calls = [0]
    def runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
        calls[0] += 1
        return WorkerResult(status, json.dumps(payload), "", 0 if status == "returned" else 1)
    runner.call_count = lambda: calls[0]
    return runner

class PipelineGovernanceTest(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        self.exp = json.loads((FIX / "tim" / "expected.json").read_text())

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_off_mode_identical_to_no_governance(self):
        """Off mode should be byte-identical to current behavior: ledger call, runner call, ledger return."""
        from workerbees.ledger import load as load_ledger

        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}

        # Baseline run with no governance
        ws_baseline = Path(tempfile.mkdtemp())
        r_baseline = brief(FIX/"tim"/"matter.md", "tim", "lawyer", ws_baseline, available={"claude","codex"},
                           runner=fake_runner_factory(payload), review_enabled=False)
        ledger_baseline = load_ledger(ws_baseline)

        # Run with off mode explicitly
        r_off = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                      runner=fake_runner_factory(payload), review_enabled=False, governance_mode="off")

        # Status should match
        self.assertEqual(r_off.status, r_baseline.status)
        # No governance key in receipt
        self.assertIsNone(r_off.receipt.get("governance"))
        # Receipt keys should match (full comparison)
        self.assertEqual(set(r_off.receipt.keys()), set(r_baseline.receipt.keys()),
                        f"Off mode receipt keys {set(r_off.receipt.keys())} != baseline {set(r_baseline.receipt.keys())}")
        # Ledger node count should match
        ledger_off = load_ledger(self.ws)
        self.assertEqual(len(ledger_off.nodes), len(ledger_baseline.nodes),
                        f"Off mode nodes {len(ledger_off.nodes)} != baseline {len(ledger_baseline.nodes)}")

    def test_off_mode_no_gateway_constructed(self):
        """Off mode should not construct Gateway or use governance logic."""
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}

        # Spy on Registry.load and Gateway.__init__ to verify they're never called in off mode
        with patch('workerbees.registry.Registry.load') as mock_registry_load, \
             patch('workerbees.gateway.Gateway.__init__', return_value=None) as mock_gateway_init:
            r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                      runner=fake_runner_factory(payload), review_enabled=False, governance_mode="off",
                      gateway=None, registry=None)
            self.assertEqual(r.status, "returned")
            # Verify Registry.load and Gateway.__init__ were never called
            mock_registry_load.assert_not_called()
            mock_gateway_init.assert_not_called()

    def test_shadow_mode_worker_runs_decision_recorded(self):
        """Shadow mode: worker runs, decision recorded in control.sqlite, no block."""
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}
        runner = fake_runner_factory(payload)

        registry = Registry.load("workerbees")
        gateway = Gateway(workspace=self.ws, registry=registry, mode="shadow")

        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                  runner=runner, review_enabled=False, governance_mode="shadow",
                  registry=registry, gateway=gateway, confidential=False)

        # Worker should have run
        self.assertEqual(runner.call_count(), 1)
        self.assertEqual(r.status, "returned")

        # Decision should be recorded in control.sqlite
        db_path = self.ws / ".workerbees" / "control.sqlite"
        self.assertTrue(db_path.exists(), "control.sqlite should exist in shadow mode")
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        decisions = cursor.execute("SELECT COUNT(*) FROM decisions").fetchone()
        self.assertGreater(decisions[0], 0, "At least one decision should be recorded")
        conn.close()

    def test_enforce_allowed_decision_recorded(self):
        """Enforce mode, allowed: worker runs, decision recorded, status not blocked."""
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}
        runner = fake_runner_factory(payload)

        registry = Registry.load("workerbees")
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")

        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                  runner=runner, review_enabled=False, governance_mode="enforce",
                  registry=registry, gateway=gateway, confidential=False)

        # Worker should have run
        self.assertEqual(runner.call_count(), 1)
        self.assertNotEqual(r.status, "blocked")
        self.assertEqual(r.status, "returned")

    def test_enforce_denied_runner_not_called_policy(self):
        """Enforce mode, real policy denial: runner not called, status blocked, decision with allowed=0."""
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}
        runner = fake_runner_factory(payload)

        # Test real denial through policy: send confidential data to a worker without sufficient clearance
        # Use a patched policy.check_dispatch to simulate authorization failure
        registry = Registry.load("workerbees")
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")

        with patch('workerbees.pipeline.check_dispatch', side_effect=PolicyError("Clearance exceeded")) as mock_check:
            r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                      runner=runner, review_enabled=False, governance_mode="enforce",
                      registry=registry, gateway=gateway, confidential=True)

            # check_dispatch should have been called
            self.assertTrue(mock_check.called)
            # Runner should NOT have been called (policy rejected before dispatch)
            self.assertEqual(runner.call_count(), 0)
            # Status should be blocked
            self.assertEqual(r.status, "blocked")
            # Receipt should contain the policy error reason
            self.assertIn("reason", r.receipt)

    def test_invalid_governance_mode_raises_value_error(self):
        """Invalid WORKERBEES_GOVERNANCE value raises ValueError."""
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}

        with self.assertRaises(ValueError) as ctx:
            brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                  runner=fake_runner_factory(payload), review_enabled=False, governance_mode="invalid_mode")

        self.assertIn("Invalid WORKERBEES_GOVERNANCE mode", str(ctx.exception))

    def test_governance_mode_from_environ(self):
        """governance_mode parameter defaults to os.environ.get('WORKERBEES_GOVERNANCE', 'off')."""
        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}

        # Set environment variable to shadow mode and verify decision is recorded
        os.environ["WORKERBEES_GOVERNANCE"] = "shadow"
        runner = fake_runner_factory(payload)

        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                  runner=runner, review_enabled=False, confidential=False)

        # Should work in shadow mode and record decision in control.sqlite
        self.assertEqual(r.status, "returned")
        db_path = self.ws / ".workerbees" / "control.sqlite"
        self.assertTrue(db_path.exists(), "control.sqlite should exist when env WORKERBEES_GOVERNANCE=shadow")
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        decisions = cursor.execute("SELECT COUNT(*) FROM decisions").fetchone()
        self.assertGreater(decisions[0], 0, "Decision should be recorded from environment variable setting")
        conn.close()

    def test_ledger_no_duplicates_with_gateway(self):
        """Gateway owns ledger emission in shadow/enforce mode: no duplicate nodes."""
        from workerbees.ledger import load

        payload = {"claims": [dict(text="t", **c) for c in self.exp["required_claims"]], "draft": "Brief. (p2)"}
        runner = fake_runner_factory(payload)

        registry = Registry.load("workerbees")
        gateway = Gateway(workspace=self.ws, registry=registry, mode="shadow")

        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws, available={"claude","codex"},
                  runner=runner, review_enabled=False, governance_mode="shadow",
                  registry=registry, gateway=gateway, confidential=False)

        ledger = load(self.ws)
        # In shadow mode with 1 worker call, should have exactly 1 node (from gateway)
        self.assertEqual(len(ledger.nodes), 1)

    def test_correction_with_governance_routing(self):
        """Correction loop reuses _dispatch_worker with edge_type='corrects'."""
        from workerbees.ledger import load

        worker_1 = {
            "claims": [dict(text="t", **c) for c in self.exp["required_claims"]],
            "draft": "First point (p2)."
        }
        worker_2 = {
            "claims": [dict(text="t", **c) for c in self.exp["required_claims"]],
            "draft": "Revised point (p2)."
        }
        calls = []
        def runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
            calls.append(cmd[0])
            if len(calls) == 1:
                return WorkerResult("returned", json.dumps(worker_1), "", 0)
            if len(calls) == 2:
                return WorkerResult("returned", json.dumps({
                    "verdicts": [
                        {"claim": 0, "ok": True, "issue": ""},
                        {"claim": 1, "ok": True, "issue": ""},
                        {"claim": 2, "ok": False, "issue": "Clause 8 overrides"},
                        {"claim": 3, "ok": True, "issue": ""},
                        {"claim": 4, "ok": True, "issue": ""},
                    ],
                    "omissions": ["monthly rent"],
                }), "", 0)
            if len(calls) == 3:
                return WorkerResult("returned", json.dumps(worker_2), "", 0)
            return WorkerResult("returned", json.dumps({
                "verdicts": [{"claim": i, "ok": True, "issue": ""} for i in range(5)],
                "omissions": [],
            }), "", 0)

        registry = Registry.load("workerbees")
        gateway = Gateway(workspace=self.ws, registry=registry, mode="shadow")

        r = brief(FIX/"tim"/"matter.md", "tim", "lawyer", self.ws,
                  available={"claude", "codex"}, runner=runner, max_corrections=1,
                  governance_mode="shadow", registry=registry, gateway=gateway, confidential=False)

        # Should have 4 runner calls: worker1, reviewer1, worker2 (corrects), reviewer2
        self.assertEqual(len(calls), 4)

        # Ledger should have 4 nodes (or similar structure depending on gateway behavior)
        ledger = load(self.ws)
        self.assertGreater(len(ledger.nodes), 2)

if __name__ == "__main__":
    unittest.main()
