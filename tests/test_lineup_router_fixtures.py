"""Fixture-expansion tests for lineup-mode routing (workerbees/lineup_router.py) -- test-only,
no production code. Covers three scenarios NOT exercised by tests/test_lineup_router.py,
per specs/009-cross-vendor-dispatch/routing-contract.md section 4/7.

Each scenario below is a FIXTURE that documents current, provisional behavior for an item
the spec explicitly flags as an OPEN QUESTION (section 7) -- none of these tests assert or
invent a resolution the spec says is unresolved.
"""
import unittest
from dataclasses import replace

from workerbees.router import Route
from workerbees.lineup_router import (
    RoutePlan,
    RunRecord,
    route_step,
)


class TestRun3MultiVendorPoolOpenQuestion(unittest.TestCase):
    """Spec section 4 Run 3 / section 7 open question #2: RoutePlan.target_vendor is
    singular but Run 3's pool is explicitly "Gemini + Mistral" -- two vendors at once.
    The spec does NOT say whether this is one multi-vendor RoutePlan, two merged
    RoutePlans, or a different shape -- and explicitly forbids inventing a
    RoutePlan.target_vendor schema change here (section 4 inline note).

    This fixture documents the ONLY shape that does not require inventing new schema:
    two separate, single-vendor RoutePlan instances, one per vendor, that a caller would
    have to merge itself. This is PROVISIONAL, not a resolution -- a future spec decision
    could pick a different shape entirely (e.g. an actual multi-vendor pool field).
    """

    def test_two_separate_route_plans_one_per_vendor_provisional(self):
        """Provisional-only: Run 3's "Gemini + Mistral" pool modeled as two RoutePlans,
        NOT a schema change to RoutePlan.target_vendor (which stays singular per spec section 1).
        """
        gemini_candidate = Route(provider="gemini", model="gemini-2.5-flash", tier="grunt", cmd_kind="http")
        mistral_candidate = Route(provider="mistral", model="mistral-small", tier="grunt", cmd_kind="http")
        authority = Route(provider="codex", model="gpt-5.4-mini", tier="grunt", cmd_kind="cli")

        gemini_plan = RoutePlan(
            run_id="example-run-3-gemini-leg",
            authority=authority,
            target_vendor="google",
            candidates=(gemini_candidate,),
            picked=gemini_candidate,
            mode="normal",
        )
        mistral_plan = RoutePlan(
            run_id="example-run-3-mistral-leg",
            authority=authority,
            target_vendor="mistral",
            candidates=(mistral_candidate,),
            picked=mistral_candidate,
            mode="normal",
        )

        self.assertEqual(gemini_plan.authority, mistral_plan.authority)
        self.assertIsInstance(gemini_plan.target_vendor, str)
        self.assertIsInstance(mistral_plan.target_vendor, str)
        self.assertNotEqual(gemini_plan.target_vendor, mistral_plan.target_vendor)
        merged_pool_for_caller_to_use = gemini_plan.candidates + mistral_plan.candidates
        self.assertEqual(len(merged_pool_for_caller_to_use), 2)


class TestRun3FourEventAuthorityReassignmentChain(unittest.TestCase):
    """Spec section 4 Run 3 events list: insufficient_capability (escalate, same authority)
    -> holder_cannot_continue (reassign to pre-approved backup) -> no_backup_left (stop).
    Exercised here as a 4-call route_step() chain: start -> escalate -> reassign -> stop.
    """

    def test_full_chain_escalate_then_reassign_then_stop_exhausted(self):
        small_authority = Route(provider="codex", model="gpt-5.4-mini", tier="grunt", cmd_kind="cli")
        backup_authority = Route(provider="claude", model="haiku", tier="grunt", cmd_kind="cli")
        worker_pool = (Route(provider="gemini", model="gemini-2.5-flash", tier="grunt", cmd_kind="http"),)
        escalation_pool = (Route(provider="gemini", model="gemini-2.5-pro", tier="workhorse", cmd_kind="http"),)

        run = RunRecord(
            run_id="example-run-3",
            task="code-write",
            accept_rule="passes hidden test suite",
            authority_holder=small_authority,
            authority_limits={},
            authority_movable=True,
            authority_move_rule="backup_list",
            policy_version="2026-09-05.1",
            allowed_models=("gpt-5.4-mini", "gemini-2.5-flash", "gemini-2.5-pro", "haiku"),
            hard_limits={"sandbox": True, "network": False, "tests": "hidden"},
            budget={"max_cost_usd": 1, "deadline_sec": 60},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 0, "fallback": "capability_escalation"},
            model_snapshot_ref="snap-001",
            pre_approved_larger_pool=escalation_pool,
            pre_approved_backup_list=(backup_authority,),
        )

        run = route_step(run, "start", worker_pool)
        self.assertEqual(run.authority_holder, small_authority)

        run = route_step(run, "insufficient_capability", escalation_pool)
        self.assertEqual(run.authority_holder, small_authority, "escalation must not move authority")
        self.assertIsNotNone(run.picked)

        run = route_step(run, "holder_cannot_continue", ())
        self.assertEqual(run.authority_holder, backup_authority)
        self.assertEqual(len(run.authority_change_events), 1)
        self.assertEqual(run.authority_change_events[0]["reason"], "holder_cannot_continue")

        exhausted_run = replace(run, pre_approved_backup_list=())
        stopped = route_step(exhausted_run, "holder_cannot_continue", ())
        self.assertEqual(stopped.authority_holder, backup_authority)
        self.assertEqual(stopped, exhausted_run, "stop() is a no-op passthrough per current code")


class TestRow2EmptyPoolTerminalCaseOpenQuestion(unittest.TestCase):
    """Spec section 3 Row 2 / section 7 open question #3: what happens if re-ranking the
    remaining eligible pool yields nothing after retries are exhausted? The RFC/spec does
    not specify this transition. This fixture documents CURRENT behavior (picked becomes
    None, no exception, no explicit stop() call) -- it does NOT invent a new policy or
    assert that this is the "correct" terminal behavior.
    """

    def test_failure_after_retries_exhausted_with_empty_remaining_pool(self):
        authority = Route(provider="claude", model="sonnet", tier="workhorse", cmd_kind="cli")
        only_candidate = Route(provider="codex", model="gpt-5.6-terra", tier="workhorse", cmd_kind="cli")
        pool = (only_candidate,)

        run = RunRecord(
            run_id="row2-empty-pool",
            task="classify",
            accept_rule="matches key",
            authority_holder=authority,
            authority_limits={},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet", "gpt-5.6-terra"),
            hard_limits={},
            budget={},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 0},
            model_snapshot_ref="snap-001",
            picked=only_candidate,
        )

        result = route_step(run, "failure", pool)

        self.assertIsNone(result.picked, "only candidate was already 'picked' so remove_failed empties the pool")
        self.assertEqual(result.authority_holder, authority, "authority unchanged even in this terminal case")


if __name__ == "__main__":
    unittest.main()
