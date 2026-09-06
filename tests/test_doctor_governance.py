"""Governance integration tests for doctor.py probes."""
import json, os, sqlite3, tempfile, unittest, shutil
from pathlib import Path
from workerbees import doctor
from workerbees.adapters.base import WorkerResult
from workerbees.registry import Registry
from workerbees.gateway import Gateway
from workerbees.router import Route


def counter_runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
    """Fake runner that counts calls and returns PONG."""
    counter_runner.calls += 1
    return WorkerResult("returned", "PONG", "", 0)


def gateway_pong_runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
    """Fake runner for gateway path that returns PONG."""
    gateway_pong_runner.calls += 1
    return WorkerResult("returned", "PONG", "", 0)


class DoctorGovernanceOffModeTest(unittest.TestCase):
    """Off mode: byte-identical to original behavior."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        counter_runner.calls = 0

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_off_mode_probe_unchanged(self):
        """Off mode probe_cli returns ok status, ledger node written by doctor."""
        from workerbees.ledger import load as load_ledger
        run_id = "test-run-1"
        result = doctor.probe_cli("claude", runner=counter_runner, workspace=self.ws,
                                 run_id=run_id, governance_mode="off")
        self.assertEqual(result["status"], "ok")
        self.assertIn("detail", result)
        self.assertIn("at", result)

        # Verify ledger node was written by doctor, not gateway
        ledger = load_ledger(self.ws)
        probe_nodes = [n for n in ledger.nodes.values() if n.task == "probe"]
        self.assertEqual(len(probe_nodes), 1)
        self.assertEqual(probe_nodes[0].edge_type, "probes")
        self.assertIsNone(probe_nodes[0].parent_id)

    def test_off_mode_run_unchanged(self):
        """Off mode run() writes cache, behavior unchanged."""
        result = doctor.run(self.ws, providers=("claude", "codex"), runner=counter_runner,
                           governance_mode="off")
        self.assertIn("results", result)
        self.assertEqual(len(result["results"]), 2)
        cache_file = self.ws / ".workerbees" / "doctor.json"
        self.assertTrue(cache_file.exists())
        cache = json.loads(cache_file.read_text())
        self.assertIn("results", cache)


class DoctorGovernanceShadowModeTest(unittest.TestCase):
    """Shadow mode: decision recorded, probe runs."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        gateway_pong_runner.calls = 0

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_shadow_mode_probe_runs_decision_recorded(self):
        """Shadow mode: probe runs, decision recorded in control.sqlite."""
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="shadow")
        run_id = "test-run-shadow"
        result = doctor.probe_cli("claude", runner=gateway_pong_runner, workspace=self.ws,
                                 run_id=run_id, governance_mode="shadow", gateway=gateway,
                                 registry=registry)
        self.assertEqual(result["status"], "ok")

        # Verify control.sqlite exists with decision record
        db_path = self.ws / ".workerbees" / "control.sqlite"
        self.assertTrue(db_path.exists())
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        decisions = cursor.execute("SELECT COUNT(*) FROM decisions").fetchone()
        self.assertGreater(decisions[0], 0)
        conn.close()


class DoctorGovernanceEnforceModeTest(unittest.TestCase):
    """Enforce mode allowed: probe runs, gateway handles ledger, no duplicates."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        gateway_pong_runner.calls = 0

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_enforce_allowed_probe_runs_one_node(self):
        """Enforce allowed: probe runs, exactly one node per probe, parent_id=None."""
        from workerbees.ledger import load as load_ledger
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")
        run_id = "test-run-enforce"
        result = doctor.probe_cli("claude", runner=gateway_pong_runner, workspace=self.ws,
                                 run_id=run_id, governance_mode="enforce", gateway=gateway,
                                 registry=registry)
        self.assertEqual(result["status"], "ok")

        # Verify ledger has exactly one node per probe (no duplicate from doctor)
        ledger = load_ledger(self.ws)
        self.assertGreater(len(ledger.nodes), 0)
        probe_nodes = [n for n in ledger.nodes.values() if n.task == "probe"]
        self.assertEqual(len(probe_nodes), 1, f"Expected 1 probe node, got {len(probe_nodes)}")

        # Verify parent_id is None (ROOT node)
        self.assertIsNone(probe_nodes[0].parent_id)
        self.assertEqual(probe_nodes[0].edge_type, "probes")

    def test_enforce_allowed_run_multiple_probes(self):
        """Enforce allowed: run() with multiple providers creates one ledger node each."""
        from workerbees.ledger import load as load_ledger
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")

        result = doctor.run(self.ws, providers=("claude", "codex"), runner=gateway_pong_runner,
                           governance_mode="enforce", gateway=gateway, registry=registry)
        self.assertIn("results", result)
        self.assertEqual(len(result["results"]), 2)

        # Both should succeed in enforce allowed
        self.assertEqual(result["results"]["claude"]["status"], "ok")
        self.assertEqual(result["results"]["codex"]["status"], "ok")

        # Verify ledger has exactly 2 probe nodes
        ledger = load_ledger(self.ws)
        probe_nodes = [n for n in ledger.nodes.values() if n.task == "probe"]
        self.assertEqual(len(probe_nodes), 2, f"Expected 2 probe nodes, got {len(probe_nodes)}")

        # All should have parent_id=None
        for node in probe_nodes:
            self.assertIsNone(node.parent_id)


class DoctorGovernanceEnforceDeniedTest(unittest.TestCase):
    """Enforce denied: real policy denial via NO_EDGE."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        counter_runner.calls = 0

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_enforce_denied_no_edge_real_policy(self):
        """Enforce denied: real policy denial when edge is missing."""
        # Copy workerbees to temp dir and remove the doctor delegates_to edge
        temp_wb = self.ws / "workerbees_temp"
        shutil.copytree(
            str(Path(__file__).resolve().parent.parent / "workerbees"),
            str(temp_wb)
        )

        # Remove the supervisor->doctor delegates_to edge
        gov_data = json.loads((temp_wb / "governance.json").read_text())
        relationships = gov_data["relationships"]
        gov_data["relationships"] = [
            r for r in relationships
            if not (r.get("source_agent_id") == "agent-supervisor-01" and
                   r.get("target_agent_id") == "agent-doctor-01" and
                   r.get("relationship_type") == "delegates_to")
        ]
        (temp_wb / "governance.json").write_text(json.dumps(gov_data))

        registry = Registry.load(str(temp_wb))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")

        result = doctor.probe_cli("claude", runner=counter_runner, workspace=self.ws,
                                 run_id="test-run", governance_mode="enforce",
                                 gateway=gateway, registry=registry)

        # Should return governance-denied status
        self.assertTrue(result["status"].startswith("WB_GOVERNANCE_"))
        self.assertIn("delegates_to", result["detail"])

        # Runner should not be called
        self.assertEqual(counter_runner.calls, 0)


class DoctorNoBootstrapRecursionTest(unittest.TestCase):
    """No bootstrap recursion: doctor.available() never called from gateway path."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_no_available_call_in_enforce_mode(self):
        """Enforce mode probe_cli never calls doctor.available()."""
        import unittest.mock
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")

        def pong_runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
            return WorkerResult("returned", "PONG", "", 0)

        # Patch doctor.available to assert it's not called
        with unittest.mock.patch("workerbees.doctor.available", wraps=doctor.available) as mock_avail:
            result = doctor.probe_cli("claude", runner=pong_runner, workspace=self.ws,
                                     run_id="test", governance_mode="enforce",
                                     gateway=gateway, registry=registry)
            self.assertEqual(result["status"], "ok")
            # Assert available() was never called
            mock_avail.assert_not_called()

    def test_no_available_call_in_run_enforce(self):
        """Enforce mode run() never calls doctor.available()."""
        import unittest.mock
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")

        def pong_runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
            return WorkerResult("returned", "PONG", "", 0)

        with unittest.mock.patch("workerbees.doctor.available", wraps=doctor.available) as mock_avail:
            result = doctor.run(self.ws, providers=("claude",), runner=pong_runner,
                               governance_mode="enforce", gateway=gateway, registry=registry)
            self.assertEqual(result["results"]["claude"]["status"], "ok")
            mock_avail.assert_not_called()


class DoctorGovernanceModeValidationTest(unittest.TestCase):
    """Invalid mode raises ValueError."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_invalid_mode_raises_valueerror(self):
        """Invalid governance_mode raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            doctor.probe_cli("claude", runner=lambda *a, **k: WorkerResult("returned", "PONG", "", 0),
                           workspace=self.ws, run_id="test",
                           governance_mode="invalid_mode")
        self.assertIn("Invalid WORKERBEES_GOVERNANCE mode", str(ctx.exception))

    def test_invalid_mode_in_run_raises_valueerror(self):
        """Invalid governance_mode in run() raises ValueError."""
        with self.assertRaises(ValueError):
            doctor.run(self.ws, runner=lambda *a, **k: WorkerResult("returned", "PONG", "", 0),
                      governance_mode="invalid_mode")


class DoctorGovernanceModeEnvTest(unittest.TestCase):
    """governance_mode=None defaults to env var or 'off'."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_mode_from_environ(self):
        """governance_mode=None defaults to WORKERBEES_GOVERNANCE env var."""
        os.environ["WORKERBEES_GOVERNANCE"] = "off"
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="off")

        result = doctor.probe_cli("claude", runner=lambda *a, **k: WorkerResult("returned", "PONG", "", 0),
                                workspace=self.ws, run_id="test",
                                governance_mode=None, gateway=gateway, registry=registry)
        self.assertEqual(result["status"], "ok")


class DoctorAvailableGovernanceWiringTest(unittest.TestCase):
    """T1: doctor.available() forwards governance params to run() without exception."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_available_with_governance_params(self):
        """T1: doctor.available() accepts and forwards governance params."""
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")

        def pong_runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
            return WorkerResult("returned", "PONG", "", 0)

        # Should not raise AttributeError; should return a sane set
        result = doctor.available(self.ws, governance_mode="enforce", gateway=gateway, registry=registry,
                                 runner=pong_runner)
        self.assertIsInstance(result, set)


class DoctorAvailableRegressionB1Test(unittest.TestCase):
    """T2: Regression for B1 — doctor.available() with env WORKERBEES_GOVERNANCE=enforce, no gateway param."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_available_env_enforce_no_gateway_param(self):
        """T2: doctor.available() reads WORKERBEES_GOVERNANCE from env, should not raise AttributeError."""
        os.environ["WORKERBEES_GOVERNANCE"] = "enforce"

        def pong_runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
            return WorkerResult("returned", "PONG", "", 0)

        # With env WORKERBEES_GOVERNANCE=enforce but no gateway param passed,
        # doctor.available() calls run(), which calls probe_cli(),
        # which should return WB_GOVERNANCE_NO_GATEWAY (not raise AttributeError).
        result = doctor.available(self.ws, runner=pong_runner)
        self.assertIsInstance(result, set)


class DoctorProbePickModelNoneGuardTest(unittest.TestCase):
    """T3: B3 guard — pick_model returns None should not crash gateway.dispatch."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_probe_cli_route_none_guard(self):
        """T3: probe_cli returns WB_NO_ELIGIBLE_ROUTE when pick_model returns None."""
        import unittest.mock
        from workerbees import router
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")

        def pong_runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
            return WorkerResult("returned", "PONG", "", 0)

        # Patch pick_model to return None (patches at router module level where it's imported from)
        with unittest.mock.patch.object(router, "pick_model", return_value=None):
            result = doctor.probe_cli("claude", runner=pong_runner, workspace=self.ws,
                                     run_id="test", governance_mode="enforce",
                                     gateway=gateway, registry=registry)
            self.assertEqual(result["status"], "WB_NO_ELIGIBLE_ROUTE")


class DoctorProbePickModelNoneCallCounterTest(unittest.TestCase):
    """T3 variant: track calls to runner when pick_model returns None."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        self.call_count = 0

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_probe_cli_route_none_no_runner_calls(self):
        """T3: when pick_model returns None, runner should not be called."""
        import unittest.mock
        from workerbees import router
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")

        def counting_runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
            self.call_count += 1
            return WorkerResult("returned", "PONG", "", 0)

        with unittest.mock.patch.object(router, "pick_model", return_value=None):
            result = doctor.probe_cli("claude", runner=counting_runner, workspace=self.ws,
                                     run_id="test", governance_mode="enforce",
                                     gateway=gateway, registry=registry)
            self.assertEqual(result["status"], "WB_NO_ELIGIBLE_ROUTE")
            self.assertEqual(self.call_count, 0, f"Expected 0 runner calls, got {self.call_count}")


class DoctorAvailablePipelineE2ETest(unittest.TestCase):
    """T4: End-to-end pipeline.brief() with enforce mode, no explicit available arg."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        # Create minimal source file
        self.src = self.ws / "test_source.md"
        self.src.write_text("[p1] Claim here: evidence.\n\n[p2] Another claim: more evidence.")

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]

    def test_pipeline_brief_enforce_mode_no_available_arg(self):
        """T4: pipeline.brief() in enforce mode without available= param."""
        from workerbees import pipeline
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))

        def pong_runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
            # For extract task, return a valid JSON response
            return WorkerResult("returned", '{"claims":[],"draft":"test"}', "", 0)

        # Call brief in enforce mode, WITHOUT available= arg
        # This forces it to call doctor.available() internally
        result = pipeline.brief(
            self.src, "test_source", "strict", self.ws,
            runner=pong_runner, governance_mode="enforce",
            gateway=Gateway(workspace=self.ws, registry=registry, mode="enforce"),
            registry=registry
        )
        # Should return a BriefResult with no AttributeError
        self.assertIsNotNone(result)
        self.assertIsInstance(result, pipeline.BriefResult)


if __name__ == "__main__":
    unittest.main()
