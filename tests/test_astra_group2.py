"""Regression gates for Astra review 2 policy/gateway rows."""
import sqlite3, tempfile, unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.test_gateway import FakeRegistry, fake_runner, make_envelope
from workerbees.adapters.base import WorkerResult
from workerbees.control import Control
from workerbees.gateway import Gateway, GatewayResult
from workerbees.envelope import Decision
from workerbees.pipeline import _dispatch_worker
from workerbees.policy import evaluate
from workerbees.registry import Registry
from workerbees.router import Route


class AstraGroup2Test(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ws = Path(self.temp.name)
        (self.ws / ".workerbees").mkdir()
        self.registry = FakeRegistry()
        fake_runner.call_count = 0

    def tearDown(self):
        self.temp.cleanup()

    def dispatch(self, env=None, route=None, mode="enforce", runner=fake_runner, context=None):
        return Gateway(self.ws, self.registry, mode=mode).dispatch(
            env or make_envelope(), context=context or {"authenticated_sender": "supervisor", "run_id": "run"},
            runner=runner, route=route or Route("claude", "haiku", "cheap", "cli"))

    def registry_with(self, **changes):
        values = {name: getattr(self.registry, name) for name in
                  ("version", "policy_version", "snapshot_hash", "agents", "capabilities", "relationships")}
        values.update(changes)
        return Registry(**values)

    def test_02_sender_intent_and_capability_enforced(self):
        disabled = replace(self.registry.agents["supervisor"], enabled=False)
        reg = self.registry_with(agents={**self.registry.agents, "supervisor": disabled})
        self.assertEqual(evaluate({"authenticated_sender": "supervisor"}, make_envelope(), reg).reason_code, "SENDER_DISABLED")
        self.assertEqual(evaluate({"authenticated_sender": "supervisor"}, make_envelope(intent="deploy"), self.registry).reason_code, "CAPABILITY_NOT_ALLOWED")
        cap = replace(self.registry.capabilities["extract"], enabled=False)
        reg = self.registry_with(capabilities={**self.registry.capabilities, "extract": cap})
        self.assertEqual(evaluate({"authenticated_sender": "supervisor"}, make_envelope(), reg).reason_code, "CAPABILITY_DISABLED")

    def test_03_boolean_approval_cannot_forge_durable_approval(self):
        rel = replace(self.registry.relationships[0], requires_approval=True)
        self.registry = self.registry_with(relationships=[rel, *self.registry.relationships[1:]])
        env = make_envelope(security={"approved": True})
        self.assertEqual(self.dispatch(env).decision.reason_code, "APPROVAL_REQUIRED")

    def test_03_bound_unexpired_approval_allows(self):
        rel = replace(self.registry.relationships[0], requires_approval=True)
        self.registry = self.registry_with(relationships=[rel, *self.registry.relationships[1:]])
        control = Control(self.ws)
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        aid = control.request_approval("run", "requester", "extract", "doc", "abc", "risk", [], expiry)
        self.assertTrue(control.decide_approval(aid, "approver", "approved", datetime.now(timezone.utc).isoformat()))
        env = make_envelope(security={"approval_id": aid, "resource": "doc", "artifact_hash": "abc"})
        result = Gateway(self.ws, self.registry, control=control, mode="enforce").dispatch(env, context={"authenticated_sender":"supervisor","run_id":"run"}, runner=fake_runner, route=Route("claude","haiku","cheap","cli"))
        self.assertEqual(result.status, "allowed")

    def test_04_protocol_and_operation_schema_bound(self):
        self.assertEqual(self.dispatch(make_envelope(protocol="bogus")).status, "envelope_invalid")
        self.assertEqual(self.dispatch(make_envelope(schema="approval_v1")).status, "envelope_invalid")

    def test_05_final_denial_and_identity_are_audited(self):
        result = self.dispatch(route=Route("gemini", "gemini-pro", "cheap", "http"))
        with sqlite3.connect(self.ws / ".workerbees/control.sqlite") as c:
            row = c.execute("SELECT allowed,reason_code,sender,recipient,operation FROM decisions WHERE node_id=?", (result.node_id,)).fetchone()
        self.assertEqual(row, (0, "PROVIDER_NOT_EXECUTABLE", "supervisor", "worker", "request"))

    def test_05_invalid_envelope_is_audited(self):
        result = self.dispatch(make_envelope(protocol="bogus"))
        with sqlite3.connect(self.ws / ".workerbees/control.sqlite") as c:
            self.assertEqual(c.execute("SELECT reason_code FROM decisions WHERE node_id=?", (result.node_id,)).fetchone()[0], "ENVELOPE_INVALID")

    def test_06_zero_calls_and_token_caps_deny(self):
        self.assertEqual(self.dispatch(make_envelope(budget={"max_calls": 0})).decision.reason_code, "BUDGET_EXCEEDED")
        self.assertEqual(self.dispatch(make_envelope(message_id="m2", budget={"max_tokens": 1})).decision.reason_code, "TOKEN_BUDGET_UNSUPPORTED")

    def test_06_committed_usage_survives_gateway_recreation(self):
        self.assertEqual(self.dispatch().status, "allowed")
        result = self.dispatch(make_envelope(message_id="m2"), context={"authenticated_sender":"supervisor","run_id":"run"})
        self.assertEqual(result.status, "allowed")
        self.assertEqual(Control(self.ws).used("run")["calls"], 2)

    def test_07_gateway_clock_enforces_deadline_without_context_now(self):
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        result = self.dispatch(make_envelope(deadline=past))
        self.assertEqual((result.status, result.decision.reason_code, fake_runner.call_count), ("denied", "EXPIRED", 0))

    def test_08_empty_success_is_claimed_before_invoke(self):
        calls = []
        def empty(*args, **kwargs):
            calls.append(1); return WorkerResult("returned", "", "", 0)
        self.assertEqual(self.dispatch(runner=empty).status, "allowed")
        self.assertEqual(self.dispatch(runner=empty).status, "duplicate")
        self.assertEqual(len(calls), 1)

    def test_09_shadow_late_denial_never_returns_missing_worker_as_success(self):
        decision = Decision(False, "d", "PROVIDER_NOT_EXECUTABLE", "no", "1", [])
        class DenyingGateway:
            def dispatch(self, *args, **kwargs):
                return GatewayResult("denied", decision, None, "node", True)
        result = _dispatch_worker(self.ws, "run", Route("claude", "haiku", "cheap", "cli"),
            [], "prompt", fake_runner, "shadow", DenyingGateway(), self.registry, False,
            None, None, None)
        self.assertIsNone(result[0])
        self.assertEqual(result[4]["reason"], "PROVIDER_NOT_EXECUTABLE")

    def test_17_forged_tier_and_frontier_without_gate_denied(self):
        forged = self.dispatch(route=Route("claude", "fable", "cheap", "cli"))
        self.assertEqual(forged.decision.reason_code, "ROUTE_NOT_CATALOGED")
        frontier = self.dispatch(make_envelope(message_id="m2"), route=Route("claude", "fable", "frontier", "cli"))
        self.assertEqual(frontier.decision.reason_code, "FRONTIER_GATE_REQUIRED")


if __name__ == "__main__":
    unittest.main()
