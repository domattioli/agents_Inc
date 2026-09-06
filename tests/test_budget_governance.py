import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

from workerbees.adapters.base import WorkerResult
from workerbees.envelope import Envelope
from workerbees.gateway import Gateway
from workerbees.registry import Registry
from workerbees.router import Route


ROOT = Path(__file__).resolve().parent.parent


def envelope(message_id, budget):
    return Envelope(
        message_id=message_id, task_id=message_id, parent_task_id=None,
        correlation_id=message_id, sender="agent-supervisor-01",
        recipient="agent-worker-01", intent="extract", operation="request",
        protocol="v1", schema="request_v1", payload={"prompt": "x"},
        data_classification="public", created_at=datetime.now(timezone.utc).isoformat(),
        budget=budget)


class RunBudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry = Registry.load(str(ROOT / "workerbees"))
        self.route = Route("claude", "haiku", "cheap", "cli")

    def tearDown(self):
        self.tmp.cleanup()

    def test_budget_exhaustion_matrix_three_modes(self):
        observed = {}
        for mode in ("off", "shadow", "enforce"):
            runner = Mock(return_value=WorkerResult("returned", "{}", "", 0))
            gateway = Gateway(self.root / mode, registry=self.registry, mode=mode)
            result = gateway.dispatch(
                envelope(mode, {"max_calls": 0}),
                context={"authenticated_sender": "agent-supervisor-01", "run_id": "run"},
                runner=runner, route=self.route)
            observed[mode] = (result.status, result.decision.reason_code, runner.call_count)
        self.assertEqual(observed["off"], ("allowed", "ALLOWED", 1))
        self.assertEqual(observed["shadow"], ("allowed", "BUDGET_EXCEEDED", 1))
        self.assertEqual(observed["enforce"], ("denied", "BUDGET_EXCEEDED", 0))

    def test_run_budget_reaches_canonical_table(self):
        workspace = self.root / "stored"
        gateway = Gateway(workspace, registry=self.registry, mode="enforce")
        gateway.dispatch(
            envelope("stored", {"max_calls": 3, "max_seconds": 9.5}),
            context={"authenticated_sender": "agent-supervisor-01", "run_id": "budget-run"},
            runner=Mock(return_value=WorkerResult("returned", "{}", "", 0)), route=self.route)
        with sqlite3.connect(workspace / ".workerbees" / "workerbees.db") as conn:
            row = conn.execute("SELECT max_calls,max_seconds FROM run_budget WHERE run_id='budget-run'").fetchone()
        self.assertEqual(row, (3, 9.5))

    def test_first_run_budget_is_immutable(self):
        gateway = Gateway(self.root / "immutable", registry=self.registry, mode="enforce")
        first = gateway.control.record_run_budget("run", {"max_calls": 2})
        second = gateway.control.record_run_budget("run", {"max_calls": 99})
        self.assertEqual(first, second)
        self.assertEqual(second["max_calls"], 2)

    def test_observed_seconds_exhaust_run_budget(self):
        gateway = Gateway(self.root / "seconds", registry=self.registry, mode="enforce")
        def slow_runner(*args, **kwargs):
            time.sleep(0.01)
            return WorkerResult("returned", "{}", "", 0)
        first = gateway.dispatch(
            envelope("seconds-1", {"max_seconds": 0.001}),
            context={"authenticated_sender": "agent-supervisor-01", "run_id": "run"},
            runner=slow_runner, route=self.route)
        second = gateway.dispatch(
            envelope("seconds-2", {"max_seconds": 0.001}),
            context={"authenticated_sender": "agent-supervisor-01", "run_id": "run"},
            runner=slow_runner, route=self.route)
        self.assertEqual(first.status, "allowed")
        self.assertEqual((second.status, second.decision.reason_code), ("denied", "BUDGET_EXCEEDED"))


if __name__ == "__main__":
    unittest.main()


class ExplicitOffOverridesEnv(unittest.TestCase):
    """bench --t15 runs paired off/enforce with env=enforce; explicit off must not fall back to env."""

    def test_review_off_ignores_env_enforce(self):
        import os
        from unittest import mock
        from workerbees import reviewer
        from workerbees.router import Route
        calls = []
        def runner(cmd, prompt):
            from workerbees.adapters.base import WorkerResult
            calls.append(cmd); return WorkerResult("returned", "NO DEFECTS", "", 0)
        with mock.patch.dict(os.environ, {"WORKERBEES_GOVERNANCE": "enforce"}):
            rv = reviewer.review("src", "s", [], "draft", "claude", {"claude", "codex"}, True,
                                 runner=runner, route=Route("codex", "gpt-5.4-mini", "mid", "cli"),
                                 governance_mode="off")
        self.assertEqual(len(calls), 1)
        self.assertNotEqual(rv.status, "error")
