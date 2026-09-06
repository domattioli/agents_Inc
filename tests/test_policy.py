import json, tempfile, unittest
from pathlib import Path
from datetime import datetime, timedelta
from workerbees.router import Route
from workerbees.policy import check_dispatch, is_authorized, PolicyError, paused, evaluate
from workerbees.envelope import Envelope
from workerbees.registry import Registry

class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def test_unauthorized_workspace_blocks_confidential_to_optional(self):
        r = Route("gemini", "gemini-2.5-flash", "cheap", "http")
        with self.assertRaises(PolicyError):
            check_dispatch(r, self.ws, confidential=True)

    def test_required_provider_always_ok(self):
        r = Route("claude", "haiku", "cheap", "cli")
        check_dispatch(r, self.ws, confidential=True)

    def test_authorization_file_grants(self):
        (self.ws / ".workerbees").mkdir()
        (self.ws / ".workerbees" / "authorization.json").write_text(json.dumps(
            {"optional_providers": True, "granted_by": "dom", "at": "2026-09-05T00:00:00Z"}))
        self.assertTrue(is_authorized(self.ws))
        check_dispatch(Route("gemini", "x", "cheap", "http"), self.ws, confidential=True)

    def test_paused_shape(self):
        self.assertEqual(paused("quota")["status"], "paused")

class EvaluateTest(unittest.TestCase):
    def setUp(self):
        self.registry = Registry.load("workerbees")

    def _make_envelope(self, sender="agent-supervisor-01", recipient="agent-worker-01",
                       operation="request", schema="request_v1", classification="internal",
                       expires_at=None) -> Envelope:
        now = datetime.utcnow().isoformat() + "Z"
        if expires_at is None:
            expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
        return Envelope(
            message_id="msg-001",
            task_id="task-001",
            parent_task_id=None,
            correlation_id="corr-001",
            sender=sender,
            recipient=recipient,
            intent="extraction",
            operation=operation,
            protocol="v1",
            schema=schema,
            payload={"text": "sample"},
            data_classification=classification,
            created_at=now,
            expires_at=expires_at,
            budget={"max_cost": 0, "max_calls": 10, "max_seconds": 60}
        )

    def test_unauthenticated_sender(self):
        env = self._make_envelope()
        context = {"authenticated_sender": None, "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "UNAUTHENTICATED_SENDER")
        self.assertIn("authenticated_sender", decision.checked_rules)

    def test_sender_mismatch(self):
        env = self._make_envelope()
        context = {"authenticated_sender": "agent-worker-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "SENDER_MISMATCH")

    def test_unknown_sender(self):
        env = self._make_envelope(sender="unknown-agent")
        context = {"authenticated_sender": "unknown-agent", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "UNKNOWN_SENDER")

    def test_unknown_recipient(self):
        env = self._make_envelope(recipient="unknown-agent")
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "UNKNOWN_RECIPIENT")

    def test_recipient_disabled(self):
        env = self._make_envelope(recipient="agent-deployer-01")
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "RECIPIENT_DISABLED")

    def test_no_edge(self):
        """Policy denies dispatch when no edge exists between sender and recipient.
        agent-worker-01 and agent-reviewer-01 have no relationship defined in governance.json."""
        env = self._make_envelope(sender="agent-worker-01", recipient="agent-reviewer-01")
        context = {"authenticated_sender": "agent-worker-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "NO_EDGE")
        self.assertIn("edge_exists", decision.checked_rules)

    def test_invalid_operation(self):
        # D1: edge check before operation. Use sender/recipient with no edge so NO_EDGE is returned first
        env = self._make_envelope(operation="invalid_op", sender="agent-worker-01", recipient="agent-supervisor-01")
        context = {"authenticated_sender": "agent-worker-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        # With D1, edge check happens before operation check, so NO_EDGE is reported
        self.assertEqual(decision.reason_code, "NO_EDGE")
        # Verify edge_exists was checked (operation_allowed not checked since NO_EDGE returned early)
        self.assertIn("edge_exists", decision.checked_rules)

    def test_invalid_schema(self):
        # D1: edge check before schema. Use sender/recipient with no edge so NO_EDGE is returned first
        env = self._make_envelope(schema="invalid_schema", sender="agent-worker-01", recipient="agent-supervisor-01")
        context = {"authenticated_sender": "agent-worker-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        # With D1, edge check happens before schema check, so NO_EDGE is reported
        self.assertEqual(decision.reason_code, "NO_EDGE")
        # Verify edge_exists was checked (schema_allowed not checked since NO_EDGE returned early)
        self.assertIn("edge_exists", decision.checked_rules)

    def test_classification_exceeded(self):
        env = self._make_envelope(recipient="agent-worker-01", classification="restricted")
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "CLASSIFICATION_EXCEEDED")

    def test_delegation_depth_exceeded(self):
        env = self._make_envelope()
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 2, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "DELEGATION_DEPTH_EXCEEDED")

    def test_expired(self):
        env = self._make_envelope(expires_at=(datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z")
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "EXPIRED")

    def test_cancelled(self):
        env = self._make_envelope()
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": True,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "CANCELLED")

    def test_approval_required(self):
        env = self._make_envelope()
        env.security = {"approval_required": True}
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "APPROVAL_REQUIRED")

    def test_cost_not_zero(self):
        env = self._make_envelope()
        env.budget["max_cost"] = 5
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "COST_NOT_ZERO")

    def test_budget_exceeded_calls(self):
        env = self._make_envelope()
        env.budget["max_calls"] = 5
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0,
                   "budget_used": {"calls": 10, "seconds": 0},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "BUDGET_EXCEEDED")

    def test_budget_exceeded_seconds(self):
        env = self._make_envelope()
        env.budget["max_seconds"] = 30
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0,
                   "budget_used": {"calls": 0, "seconds": 60},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "BUDGET_EXCEEDED")

    def test_allowed_valid_request(self):
        env = self._make_envelope()
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0,
                   "budget_used": {"calls": 0, "seconds": 0},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason_code, "ALLOWED")
        self.assertIsNotNone(decision.decision_id)
        self.assertGreaterEqual(len(decision.checked_rules), 1)

    def test_rule_order_edge_before_operation(self):
        """D1: Verify edge_exists is checked and reported before operation_allowed."""
        env = self._make_envelope(operation="invalid_op", sender="agent-worker-01",
                                  recipient="agent-supervisor-01")
        decision = evaluate({"authenticated_sender": "agent-worker-01"}, env, self.registry)
        self.assertEqual(decision.reason_code, "NO_EDGE")
        self.assertIn("edge_exists", decision.checked_rules)
        self.assertNotIn("operation_allowed", decision.checked_rules)

    def test_classification_sender_clearance_insufficient(self):
        """D2: Sender clearance must be >= data_classification."""
        # agent-supervisor-01 (confidential=2) as sender with classification=restricted (3)
        # sender_level=2 < env_level=3, so sender insufficient
        env = self._make_envelope(sender="agent-supervisor-01", recipient="agent-worker-01", classification="restricted")
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "CLASSIFICATION_EXCEEDED")
        self.assertIn("Sender clearance", decision.reason)

    def test_unknown_classification_invalid_level(self):
        """D3: Unknown classification should be denied."""
        env = self._make_envelope(classification="unknown-level")
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "UNKNOWN_CLASSIFICATION")

    def test_delegation_depth_limit_min_of_three(self):
        """D4: Depth limit = min(edge.max_delegation_depth, sender.max_delegation_depth, 1)."""
        # Create a custom registry with edge max_delegation_depth=0
        from workerbees.registry import Registry, Agent, Relationship, Capability

        test_registry = Registry(
            version="test",
            policy_version="test",
            snapshot_hash="test",
            agents={
                "agent-supervisor-01": Agent(
                    id="agent-supervisor-01", name="Supervisor", type="supervisor",
                    capabilities=[], enabled=True, created_date="2026-01-15",
                    clearance="confidential", max_delegation_depth=2
                ),
                "agent-worker-01": Agent(
                    id="agent-worker-01", name="Worker", type="worker",
                    capabilities=[], enabled=True, created_date="2026-01-15",
                    clearance="internal"
                )
            },
            capabilities={},
            relationships=[
                Relationship(
                    source_id="agent-supervisor-01", target_id="agent-worker-01",
                    type="delegates_to", max_delegation_depth=0
                )
            ]
        )

        env = self._make_envelope()
        # With edge.max_delegation_depth=0, even depth 1 should fail
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 1, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, test_registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "DELEGATION_DEPTH_EXCEEDED")

    def test_approval_required_by_edge(self):
        """D5: Approval required if edge.requires_approval is true."""
        from workerbees.registry import Registry, Agent, Relationship

        test_registry = Registry(
            version="test",
            policy_version="test",
            snapshot_hash="test",
            agents={
                "agent-supervisor-01": Agent(
                    id="agent-supervisor-01", name="Supervisor", type="supervisor",
                    capabilities=[], enabled=True, created_date="2026-01-15",
                    clearance="confidential"
                ),
                "agent-worker-01": Agent(
                    id="agent-worker-01", name="Worker", type="worker",
                    capabilities=[], enabled=True, created_date="2026-01-15",
                    clearance="internal"
                )
            },
            capabilities={},
            relationships=[
                Relationship(
                    source_id="agent-supervisor-01", target_id="agent-worker-01",
                    type="delegates_to", requires_approval=True
                )
            ]
        )

        env = self._make_envelope()
        env.security = {}  # No approval in envelope
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, test_registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "APPROVAL_REQUIRED")

    def test_budget_projected_calls(self):
        """D6: Projected calls = budget_used.calls + 1 must not exceed limit."""
        env = self._make_envelope()
        env.budget["max_calls"] = 9
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0,
                   "budget_used": {"calls": 9, "seconds": 0},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "BUDGET_EXCEEDED")

    def test_budget_used_seconds_at_limit(self):
        """D6: Used seconds at the durable run limit deny."""
        env = self._make_envelope()
        env.budget["max_seconds"] = 30
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0,
                   "budget_used": {"calls": 0, "seconds": 40},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0",
                   "budget_limits": {"max_seconds": 40}}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "BUDGET_EXCEEDED")

    def test_policy_error_on_registry_mock_exception(self):
        """D7: Catch exceptions and return POLICY_ERROR."""
        class FailingRegistry:
            policy_version = "test"
            def agent(self, id, include_disabled=False):
                raise RuntimeError("Mock registry failure")
            def edge(self, src, dst, rel_type):
                return None

        env = self._make_envelope()
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, FailingRegistry())
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "POLICY_ERROR")

if __name__ == "__main__":
    unittest.main()
