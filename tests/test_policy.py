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
        env = self._make_envelope(recipient="agent-reviewer-01")
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "NO_EDGE")

    def test_invalid_operation(self):
        env = self._make_envelope(operation="invalid_op")
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "OPERATION_NOT_ALLOWED")

    def test_invalid_schema(self):
        env = self._make_envelope(schema="invalid_schema")
        context = {"authenticated_sender": "agent-supervisor-01", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "SCHEMA_NOT_ALLOWED")

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

    def test_rule_order_unknown_sender_before_edge(self):
        """Verify unknown_sender is checked before edge."""
        env = self._make_envelope(sender="unknown-agent")
        context = {"authenticated_sender": "unknown-agent", "depth": 0, "budget_used": {},
                   "now": datetime.utcnow().isoformat() + "Z", "cancelled": False,
                   "policy_version": "1.0"}
        decision = evaluate(context, env, self.registry)
        self.assertEqual(decision.reason_code, "UNKNOWN_SENDER")
        unknown_idx = decision.checked_rules.index("known_sender")
        edge_idx = decision.checked_rules.index("edge_exists") if "edge_exists" in decision.checked_rules else None
        if edge_idx is not None:
            self.assertLess(unknown_idx, edge_idx)

if __name__ == "__main__":
    unittest.main()
