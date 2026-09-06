"""Governance matrix tests: feature flag matrix gates A-E.

GATE A: FLAG MATRIX (off, shadow, enforce) x (tim, dom) - status consistency
GATE B: SEEDED FAULTS - forged claims rejected in all modes
GATE C: ZERO-CALL DENIALS - real policy denial, no runner calls, zero ledger nodes
GATE D: AUDIT FAULT INJECTION - control layer failure vs. ledger failure behavior
GATE E: INVALID MODE - ValueError on unsupported WORKERBEES_GOVERNANCE
"""
import json, os, sqlite3, tempfile, unittest, shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from workerbees.pipeline import brief
from workerbees.adapters.base import WorkerResult
from workerbees.registry import Registry
from workerbees.gateway import Gateway, GatewayError
from workerbees.control import Control, ControlError
from workerbees.policy import PolicyError
from workerbees.ledger import load as load_ledger

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def fake_runner_factory(payload: dict, status="returned", call_count_list=None):
    """Factory returning a fake runner that tracks calls."""
    def runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
        if call_count_list is not None:
            call_count_list[0] += 1
        return WorkerResult(status, json.dumps(payload), "", 0 if status == "returned" else 1)
    return runner


def fake_runner_with_review_factory(worker_payload: dict, reviewer_verdict: dict, call_count_list=None):
    """Factory returning a fake runner that returns worker payload on first call, reviewer verdict on second."""
    call_counter = [0]
    def runner(cmd, stdin_text, timeout=300, cwd=None, **kwargs):
        call_counter[0] += 1
        if call_count_list is not None:
            call_count_list[0] += 1
        # First call is worker (returns claims + draft), second is reviewer (returns verdict)
        if call_counter[0] == 1:
            return WorkerResult("returned", json.dumps(worker_payload), "", 0)
        else:
            # Reviewer call returns verdict JSON
            return WorkerResult("returned", json.dumps(reviewer_verdict), "", 0)
    return runner


# ============================================================================
# GATE A: FLAG MATRIX (the headline gate)
# ============================================================================

class GateAFlagMatrix(unittest.TestCase):
    """A: FLAG MATRIX. 3 modes x 2 fixtures. Status must be identical across modes."""

    def setUp(self):
        self.ws_off = Path(tempfile.mkdtemp())
        self.ws_shadow = Path(tempfile.mkdtemp())
        self.ws_enforce = Path(tempfile.mkdtemp())

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]
        shutil.rmtree(str(self.ws_off), ignore_errors=True)
        shutil.rmtree(str(self.ws_shadow), ignore_errors=True)
        shutil.rmtree(str(self.ws_enforce), ignore_errors=True)

    def _test_fixture_matrix(self, fixture_name, source_file):
        """Test a single fixture across all 3 modes. Status must match."""
        exp = json.loads((FIX / fixture_name / "expected.json").read_text())
        payload = {
            "claims": [dict(text="t", **c) for c in exp["required_claims"]],
            "draft": "Brief summary (p2)."
        }

        # Mode: off
        call_count_off = [0]
        runner_off = fake_runner_factory(payload, call_count_list=call_count_off)
        r_off = brief(FIX / fixture_name / source_file, fixture_name, "lawyer",
                     self.ws_off, available={"claude", "codex"},
                     runner=runner_off, review_enabled=False, governance_mode="off")

        # Mode: shadow
        call_count_shadow = [0]
        runner_shadow = fake_runner_factory(payload, call_count_list=call_count_shadow)
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway_shadow = Gateway(workspace=self.ws_shadow, registry=registry, mode="shadow")
        r_shadow = brief(FIX / fixture_name / source_file, fixture_name, "lawyer",
                        self.ws_shadow, available={"claude", "codex"},
                        runner=runner_shadow, review_enabled=False, governance_mode="shadow",
                        registry=registry, gateway=gateway_shadow)

        # Mode: enforce
        call_count_enforce = [0]
        runner_enforce = fake_runner_factory(payload, call_count_list=call_count_enforce)
        gateway_enforce = Gateway(workspace=self.ws_enforce, registry=registry, mode="enforce")
        r_enforce = brief(FIX / fixture_name / source_file, fixture_name, "lawyer",
                         self.ws_enforce, available={"claude", "codex"},
                         runner=runner_enforce, review_enabled=False, governance_mode="enforce",
                         registry=registry, gateway=gateway_enforce)

        # Gate: all three modes must have identical status
        self.assertEqual(r_off.status, r_shadow.status,
                        f"Off mode status {r_off.status} != shadow {r_shadow.status} for {fixture_name}")
        self.assertEqual(r_off.status, r_enforce.status,
                        f"Off mode status {r_off.status} != enforce {r_enforce.status} for {fixture_name}")

        # Gate: shadow and enforce must record decisions in control.sqlite
        db_path_shadow = self.ws_shadow / ".workerbees" / "control.sqlite"
        db_path_enforce = self.ws_enforce / ".workerbees" / "control.sqlite"
        self.assertTrue(db_path_shadow.exists(), f"control.sqlite should exist for shadow mode in {fixture_name}")
        self.assertTrue(db_path_enforce.exists(), f"control.sqlite should exist for enforce mode in {fixture_name}")

        # Gate: decision count >= runner call count for shadow & enforce
        conn_shadow = sqlite3.connect(str(db_path_shadow))
        cursor_shadow = conn_shadow.cursor()
        decisions_shadow = cursor_shadow.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        conn_shadow.close()

        conn_enforce = sqlite3.connect(str(db_path_enforce))
        cursor_enforce = conn_enforce.cursor()
        decisions_enforce = cursor_enforce.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        conn_enforce.close()

        self.assertGreaterEqual(decisions_shadow, call_count_shadow[0],
                               f"Shadow decisions {decisions_shadow} < runner calls {call_count_shadow[0]} for {fixture_name}")
        self.assertGreaterEqual(decisions_enforce, call_count_enforce[0],
                               f"Enforce decisions {decisions_enforce} < runner calls {call_count_enforce[0]} for {fixture_name}")

    def test_a1_tim_matrix(self):
        """Gate A1: tim fixture across (off, shadow, enforce) -> identical status."""
        self._test_fixture_matrix("tim", "matter.md")

    def test_a2_dom_matrix(self):
        """Gate A2: dom fixture across (off, shadow, enforce) -> identical status."""
        self._test_fixture_matrix("dom", "design.md")

    def _test_fixture_matrix_reviewed(self, fixture_name, source_file):
        """Test a single fixture with review enabled across all 3 modes. Status must match."""
        exp = json.loads((FIX / fixture_name / "expected.json").read_text())
        worker_payload = {
            "claims": [dict(text="t", **c) for c in exp["required_claims"]],
            "draft": "Brief summary (p2)."
        }
        # All-ok reviewer verdict (matches format expected by reviewer.py)
        reviewer_verdict = {
            "verdicts": [{"claim": i, "ok": True, "issue": ""} for i in range(len(exp["required_claims"]))],
            "omissions": []
        }

        # Mode: off (review_enabled=True, same two-call runner as shadow/enforce)
        call_count_off = [0]
        runner_off = fake_runner_with_review_factory(worker_payload, reviewer_verdict, call_count_list=call_count_off)
        r_off = brief(FIX / fixture_name / source_file, fixture_name, "lawyer",
                     self.ws_off, available={"claude", "codex"},
                     runner=runner_off, review_enabled=True, governance_mode="off")

        # Mode: shadow (with review)
        call_count_shadow = [0]
        runner_shadow = fake_runner_with_review_factory(worker_payload, reviewer_verdict, call_count_list=call_count_shadow)
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway_shadow = Gateway(workspace=self.ws_shadow, registry=registry, mode="shadow")
        r_shadow = brief(FIX / fixture_name / source_file, fixture_name, "lawyer",
                        self.ws_shadow, available={"claude", "codex"},
                        runner=runner_shadow, review_enabled=True, governance_mode="shadow",
                        registry=registry, gateway=gateway_shadow)

        # Mode: enforce (with review)
        call_count_enforce = [0]
        runner_enforce = fake_runner_with_review_factory(worker_payload, reviewer_verdict, call_count_list=call_count_enforce)
        gateway_enforce = Gateway(workspace=self.ws_enforce, registry=registry, mode="enforce")
        r_enforce = brief(FIX / fixture_name / source_file, fixture_name, "lawyer",
                         self.ws_enforce, available={"claude", "codex"},
                         runner=runner_enforce, review_enabled=True, governance_mode="enforce",
                         registry=registry, gateway=gateway_enforce)

        # Gate: off, shadow, and enforce must have identical status
        self.assertEqual(r_off.status, "verified",
                        f"Off mode with verified claims should be verified; got {r_off.status}")
        self.assertEqual(r_off.status, r_shadow.status,
                        f"Off mode status {r_off.status} != shadow {r_shadow.status} for reviewed {fixture_name}")
        self.assertEqual(r_off.status, r_enforce.status,
                        f"Off mode status {r_off.status} != enforce {r_enforce.status} for reviewed {fixture_name}")

        # Gate: runner call counts must be identical across all three modes (governance must not add/drop calls)
        self.assertEqual(call_count_off[0], call_count_shadow[0],
                        f"Off mode runner calls {call_count_off[0]} != shadow {call_count_shadow[0]} for reviewed {fixture_name}")
        self.assertEqual(call_count_off[0], call_count_enforce[0],
                        f"Off mode runner calls {call_count_off[0]} != enforce {call_count_enforce[0]} for reviewed {fixture_name}")

        # Gate: shadow and enforce must record decisions for both worker and reviewer calls
        db_path_shadow = self.ws_shadow / ".workerbees" / "control.sqlite"
        db_path_enforce = self.ws_enforce / ".workerbees" / "control.sqlite"
        self.assertTrue(db_path_shadow.exists(), f"control.sqlite should exist for shadow mode in {fixture_name}")
        self.assertTrue(db_path_enforce.exists(), f"control.sqlite should exist for enforce mode in {fixture_name}")

        conn_shadow = sqlite3.connect(str(db_path_shadow))
        cursor_shadow = conn_shadow.cursor()
        decisions_shadow = cursor_shadow.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        conn_shadow.close()

        conn_enforce = sqlite3.connect(str(db_path_enforce))
        cursor_enforce = conn_enforce.cursor()
        decisions_enforce = cursor_enforce.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        conn_enforce.close()

        # Should have exactly 2 decision rows (one for worker, one for reviewer)
        self.assertEqual(decisions_shadow, 2,
                        f"Shadow decisions should include exactly worker+reviewer rows; got {decisions_shadow}")
        self.assertEqual(decisions_enforce, 2,
                        f"Enforce decisions should include exactly worker+reviewer rows; got {decisions_enforce}")

        # Gate: ledger should have exactly 2 nodes (worker + reviewer) for reviewed run
        ledger_shadow = load_ledger(self.ws_shadow)
        ledger_enforce = load_ledger(self.ws_enforce)

        self.assertEqual(len(ledger_shadow.nodes), 2,
                        f"Shadow ledger should have exactly 2 nodes (worker + reviewer); got {len(ledger_shadow.nodes)}")
        self.assertEqual(len(ledger_enforce.nodes), 2,
                        f"Enforce ledger should have exactly 2 nodes (worker + reviewer); got {len(ledger_enforce.nodes)}")

        # Gate: exactly one node in each ledger must have edge_type="reviews" with parent_id pointing to the other
        shadow_review_nodes = [n for n in ledger_shadow.nodes.values() if n.edge_type == "reviews"]
        self.assertEqual(len(shadow_review_nodes), 1,
                        f"Shadow ledger should have exactly 1 'reviews' edge, got {len(shadow_review_nodes)}")
        shadow_reviewer = shadow_review_nodes[0]
        shadow_worker_ids = [n.id for n in ledger_shadow.nodes.values() if n.parent_id is None]
        self.assertEqual(len(shadow_worker_ids), 1,
                        f"Shadow ledger should have exactly 1 worker node (no parent), got {len(shadow_worker_ids)}")
        self.assertEqual(shadow_reviewer.parent_id, shadow_worker_ids[0],
                        f"Shadow reviewer node parent_id should be worker id; got {shadow_reviewer.parent_id} vs {shadow_worker_ids[0]}")

        enforce_review_nodes = [n for n in ledger_enforce.nodes.values() if n.edge_type == "reviews"]
        self.assertEqual(len(enforce_review_nodes), 1,
                        f"Enforce ledger should have exactly 1 'reviews' edge, got {len(enforce_review_nodes)}")
        enforce_reviewer = enforce_review_nodes[0]
        enforce_worker_ids = [n.id for n in ledger_enforce.nodes.values() if n.parent_id is None]
        self.assertEqual(len(enforce_worker_ids), 1,
                        f"Enforce ledger should have exactly 1 worker node (no parent), got {len(enforce_worker_ids)}")
        self.assertEqual(enforce_reviewer.parent_id, enforce_worker_ids[0],
                        f"Enforce reviewer node parent_id should be worker id; got {enforce_reviewer.parent_id} vs {enforce_worker_ids[0]}")

    def test_a3_tim_matrix_reviewed(self):
        """Gate A3: tim fixture with review across (off, shadow, enforce) -> verified status."""
        self._test_fixture_matrix_reviewed("tim", "matter.md")

    def test_a4_dom_matrix_reviewed(self):
        """Gate A4: dom fixture with review across (off, shadow, enforce) -> verified status."""
        self._test_fixture_matrix_reviewed("dom", "design.md")


# ============================================================================
# GATE B: SEEDED FAULTS
# ============================================================================

class GateBSeededFaults(unittest.TestCase):
    """B: SEEDED FAULTS. Feed forged claims; status never 'verified' in any mode."""

    def setUp(self):
        self.ws_off = Path(tempfile.mkdtemp())
        self.ws_shadow = Path(tempfile.mkdtemp())
        self.ws_enforce = Path(tempfile.mkdtemp())

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]
        shutil.rmtree(str(self.ws_off), ignore_errors=True)
        shutil.rmtree(str(self.ws_shadow), ignore_errors=True)
        shutil.rmtree(str(self.ws_enforce), ignore_errors=True)

    def _test_fixture_faults(self, fixture_name, source_file):
        """Test a single fixture with forged claims. Status must reject in all modes."""
        faults = json.loads((FIX / fixture_name / "faults.json").read_text())
        forged = faults.get("forged", [])
        self.assertGreater(len(forged), 0, f"{fixture_name} must have ≥1 forged claim")

        payload_forged = {
            "claims": [dict(text="t", **c) for c in forged],
            "draft": "Brief summary (p2)."
        }

        # Mode: off
        runner_off = fake_runner_factory(payload_forged)
        r_off = brief(FIX / fixture_name / source_file, fixture_name, "lawyer",
                     self.ws_off, available={"claude", "codex"},
                     runner=runner_off, review_enabled=False, governance_mode="off")

        # Mode: shadow
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway_shadow = Gateway(workspace=self.ws_shadow, registry=registry, mode="shadow")
        runner_shadow = fake_runner_factory(payload_forged)
        r_shadow = brief(FIX / fixture_name / source_file, fixture_name, "lawyer",
                        self.ws_shadow, available={"claude", "codex"},
                        runner=runner_shadow, review_enabled=False, governance_mode="shadow",
                        registry=registry, gateway=gateway_shadow)

        # Mode: enforce
        gateway_enforce = Gateway(workspace=self.ws_enforce, registry=registry, mode="enforce")
        runner_enforce = fake_runner_factory(payload_forged)
        r_enforce = brief(FIX / fixture_name / source_file, fixture_name, "lawyer",
                         self.ws_enforce, available={"claude", "codex"},
                         runner=runner_enforce, review_enabled=False, governance_mode="enforce",
                         registry=registry, gateway=gateway_enforce)

        # Gate: forged claims must never result in "verified" status
        self.assertNotEqual(r_off.status, "verified",
                           f"Off mode should reject forged claims; got {r_off.status}")
        self.assertNotEqual(r_shadow.status, "verified",
                           f"Shadow mode should reject forged claims; got {r_shadow.status}")
        self.assertNotEqual(r_enforce.status, "verified",
                           f"Enforce mode should reject forged claims; got {r_enforce.status}")

        # Verify receipt contains source_integrity fail
        self.assertEqual(r_off.receipt.get("source_integrity"), "fail",
                        f"Off mode: source_integrity should be fail for forged claims")

        # Gate F3: In shadow and enforce, verify that governance permitted the dispatch call (allowed=1)
        # This proves the test exercises governance policy, not just the verifier.
        db_path_shadow = self.ws_shadow / ".workerbees" / "control.sqlite"
        db_path_enforce = self.ws_enforce / ".workerbees" / "control.sqlite"

        if db_path_shadow.exists():
            conn_shadow = sqlite3.connect(str(db_path_shadow))
            cursor_shadow = conn_shadow.cursor()
            allowed_decisions = cursor_shadow.execute("SELECT COUNT(*) FROM decisions WHERE allowed=1").fetchone()[0]
            conn_shadow.close()
            self.assertGreater(allowed_decisions, 0,
                             f"Shadow mode: governance should have permitted at least one dispatch call, but allowed decisions = {allowed_decisions}")

        if db_path_enforce.exists():
            conn_enforce = sqlite3.connect(str(db_path_enforce))
            cursor_enforce = conn_enforce.cursor()
            allowed_decisions = cursor_enforce.execute("SELECT COUNT(*) FROM decisions WHERE allowed=1").fetchone()[0]
            conn_enforce.close()
            self.assertGreater(allowed_decisions, 0,
                             f"Enforce mode: governance should have permitted at least one dispatch call, but allowed decisions = {allowed_decisions}")

    def test_b1_tim_forged(self):
        """Gate B1: tim fixture with forged claims rejected in all modes."""
        self._test_fixture_faults("tim", "matter.md")

    def test_b2_dom_forged(self):
        """Gate B2: dom fixture with forged claims rejected in all modes."""
        self._test_fixture_faults("dom", "design.md")


# ============================================================================
# GATE C: ZERO-CALL DENIALS
# ============================================================================

class GateCZeroCallDenials(unittest.TestCase):
    """C: ZERO-CALL DENIALS. Real policy denial -> no runner calls, decision recorded, zero ledger nodes."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]
        shutil.rmtree(str(self.ws), ignore_errors=True)

    def test_c1_classify_exceeded_denial(self):
        """Gate C1: CLASSIFICATION_EXCEEDED (real policy) -> blocked, no runner call, decision recorded."""
        # Create temp workerbees with modified governance (lower worker clearance)
        temp_wb = self.ws / "workerbees_temp"
        shutil.copytree(
            str(Path(__file__).resolve().parent.parent / "workerbees"),
            str(temp_wb)
        )

        # Lower agent-worker-01 clearance to public
        gov_data = json.loads((temp_wb / "governance.json").read_text())
        for agent in gov_data["agents"]:
            if agent["id"] == "agent-worker-01":
                agent["clearance"] = "public"
        (temp_wb / "governance.json").write_text(json.dumps(gov_data))

        registry = Registry.load(str(temp_wb))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")

        exp = json.loads((FIX / "tim" / "expected.json").read_text())
        payload = {
            "claims": [dict(text="t", **c) for c in exp["required_claims"]],
            "draft": "Brief summary (p2)."
        }

        call_count = [0]
        runner = fake_runner_factory(payload, call_count_list=call_count)

        # Call with confidential=True (should trigger CLASSIFICATION_EXCEEDED)
        r = brief(FIX / "tim" / "matter.md", "tim", "lawyer",
                 self.ws, available={"claude", "codex"},
                 runner=runner, review_enabled=False, governance_mode="enforce",
                 registry=registry, gateway=gateway, confidential=True)

        # Gate: status must be "blocked"
        self.assertEqual(r.status, "blocked",
                        f"Real policy denial should result in blocked status, got {r.status}")

        # Gate: runner should never have been called
        self.assertEqual(call_count[0], 0,
                        f"Runner should not be called on policy denial, but was called {call_count[0]} times")

        # Gate: exactly one decision should be recorded with allowed=0 and reason_code "CLASSIFICATION_EXCEEDED"
        db_path = self.ws / ".workerbees" / "control.sqlite"
        self.assertTrue(db_path.exists(), "control.sqlite should exist after denial")
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        decisions = cursor.execute("SELECT COUNT(*) FROM decisions WHERE allowed=0 AND reason_code=?",
                                   ("CLASSIFICATION_EXCEEDED",)).fetchone()[0]
        conn.close()
        self.assertEqual(decisions, 1,
                        f"Exactly one CLASSIFICATION_EXCEEDED denial should be recorded, got {decisions}")

        # Gate: zero ledger nodes (denial is not an invocation)
        ledger = load_ledger(self.ws)
        self.assertEqual(len(ledger.nodes), 0,
                        f"Denied request should not create ledger nodes, but found {len(ledger.nodes)}")


# ============================================================================
# GATE D: AUDIT FAULT INJECTION
# ============================================================================

class GateDFaultInjection(unittest.TestCase):
    """D: AUDIT FAULT INJECTION. Control failure -> denied. Ledger failure -> still works."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]
        shutil.rmtree(str(self.ws), ignore_errors=True)

    def test_d1_control_write_fails_blocks_dispatch(self):
        """Gate D1: Control layer write failure -> dispatch blocked, no runner call."""
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))

        # Create a workspace where control.sqlite cannot be written
        # (use a path that's not a directory)
        bad_ws = self.ws / "bad_workspace"
        bad_ws.mkdir(parents=True, exist_ok=True)
        control_path = bad_ws / ".workerbees" / "control.sqlite"
        control_path.parent.mkdir(parents=True, exist_ok=True)
        # Create a file at the DB path location
        control_path.write_text("not a database")

        gateway = Gateway(workspace=bad_ws, registry=registry, mode="enforce")

        exp = json.loads((FIX / "tim" / "expected.json").read_text())
        payload = {
            "claims": [dict(text="t", **c) for c in exp["required_claims"]],
            "draft": "Brief summary (p2)."
        }

        call_count = [0]
        runner = fake_runner_factory(payload, call_count_list=call_count)

        # Call brief with enforce mode (control layer should fail)
        r = brief(FIX / "tim" / "matter.md", "tim", "lawyer",
                 bad_ws, available={"claude", "codex"},
                 runner=runner, review_enabled=False, governance_mode="enforce",
                 registry=registry, gateway=gateway, confidential=False)

        # Gate: status should be "blocked" due to control layer failure
        self.assertEqual(r.status, "blocked",
                        f"Control write failure should result in 'blocked', got {r.status}")

        # Gate: runner should not have been called
        self.assertEqual(call_count[0], 0,
                        f"Runner should not be called when control fails, but was called {call_count[0]} times")

    def test_d2_ledger_write_fails_preserves_outcome(self):
        """Gate D2: Ledger write failure -> outcome preserved, runner called, process continues."""
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))
        gateway = Gateway(workspace=self.ws, registry=registry, mode="enforce")

        exp = json.loads((FIX / "tim" / "expected.json").read_text())
        payload = {
            "claims": [dict(text="t", **c) for c in exp["required_claims"]],
            "draft": "Brief summary (p2)."
        }

        call_count = [0]
        runner = fake_runner_factory(payload, call_count_list=call_count)

        # Patch both record_dispatch and record_return in the gateway module (where they're imported)
        # to fail. This accurately models ledger outage.
        with patch("workerbees.gateway.record_dispatch", side_effect=OSError("Ledger write failed")), \
             patch("workerbees.gateway.record_return", side_effect=OSError("Ledger write failed")):
            # Call should still proceed (ledger is best-effort)
            r = brief(FIX / "tim" / "matter.md", "tim", "lawyer",
                     self.ws, available={"claude", "codex"},
                     runner=runner, review_enabled=False, governance_mode="enforce",
                     registry=registry, gateway=gateway, confidential=False)

        # Gate: brief should have completed with expected status (not error/exception)
        self.assertIn(r.status, ["returned", "needs-review", "paused"],
                     f"Ledger failure should not crash; got status {r.status}")

        # Gate: runner should have been called (dispatch succeeded despite ledger failure)
        self.assertGreater(call_count[0], 0,
                          f"Runner should be called even if ledger fails; call_count={call_count[0]}")

        # Gate: outcome is preserved (status same as if ledger succeeded)
        # AND the failure was observed (if pipeline surfaces ledger_error in receipt)
        # OR ledger has zero nodes while runner was called
        ledger = load_ledger(self.ws)
        if "ledger_error" in r.receipt:
            self.assertEqual(r.receipt.get("ledger_error"), "write_failed",
                           f"Receipt should surface ledger error; got {r.receipt.get('ledger_error')}")
        else:
            # Ledger error not surfaced in receipt; verify fault was observed by empty ledger
            self.assertEqual(len(ledger.nodes), 0,
                           f"Ledger should be empty after write failure, but has {len(ledger.nodes)} nodes")


# ============================================================================
# GATE E: INVALID MODE
# ============================================================================

class GateEInvalidMode(unittest.TestCase):
    """E: INVALID MODE. Unsupported WORKERBEES_GOVERNANCE raises ValueError."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def tearDown(self):
        if "WORKERBEES_GOVERNANCE" in os.environ:
            del os.environ["WORKERBEES_GOVERNANCE"]
        shutil.rmtree(str(self.ws), ignore_errors=True)

    def test_e1_brief_invalid_mode_raises(self):
        """Gate E1: brief() with invalid governance_mode raises ValueError."""
        exp = json.loads((FIX / "tim" / "expected.json").read_text())
        payload = {
            "claims": [dict(text="t", **c) for c in exp["required_claims"]],
            "draft": "Brief summary (p2)."
        }
        runner = fake_runner_factory(payload)

        with self.assertRaises(ValueError) as ctx:
            brief(FIX / "tim" / "matter.md", "tim", "lawyer",
                 self.ws, available={"claude", "codex"},
                 runner=runner, review_enabled=False, governance_mode="invalid_mode")

        self.assertIn("Invalid WORKERBEES_GOVERNANCE mode", str(ctx.exception))

    def test_e2_gateway_invalid_mode_raises(self):
        """Gate E2: Gateway() with invalid mode raises GatewayError."""
        with self.assertRaises(GatewayError) as ctx:
            Gateway(workspace=self.ws, mode="invalid_mode")
        self.assertIn("Invalid WORKERBEES_GOVERNANCE mode", str(ctx.exception))

    def test_e3_env_invalid_mode_raises(self):
        """Gate E3: WORKERBEES_GOVERNANCE=invalid in env raises GatewayError on gateway init."""
        os.environ["WORKERBEES_GOVERNANCE"] = "invalid_mode"
        registry = Registry.load(str(Path(__file__).resolve().parent.parent / "workerbees"))

        with self.assertRaises(GatewayError) as ctx:
            Gateway(workspace=self.ws, registry=registry)
        self.assertIn("Invalid WORKERBEES_GOVERNANCE mode", str(ctx.exception))

        del os.environ["WORKERBEES_GOVERNANCE"]


if __name__ == "__main__":
    unittest.main()
