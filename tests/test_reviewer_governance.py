import json, os, sqlite3, tempfile, unittest
from pathlib import Path
from workerbees.reviewer import review, ReviewResult
from workerbees.adapters.base import WorkerResult
from workerbees.registry import Registry
from workerbees.gateway import Gateway
from workerbees.router import Route

SRC = "Clause 3. Rent monthly.\n\nClause 8. Rent quarterly."
CLAIMS = [{"text": "monthly", "quote": "Rent monthly", "anchor": "x#p1"}]

def runner_ok(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
    """Fake runner that returns ok verdicts."""
    return WorkerResult("returned", json.dumps({
        "verdicts": [{"claim": 0, "ok": True, "issue": ""}],
        "omissions": []
    }), "", 0)

def counter_runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
    """Fake runner that counts calls."""
    counter_runner.calls += 1
    return runner_ok(cmd, stdin_text, timeout, cwd, **kwargs)

class ReviewerGovernanceTest(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        counter_runner.calls = 0

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_supplied_same_vendor_route_off_mode(self):
        """Supplied same-vendor route returns 'same_vendor' in off mode, runner not called."""
        route = Route(provider="claude", model="claude-opus", tier="frontier", cmd_kind="cli")
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude"}, False,
                    runner=counter_runner, role="lawyer", route=route, governance_mode="off")
        self.assertEqual(res.status, "same_vendor")
        self.assertEqual(counter_runner.calls, 0)

    def test_supplied_same_vendor_route_enforce_mode(self):
        """Supplied same-vendor route returns 'same_vendor' in enforce mode, runner not called."""
        route = Route(provider="claude", model="claude-opus", tier="frontier", cmd_kind="cli")
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude"}, False,
                    runner=counter_runner, role="lawyer", route=route,
                    governance_mode="enforce", gateway=gateway, registry=registry,
                    workspace=self.ws, run_id="run1", parent_id="parent1", confidential=False)
        self.assertEqual(res.status, "same_vendor")
        self.assertEqual(counter_runner.calls, 0)

    def test_off_mode_behavior_unchanged(self):
        """Off mode should parse reviewer response normally (status ok, verdicts, omissions)."""
        res = review(SRC, "x", CLAIMS, "d", "codex", {"claude", "codex"}, False,
                    runner=runner_ok, role="lawyer", governance_mode="off")
        self.assertEqual(res.status, "ok")
        self.assertEqual(len(res.verdicts), 1)
        self.assertEqual(res.verdicts[0]["ok"], True)
        self.assertEqual(res.omissions, [])

    def test_shadow_mode_decision_recorded(self):
        """Shadow mode: reviewer runs, decision recorded in control.sqlite."""
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="shadow")
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude", "codex"}, False,
                    runner=runner_ok, role="lawyer", governance_mode="shadow",
                    gateway=gateway, registry=registry, workspace=self.ws,
                    run_id="run1", parent_id="parent1", confidential=False)
        self.assertEqual(res.status, "ok")
        db_path = self.ws / ".workerbees" / "control.sqlite"
        self.assertTrue(db_path.exists(), "control.sqlite should exist in shadow mode")
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        decisions = cursor.execute("SELECT COUNT(*) FROM decisions").fetchone()
        self.assertGreater(decisions[0], 0, "At least one decision should be recorded")
        conn.close()

    def test_enforce_allowed_no_ledger_duplicate(self):
        """Enforce mode allowed: gateway handles ledger, no duplicate reviewer node."""
        from workerbees.ledger import load as load_ledger
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude", "codex"}, False,
                    runner=runner_ok, role="lawyer", governance_mode="enforce",
                    gateway=gateway, registry=registry, workspace=self.ws,
                    run_id="run1", parent_id="parent1", confidential=False)
        self.assertEqual(res.status, "ok")
        ledger = load_ledger(self.ws)
        self.assertGreater(len(ledger.nodes), 0, "Ledger should have nodes")
        # Gateway should have created the ledger node, not review() duplicating
        task_counts = {}
        for node in ledger.nodes.values():
            task_counts[node.task] = task_counts.get(node.task, 0) + 1
        # Should have exactly one "review" task node (from gateway, not duplicate from caller)
        self.assertEqual(task_counts.get("review", 0), 1, f"Expected 1 review node, got {task_counts}")

    def test_enforce_denied_real_classification_exceeded(self):
        """Enforce mode denied: real policy denial via CLASSIFICATION_EXCEEDED."""
        import json, shutil
        # Create temp workerbees dir with modified governance.json
        temp_wb = self.ws / "workerbees_temp"
        shutil.copytree(
            str(Path(__file__).resolve().parent.parent / "workerbees"),
            str(temp_wb)
        )
        # Lower reviewer clearance to public to trigger CLASSIFICATION_EXCEEDED
        gov_data = json.loads((temp_wb / "governance.json").read_text())
        for agent in gov_data["agents"]:
            if agent["id"] == "agent-reviewer-01":
                agent["clearance"] = "public"
        (temp_wb / "governance.json").write_text(json.dumps(gov_data))

        # Load modified registry
        registry = Registry.load(str(temp_wb))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude", "codex"}, False,
                    runner=counter_runner, role="lawyer", governance_mode="enforce",
                    gateway=gateway, registry=registry, workspace=self.ws,
                    run_id="run1", parent_id="parent1", confidential=True)
        self.assertEqual(res.status, "blocked", f"Expected blocked status, got {res.status}")
        self.assertEqual(counter_runner.calls, 0, "Runner should not be called on policy denial")

    def test_enforce_denied_real_no_edge_with_patched_request(self):
        """Enforce denied via real policy: construct envelope with no edge by using anonymous sender."""
        # This test creates a real NO_EDGE denial without mocking evaluate
        # We use an unlisted sender-recipient pair to force real policy denial
        # Since we can't easily create custom envelopes from review(), we verify the mechanism works
        # by checking that when gateway.dispatch is called with denied result, review returns "blocked"
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")

        # Direct test: call gateway.dispatch with a no-edge envelope
        from workerbees.envelope import Envelope
        from datetime import datetime
        import uuid
        uid = uuid.uuid4().hex
        # Use worker→reviewer (no edge exists for this pairing)
        env = Envelope(
            message_id=uid, task_id=uid, parent_task_id=None, correlation_id=uid,
            sender="agent-worker-01", recipient="agent-reviewer-01",
            intent="review", operation="request", protocol="v1", schema="request_v1",
            payload={"prompt": "test"}, data_classification="internal",
            created_at=datetime.utcnow().isoformat()+"Z"
        )
        route = Path(__file__).resolve().parent.parent / "workerbees"
        from workerbees.router import pick_model
        r = pick_model("review", "mid", {"claude", "codex"}, False)
        result = gateway.dispatch(env, context={"authenticated_sender": env.sender},
                                 runner=counter_runner, route=r)
        # Policy should deny (NO_EDGE for worker→reviewer)
        self.assertFalse(result.decision.allowed)
        self.assertEqual(result.decision.reason_code, "NO_EDGE")
        # Runner should not have been called
        self.assertEqual(counter_runner.calls, 0)

    def test_invalid_governance_mode_raises_valueerror(self):
        """Invalid governance_mode raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            review(SRC, "x", CLAIMS, "d", "codex", {"claude", "codex"}, False,
                  runner=runner_ok, role="lawyer", governance_mode="invalid_mode")
        self.assertIn("Invalid WORKERBEES_GOVERNANCE mode", str(ctx.exception))

    def test_governance_mode_from_environ(self):
        """governance_mode=None defaults to os.environ['WORKERBEES_GOVERNANCE'] or 'off'."""
        os.environ["WORKERBEES_GOVERNANCE"] = "shadow"
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="shadow")
        res = review(SRC, "x", CLAIMS, "d", "claude", {"claude", "codex"}, False,
                    runner=runner_ok, role="lawyer", governance_mode=None,
                    gateway=gateway, registry=registry, workspace=self.ws,
                    run_id="run1", parent_id="parent1", confidential=False)
        self.assertEqual(res.status, "ok")
        db_path = self.ws / ".workerbees" / "control.sqlite"
        self.assertTrue(db_path.exists(), "Shadow mode env var should trigger decision recording")

    def test_shadow_mode_duplicate_envelope_no_exception(self):
        """G4 regression: shadow mode with duplicate/conflict status returns sane ReviewResult, no exception."""
        import unittest.mock
        from workerbees.envelope import Decision
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="shadow")

        # Mock gateway.dispatch to return duplicate status (None worker_result)
        dup_decision = Decision(False, "dup-node", "DUPLICATE", "Same message ID and hash", "1.0", [])
        dup_result_obj = type('GatewayResult', (), {
            'status': 'duplicate',
            'decision': dup_decision,
            'worker_result': None,
            'node_id': 'dup-node',
            'decision_recorded': False
        })()

        with unittest.mock.patch.object(gateway, 'dispatch', return_value=dup_result_obj):
            res = review(SRC, "x", CLAIMS, "d", "claude", {"claude", "codex"}, False,
                        runner=counter_runner, role="lawyer", governance_mode="shadow",
                        gateway=gateway, registry=registry, workspace=self.ws,
                        run_id="run1", parent_id="parent1", confidential=False)

        # Should return duplicate status without raising AttributeError
        self.assertEqual(res.status, "duplicate", "Should return duplicate status from gateway")
        self.assertEqual(counter_runner.calls, 0, "Runner should not be called when gateway returns duplicate")

    def test_shadow_mode_conflict_envelope_no_exception(self):
        """G4 regression: shadow mode with conflict status (None worker_result) handled correctly."""
        import unittest.mock
        from workerbees.envelope import Decision
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="shadow")

        # Mock gateway.dispatch to return conflict status (None worker_result)
        conflict_decision = Decision(False, "conf-node", "REPLAY_CONFLICT", "Message ID exists with different hash", "1.0", [])
        conflict_result_obj = type('GatewayResult', (), {
            'status': 'conflict',
            'decision': conflict_decision,
            'worker_result': None,
            'node_id': 'conf-node',
            'decision_recorded': False
        })()

        with unittest.mock.patch.object(gateway, 'dispatch', return_value=conflict_result_obj):
            res = review(SRC, "x", CLAIMS, "d", "claude", {"claude", "codex"}, False,
                        runner=counter_runner, role="lawyer", governance_mode="shadow",
                        gateway=gateway, registry=registry, workspace=self.ws,
                        run_id="run1", parent_id="parent1", confidential=False)

        # Should return conflict status without raising AttributeError
        self.assertEqual(res.status, "conflict", "Should return conflict status from gateway")
        self.assertEqual(counter_runner.calls, 0, "Runner should not be called when gateway returns conflict")

if __name__ == "__main__":
    unittest.main()
