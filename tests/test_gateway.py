"""Tests for workerbees.gateway.Gateway governance dispatch."""
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

from workerbees.gateway import Gateway, GatewayError, GatewayResult
from workerbees.envelope import Envelope, Decision, ArtifactRef
from workerbees.registry import Registry, Agent, Capability, Relationship
from workerbees.router import Route
from workerbees.control import Control, ControlError
from workerbees.adapters.base import WorkerResult


class FakeRegistry(Registry):
    """Registry fixture for testing."""
    def __init__(self):
        super().__init__(
            version="1.0",
            policy_version="1.0",
            snapshot_hash="test",
            agents={
                "supervisor": Agent(
                    id="supervisor", name="Supervisor", type="system",
                    capabilities=[], enabled=True, created_date="2026-01-01",
                    clearance="internal"
                ),
                "worker": Agent(
                    id="worker", name="Worker", type="execution",
                    capabilities=["extract"], enabled=True, created_date="2026-01-01",
                    clearance="internal"
                ),
                "reviewer": Agent(
                    id="reviewer", name="Reviewer", type="judgment",
                    capabilities=["review"], enabled=True, created_date="2026-01-01",
                    clearance="internal"
                ),
            },
            capabilities={
                "extract": Capability(id="extract", name="extract", enabled=True),
                "review": Capability(id="review", name="review", enabled=True),
            },
            relationships=[
                Relationship(
                    source_id="supervisor", target_id="worker",
                    type="delegates_to", max_delegation_depth=1,
                    requires_approval=False
                ),
                Relationship(
                    source_id="supervisor", target_id="reviewer",
                    type="delegates_to", max_delegation_depth=1,
                    requires_approval=False
                ),
            ]
        )


def make_envelope(sender="supervisor", recipient="worker", operation="request",
                  **overrides) -> Envelope:
    """Create a test envelope."""
    defaults = {
        "message_id": "msg-1",
        "task_id": "task-1",
        "parent_task_id": None,
        "correlation_id": "corr-1",
        "sender": sender,
        "recipient": recipient,
        "intent": "extract",
        "operation": operation,
        "protocol": "workerbees",
        "schema": "request_v1",
        "payload": {"prompt": "test prompt"},
        "data_classification": "internal",
        "created_at": "2026-01-01T00:00:00Z",
        "expires_at": None,
        "deadline": None,
        "reply_to": None,
        "required_artifacts": [],
        "budget": {"max_calls": 10, "max_seconds": 60},
        "provenance": {},
        "security": {},
    }
    defaults.update(overrides)
    return Envelope.from_dict(defaults)


def fake_runner(cmd, stdin_text, timeout=300, cwd=None):
    """Fake runner that counts calls and returns success."""
    fake_runner.call_count = getattr(fake_runner, 'call_count', 0) + 1
    fake_runner.last_cmd = cmd
    fake_runner.last_stdin = stdin_text
    return WorkerResult("returned", "output", "", 0)


class GatewayTest(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)
        self.workerbees_dir = self.workspace / ".workerbees"
        self.workerbees_dir.mkdir(parents=True, exist_ok=True)
        self.registry = FakeRegistry()
        fake_runner.call_count = 0
        fake_runner.last_cmd = None
        fake_runner.last_stdin = None

    def tearDown(self):
        """Clean up fixtures."""
        self.tmpdir.cleanup()

    def test_bad_mode_env_raises_gateway_error(self):
        """Unsupported mode value raises GatewayError at init."""
        with patch.dict('os.environ', {'WORKERBEES_GOVERNANCE': 'invalid'}):
            with self.assertRaises(GatewayError):
                Gateway(self.workspace, registry=self.registry)

    def test_enforce_mode_requires_registry(self):
        """enforce mode without registry raises GatewayError."""
        with patch.dict('os.environ', {'WORKERBEES_GOVERNANCE': 'enforce'}):
            with self.assertRaises(GatewayError):
                Gateway(self.workspace)

    def test_off_mode_default(self):
        """Default mode is off."""
        gw = Gateway(self.workspace)
        self.assertEqual(gw.mode, "off")

    def test_invalid_envelope_denied_zero_calls(self):
        """Invalid envelope → ENVELOPE_INVALID, zero runner calls."""
        gw = Gateway(self.workspace, registry=self.registry, mode="enforce")
        # Create envelope with unknown fields (triggers validation error)
        env = make_envelope()
        # Manually corrupt the envelope to have an invalid operation
        env.operation = "invalid_operation"
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1"}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertEqual(result.status, "envelope_invalid")
        self.assertFalse(result.decision.allowed)
        self.assertIsNone(result.worker_result)
        self.assertEqual(fake_runner.call_count, 0)

    def test_allowed_request_one_call_decision_recorded(self):
        """Allowed request → 1 call, decision recorded, node_id set."""
        gw = Gateway(self.workspace, registry=self.registry, mode="enforce")
        env = make_envelope()
        route = Route("claude", "haiku", "cheap", "cli")
        context = {
            "authenticated_sender": "supervisor",
            "run_id": "run-1",
            "depth": 0,
            "budget_used": {"calls": 0, "seconds": 0.0},
        }

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertEqual(result.status, "allowed")
        self.assertTrue(result.decision.allowed)
        self.assertEqual(fake_runner.call_count, 1)
        self.assertTrue(result.decision_recorded)
        self.assertIsNotNone(result.node_id)

    def test_unknown_recipient_denied_in_enforce(self):
        """Unknown recipient denied in enforce → 0 calls, decision recorded."""
        gw = Gateway(self.workspace, registry=self.registry, mode="enforce")
        env = make_envelope(recipient="unknown_agent")
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1"}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertEqual(result.status, "denied")
        self.assertFalse(result.decision.allowed)
        self.assertEqual(result.decision.reason_code, "UNKNOWN_RECIPIENT")
        self.assertEqual(fake_runner.call_count, 0)
        self.assertTrue(result.decision_recorded)

    def test_unknown_recipient_shadow_one_call_plus_decision(self):
        """Unknown recipient in shadow → 1 call + recorded decision."""
        gw = Gateway(self.workspace, registry=self.registry, mode="shadow")
        env = make_envelope(recipient="unknown_agent")
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1"}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        # Shadow mode: decision recorded but execution proceeds
        self.assertEqual(fake_runner.call_count, 1)
        self.assertTrue(result.decision_recorded)

    def test_off_mode_no_policy_side_effects(self):
        """Off mode → no policy call side effects but still runs."""
        gw = Gateway(self.workspace, registry=self.registry, mode="off")
        env = make_envelope(recipient="unknown_agent")  # Would fail in enforce
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1"}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        # Off mode: execution proceeds, no policy evaluation
        self.assertEqual(result.status, "allowed")
        self.assertEqual(fake_runner.call_count, 1)

    def test_duplicate_message_same_hash_zero_calls(self):
        """Duplicate message_id same hash → 0 calls, status duplicate."""
        gw = Gateway(self.workspace, registry=self.registry, mode="enforce")
        env = make_envelope(message_id="msg-1", payload={"prompt": "test prompt"})
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1"}

        # First call: allowed
        result1 = gw.dispatch(env, context=context, runner=fake_runner, route=route)
        self.assertEqual(result1.status, "allowed")
        self.assertEqual(fake_runner.call_count, 1)

        # Second call with same envelope (same message_id and payload) → duplicate
        fake_runner.call_count = 0
        result2 = gw.dispatch(env, context=context, runner=fake_runner, route=route)
        self.assertEqual(result2.status, "duplicate")
        self.assertEqual(fake_runner.call_count, 0)

    def test_conflict_different_payload_same_message_id(self):
        """Conflict (same message_id, different hash) → denied, 0 calls."""
        gw = Gateway(self.workspace, registry=self.registry, mode="enforce")
        env1 = make_envelope(message_id="msg-1")
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1"}

        # First call
        result1 = gw.dispatch(env1, context=context, runner=fake_runner, route=route)
        self.assertEqual(result1.status, "allowed")

        # Second call with same message_id but different payload
        env2 = make_envelope(message_id="msg-1", payload={"prompt": "different"})
        fake_runner.call_count = 0
        result2 = gw.dispatch(env2, context=context, runner=fake_runner, route=route)

        self.assertEqual(result2.status, "conflict")
        self.assertFalse(result2.decision.allowed)
        self.assertEqual(fake_runner.call_count, 0)

    def test_audit_unavailable_in_enforce_blocked(self):
        """Audit unavailable in enforce → blocked, 0 calls."""
        # Create a control that fails on replay check (simulating audit unavailable)
        mock_control = Mock(spec=Control)
        mock_control.check_replay.side_effect = ControlError("DB connection failed")

        gw = Gateway(self.workspace, registry=self.registry, control=mock_control, mode="enforce")
        env = make_envelope()
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1"}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertEqual(result.status, "blocked")
        self.assertEqual(fake_runner.call_count, 0)

    def test_provider_not_executable_denied(self):
        """Non-claude/codex provider → PROVIDER_NOT_EXECUTABLE, 0 calls."""
        gw = Gateway(self.workspace, registry=self.registry, mode="enforce")
        env = make_envelope()
        route = Route("gemini", "gemini-pro", "cheap", "http")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1"}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertEqual(result.status, "denied")
        self.assertEqual(result.decision.reason_code, "PROVIDER_NOT_EXECUTABLE")
        self.assertEqual(fake_runner.call_count, 0)

    def test_decision_contains_reason_code_and_checked_rules(self):
        """Decision includes reason_code and checked_rules."""
        gw = Gateway(self.workspace, registry=self.registry, mode="enforce")
        env = make_envelope(recipient="unknown_agent")
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1"}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertIsNotNone(result.decision.reason_code)
        self.assertIsInstance(result.decision.checked_rules, list)

    def test_allowed_in_shadow_executes_despite_invalid_context(self):
        """Shadow mode executes even if policy would deny."""
        gw = Gateway(self.workspace, registry=self.registry, mode="shadow")
        env = make_envelope()
        # Missing authenticated_sender (would fail policy)
        context = {"run_id": "run-1"}
        route = Route("claude", "haiku", "cheap", "cli")

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        # Shadow still executes
        self.assertEqual(fake_runner.call_count, 1)

    def test_node_id_in_result(self):
        """Result includes unique node_id."""
        gw = Gateway(self.workspace, registry=self.registry, mode="off")
        env = make_envelope()
        route = Route("claude", "haiku", "cheap", "cli")
        context = {}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertIsNotNone(result.node_id)
        self.assertGreater(len(result.node_id), 0)

    def test_claude_adapter_called_with_correct_model(self):
        """Claude provider builds command with correct model."""
        with patch('workerbees.adapters.claude.build_cmd') as mock_claude:
            mock_claude.return_value = ["claude", "-p", "--model", "haiku"]

            gw = Gateway(self.workspace, registry=self.registry, mode="off")
            env = make_envelope()
            route = Route("claude", "haiku", "cheap", "cli")
            context = {}

            gw.dispatch(env, context=context, runner=fake_runner, route=route)

            mock_claude.assert_called_once_with("haiku")

    def test_codex_adapter_called_with_correct_model(self):
        """Codex provider builds command with correct model."""
        with patch('workerbees.adapters.codex.build_cmd') as mock_codex:
            mock_codex.return_value = ["codex", "exec", "-m", "gpt-5.4-mini"]

            gw = Gateway(self.workspace, registry=self.registry, mode="off")
            env = make_envelope()
            route = Route("codex", "gpt-5.4-mini", "mid", "cli")
            context = {"cwd": "/tmp"}

            gw.dispatch(env, context=context, runner=fake_runner, route=route)

            mock_codex.assert_called_once_with("gpt-5.4-mini", "/tmp")

    def test_worker_result_returned_on_success(self):
        """Successful run returns worker_result."""
        gw = Gateway(self.workspace, registry=self.registry, mode="off")
        env = make_envelope()
        route = Route("claude", "haiku", "cheap", "cli")
        context = {}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertIsNotNone(result.worker_result)
        self.assertEqual(result.worker_result.status, "returned")
        self.assertEqual(result.worker_result.output, "output")

    def test_decision_recorded_flag_set_correctly(self):
        """decision_recorded flag reflects control.record_decision success."""
        gw = Gateway(self.workspace, registry=self.registry, mode="enforce")
        env = make_envelope()
        route = Route("claude", "haiku", "cheap", "cli")
        context = {
            "authenticated_sender": "supervisor",
            "run_id": "run-1",
            "depth": 0,
            "budget_used": {"calls": 0, "seconds": 0.0},
        }

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertTrue(result.decision_recorded)

    def test_decision_id_in_result(self):
        """Decision includes decision_id."""
        gw = Gateway(self.workspace, registry=self.registry, mode="enforce")
        env = make_envelope()
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1"}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertIsNotNone(result.decision)
        self.assertIsNotNone(result.decision.decision_id)
        self.assertGreater(len(result.decision.decision_id), 0)

    def test_decision_id_available_in_result(self):
        """Decision in result includes decision_id for audit logging."""
        gw = Gateway(self.workspace, registry=self.registry, mode="off")
        env = make_envelope()
        route = Route("claude", "haiku", "cheap", "cli")
        context = {}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertIsNotNone(result.decision)
        self.assertIsNotNone(result.decision.decision_id)
        self.assertGreater(len(result.decision.decision_id), 0)

    def test_cancellation_before_reserve(self):
        """is_cancelled check before reserve → status cancelled, 0 calls."""
        mock_control = Mock(spec=Control)
        mock_control.check_replay.return_value = Mock(state="new")
        mock_control.is_cancelled.return_value = True
        mock_control.record_decision.return_value = True

        gw = Gateway(self.workspace, registry=self.registry, control=mock_control, mode="enforce")
        env = make_envelope()
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1"}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(fake_runner.call_count, 0)

    def test_cancellation_before_invoke(self):
        """is_cancelled check before invoke → status cancelled, release called, 0 calls."""
        mock_control = Mock(spec=Control)
        mock_control.check_replay.return_value = Mock(state="new")
        # First call (before reserve) returns False, second (before invoke) returns True
        mock_control.is_cancelled.side_effect = [False, True]
        mock_control.record_decision.return_value = True
        mock_control.reserve.return_value = True
        mock_control.release.return_value = True

        gw = Gateway(self.workspace, registry=self.registry, control=mock_control, mode="enforce")
        env = make_envelope()
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1"}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(fake_runner.call_count, 0)
        mock_control.release.assert_called()

    def test_deadline_expired_denies_invoke(self):
        """Deadline in past → EXPIRED, 0 calls."""
        from datetime import datetime, timedelta, timezone
        gw = Gateway(self.workspace, registry=self.registry, mode="enforce")
        now = datetime.now(timezone.utc)
        past_time = (now - timedelta(minutes=1)).replace(tzinfo=None).isoformat() + "Z"
        env = make_envelope(deadline=past_time)
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "supervisor", "run_id": "run-1", "now": now.replace(tzinfo=None)}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertEqual(result.status, "denied")
        self.assertEqual(result.decision.reason_code, "EXPIRED")
        self.assertEqual(fake_runner.call_count, 0)

    def test_deadline_valid_passes_timeout_to_runner(self):
        """Valid deadline → timeout calculated and passed to runner."""
        from datetime import datetime, timedelta, timezone
        gw = Gateway(self.workspace, registry=self.registry, mode="off")
        now = datetime.now(timezone.utc)
        future_time = (now + timedelta(seconds=30)).replace(tzinfo=None).isoformat() + "Z"
        env = make_envelope(deadline=future_time, budget={"max_seconds": 60})
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"now": now.replace(tzinfo=None)}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertEqual(result.status, "allowed")
        self.assertEqual(fake_runner.call_count, 1)
        self.assertIsNotNone(fake_runner.last_cmd)

    def test_sender_mismatch_denied(self):
        """context[authenticated_sender] != envelope.sender → SENDER_MISMATCH, 0 calls."""
        gw = Gateway(self.workspace, registry=self.registry, mode="enforce")
        env = make_envelope(sender="supervisor")
        route = Route("claude", "haiku", "cheap", "cli")
        context = {"authenticated_sender": "different_agent", "run_id": "run-1"}

        result = gw.dispatch(env, context=context, runner=fake_runner, route=route)

        self.assertEqual(result.status, "denied")
        self.assertEqual(result.decision.reason_code, "SENDER_MISMATCH")
        self.assertEqual(fake_runner.call_count, 0)


if __name__ == "__main__":
    unittest.main()
