"""Unit tests for lineup_router.py — authority-driven cross-vendor dispatch."""
import unittest
from workerbees.router import Route
from workerbees.lineup_router import (
    RoutePlan,
    RunRecord,
    lineup_candidates,
    route_step,
    pick_model_or_lineup,
)


class TestRoutePlan(unittest.TestCase):
    """RoutePlan dataclass tests."""

    def test_route_plan_frozen(self):
        """RoutePlan is frozen."""
        plan = RoutePlan(
            run_id="test-1",
            authority=Route("claude", "sonnet", "workhorse", "cli"),
            target_vendor="openai",
            candidates=(),
            picked=None,
            mode="normal"
        )
        with self.assertRaises(AttributeError):
            plan.mode = "retry"

    def test_route_plan_basic_construction(self):
        """RoutePlan constructs with all fields."""
        authority = Route("claude", "sonnet", "workhorse", "cli")
        candidate = Route("codex", "gpt-5.6-terra", "workhorse", "cli")
        plan = RoutePlan(
            run_id="test-plan",
            authority=authority,
            target_vendor="openai",
            candidates=(candidate,),
            picked=candidate,
            mode="normal"
        )
        self.assertEqual(plan.run_id, "test-plan")
        self.assertEqual(plan.authority.model, "sonnet")
        self.assertEqual(plan.target_vendor, "openai")
        self.assertEqual(len(plan.candidates), 1)
        self.assertEqual(plan.picked.model, "gpt-5.6-terra")


class TestRunRecord(unittest.TestCase):
    """RunRecord dataclass tests."""

    def test_run_record_requires_nonempty_tie_break_order(self):
        """RunRecord construction rejects empty tie_break_order."""
        with self.assertRaises(ValueError) as ctx:
            RunRecord(
                run_id="test-1",
                task="classify",
                accept_rule="matches answer key",
                authority_holder=Route("claude", "sonnet", "workhorse", "cli"),
                authority_limits={},
                authority_movable=False,
                authority_move_rule=None,
                policy_version="2026-09-05.1",
                allowed_models=("sonnet", "haiku"),
                hard_limits={},
                budget={"max_cost_usd": 2},
                tie_break_order=(),  # INVALID
                retry_rule={"max_retries": 1},
                model_snapshot_ref="snap-001",
            )
        self.assertIn("tie_break_order", str(ctx.exception))

    def test_run_record_frozen(self):
        """RunRecord is frozen."""
        run = RunRecord(
            run_id="test-1",
            task="classify",
            accept_rule="matches answer key",
            authority_holder=Route("claude", "sonnet", "workhorse", "cli"),
            authority_limits={},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet", "haiku"),
            hard_limits={},
            budget={"max_cost_usd": 2},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 1},
            model_snapshot_ref="snap-001",
        )
        with self.assertRaises(AttributeError):
            run.task = "review"

    def test_run_record_valid_construction(self):
        """RunRecord constructs when tie_break_order is non-empty."""
        run = RunRecord(
            run_id="run-1",
            task="classify",
            accept_rule="matches answer key",
            authority_holder=Route("claude", "sonnet", "workhorse", "cli"),
            authority_limits={"max_cost_usd": 2},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet", "haiku", "gpt-5.6-terra"),
            hard_limits={"data": "public_only"},
            budget={"max_cost_usd": 2, "deadline_sec": 120},
            tie_break_order=("cost", "latency"),
            retry_rule={"max_retries": 1},
            model_snapshot_ref="snap-001",
        )
        self.assertEqual(run.run_id, "run-1")
        self.assertEqual(run.tie_break_order, ("cost", "latency"))


class TestLineupCandidates(unittest.TestCase):
    """lineup_candidates() function tests."""

    def test_lineup_candidates_openai_multiple_tiers(self):
        """lineup_candidates returns OpenAI models across multiple tiers for a task."""
        # OpenAI vendor models in catalog: gpt-5.4-mini (grunt), gpt-5.6-luna (grunt),
        # gpt-5.6-terra (workhorse), gpt-5.6-sol (orchestrator), gpt-6-astra (executive)
        policy_allowed = {"gpt-5.4-mini", "gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol", "gpt-6-astra"}
        candidates = lineup_candidates("openai", "classify", policy_allowed)

        self.assertGreater(len(candidates), 0, "Should find OpenAI models for classify task")
        # Check that we span multiple tiers (not just one pinned tier like old behavior)
        tiers = {c.tier for c in candidates}
        self.assertGreaterEqual(len(tiers), 2, f"Should span multiple tiers, got tiers: {tiers}")

        # All should have vendor openai (via their provider codex)
        for route in candidates:
            self.assertEqual(route.provider, "codex")

    def test_lineup_candidates_anthropic_all_tiers(self):
        """lineup_candidates returns Claude models across all tiers."""
        policy_allowed = {"haiku", "sonnet", "opus", "fable"}
        candidates = lineup_candidates("anthropic", "draft", policy_allowed)

        self.assertGreater(len(candidates), 0, "Should find anthropic models for draft task")
        tiers = {c.tier for c in candidates}
        self.assertGreaterEqual(len(tiers), 2, "Should span multiple tiers")

        # All should be claude provider
        for route in candidates:
            self.assertEqual(route.provider, "claude")

    def test_lineup_candidates_filters_bad_tasks(self):
        """lineup_candidates excludes models with task in tasks_bad."""
        # sonnet has "review-of-record" in tasks_bad
        policy_allowed = {"sonnet", "haiku", "opus"}
        candidates = lineup_candidates("anthropic", "review-of-record", policy_allowed)

        # Should not include sonnet or haiku (both have review-of-record in tasks_bad)
        model_names = {c.model for c in candidates}
        self.assertNotIn("sonnet", model_names)
        self.assertNotIn("haiku", model_names)
        # opus should be there (not in tasks_bad)
        self.assertIn("opus", model_names)

    def test_lineup_candidates_respects_policy_allowed(self):
        """lineup_candidates only returns models in policy_allowed_models."""
        policy_allowed = {"sonnet"}  # Only sonnet allowed
        candidates = lineup_candidates("anthropic", "draft", policy_allowed)

        for route in candidates:
            self.assertIn(route.model, policy_allowed)


class TestRouteStep(unittest.TestCase):
    """route_step() function tests — routing matrix rows."""

    def test_route_step_start_row_1(self):
        """route_step with 'start' event picks best from pool (Row 1)."""
        authority = Route("claude", "sonnet", "workhorse", "cli")
        pool = (
            Route("codex", "gpt-5.6-terra", "workhorse", "cli"),
            Route("codex", "gpt-6-astra", "executive", "cli"),
        )
        run = RunRecord(
            run_id="run-1",
            task="classify",
            accept_rule="matches key",
            authority_holder=authority,
            authority_limits={},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet", "gpt-5.6-terra", "gpt-6-astra"),
            hard_limits={},
            budget={},
            tie_break_order=("cost",),  # cost tie-break
            retry_rule={"max_retries": 1},
            model_snapshot_ref="snap-001",
        )

        result = route_step(run, "start", pool)

        # Authority should be unchanged (Row 1 invariant)
        self.assertEqual(result.authority_holder, authority)
        # Should have picked something
        self.assertIsNotNone(result.picked)
        # Should have recorded candidates_considered
        self.assertGreater(len(result.candidates_considered), 0)

    def test_route_step_failure_within_retries(self):
        """route_step with 'failure' within max_retries retries same model (Row 2, fixed retries)."""
        authority = Route("claude", "sonnet", "workhorse", "cli")
        pool = (
            Route("codex", "gpt-5.6-terra", "workhorse", "cli"),
            Route("codex", "gpt-6-astra", "executive", "cli"),
        )
        # Start state: picked one model
        run = RunRecord(
            run_id="run-1",
            task="classify",
            accept_rule="matches key",
            authority_holder=authority,
            authority_limits={},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet", "gpt-5.6-terra", "gpt-6-astra"),
            hard_limits={},
            budget={},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 2},  # Allow 2 retries
            model_snapshot_ref="snap-001",
            picked=pool[0],
            retries=(),  # 0 retries so far
        )

        result = route_step(run, "failure", pool)

        # Authority should be unchanged
        self.assertEqual(result.authority_holder, authority)
        # Should have recorded a retry
        self.assertEqual(len(result.retries), 1)
        # Picked should still be the same (fixed retry)
        self.assertEqual(result.picked, pool[0])

    def test_route_step_failure_exhausted_retries_reranks(self):
        """route_step with 'failure' after max_retries exhausted re-ranks remaining pool (Row 2)."""
        authority = Route("claude", "sonnet", "workhorse", "cli")
        pool = (
            Route("codex", "gpt-5.6-terra", "workhorse", "cli"),
            Route("codex", "gpt-6-astra", "executive", "cli"),
        )
        run = RunRecord(
            run_id="run-1",
            task="classify",
            accept_rule="matches key",
            authority_holder=authority,
            authority_limits={},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet", "gpt-5.6-terra", "gpt-6-astra"),
            hard_limits={},
            budget={},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 1},  # Allow 1 retry
            model_snapshot_ref="snap-001",
            picked=pool[0],
            retries=(
                {"attempt": 1, "route": {"provider": "codex", "model": "gpt-5.6-terra", "tier": "workhorse", "cmd_kind": "cli"}, "outcome": "failure"},
            ),  # 1 retry already used
        )

        result = route_step(run, "failure", pool)

        # Authority should be unchanged
        self.assertEqual(result.authority_holder, authority)
        # Should pick the next model (since first one failed)
        self.assertNotEqual(result.picked, pool[0])

    def test_route_step_insufficient_capability_escalation(self):
        """route_step with 'insufficient_capability' escalates to larger pool without changing authority (Row 3)."""
        authority = Route("claude", "sonnet", "workhorse", "cli")
        current_pool = (Route("codex", "gpt-5.6-terra", "workhorse", "cli"),)
        escalation_pool = (
            Route("codex", "gpt-6-astra", "executive", "cli"),
            Route("claude", "opus", "orchestrator", "cli"),
        )

        run = RunRecord(
            run_id="run-1",
            task="classify",
            accept_rule="matches key",
            authority_holder=authority,
            authority_limits={},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet", "gpt-5.6-terra", "gpt-6-astra", "opus"),
            hard_limits={},
            budget={},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 1},
            model_snapshot_ref="snap-001",
            picked=current_pool[0],
            pre_approved_larger_pool=escalation_pool,
        )

        result = route_step(run, "insufficient_capability", escalation_pool)

        # Authority should be UNCHANGED (Row 3 invariant)
        self.assertEqual(result.authority_holder, authority)
        # Should pick from escalation pool
        self.assertIsNotNone(result.picked)

    def test_route_step_holder_cannot_continue_reassigns_authority(self):
        """route_step with 'holder_cannot_continue' changes authority to first backup (Row 4)."""
        old_authority = Route("claude", "haiku", "grunt", "cli")
        backup_authority = Route("claude", "sonnet", "workhorse", "cli")

        run = RunRecord(
            run_id="run-1",
            task="classify",
            accept_rule="matches key",
            authority_holder=old_authority,
            authority_limits={},
            authority_movable=True,
            authority_move_rule="backup_list",
            policy_version="2026-09-05.1",
            allowed_models=("haiku", "sonnet", "opus"),
            hard_limits={},
            budget={},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 1},
            model_snapshot_ref="snap-001",
            pre_approved_backup_list=(backup_authority,),
        )

        result = route_step(run, "holder_cannot_continue", ())

        # Authority should CHANGE
        self.assertNotEqual(result.authority_holder, old_authority)
        self.assertEqual(result.authority_holder, backup_authority)
        # Should have recorded the authority change
        self.assertEqual(len(result.authority_change_events), 1)
        change_event = result.authority_change_events[0]
        self.assertEqual(change_event["reason"], "holder_cannot_continue")

    def test_route_step_authority_unchanged_across_start_then_failure(self):
        """Test Row 1 -> Row 2 invariant: authority unchanged."""
        authority = Route("claude", "sonnet", "workhorse", "cli")
        pool = (
            Route("codex", "gpt-5.6-terra", "workhorse", "cli"),
            Route("codex", "gpt-6-astra", "executive", "cli"),
        )

        # Row 1: start
        run1 = RunRecord(
            run_id="run-1",
            task="classify",
            accept_rule="matches key",
            authority_holder=authority,
            authority_limits={},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=("sonnet", "gpt-5.6-terra", "gpt-6-astra"),
            hard_limits={},
            budget={},
            tie_break_order=("cost",),
            retry_rule={"max_retries": 1},
            model_snapshot_ref="snap-001",
        )
        result1 = route_step(run1, "start", pool)
        authority_after_start = result1.authority_holder

        # Row 2: failure (within retries)
        result2 = route_step(result1, "failure", pool)
        authority_after_failure = result2.authority_holder

        # Authority should NOT change
        self.assertEqual(authority_after_start, authority_after_failure)


class TestPickModelOrLineup(unittest.TestCase):
    """pick_model_or_lineup() compatibility wrapper tests."""

    def test_pick_model_or_lineup_without_target_vendor_uses_old_path(self):
        """pick_model_or_lineup without lineup_target_vendor uses old pick_model path."""
        result = pick_model_or_lineup(
            "classify",
            "workhorse",
            {"claude", "codex"},
            workspace_authorized=False,
            lineup_target_vendor=None
        )

        # Should return a Route (from old pick_model), not a RoutePlan
        self.assertIsInstance(result, Route)

    def test_pick_model_or_lineup_with_target_vendor_returns_route_plan(self):
        """pick_model_or_lineup with lineup_target_vendor returns RoutePlan."""
        result = pick_model_or_lineup(
            "classify",
            "workhorse",
            {"claude", "codex"},
            workspace_authorized=False,
            lineup_target_vendor="openai"
        )

        # Should return a RoutePlan
        self.assertIsInstance(result, RoutePlan)
        self.assertEqual(result.target_vendor, "openai")
        # Should have found some candidates
        self.assertGreater(len(result.candidates), 0)


class TestRun1Input(unittest.TestCase):
    """Test case based on spec section 4 Run 1: classify task, Sonnet authority, OpenAI target."""

    def test_run1_sonnet_classifies_via_openai_lineup(self):
        """Run 1: Sonnet (anthropic) routes across OpenAI lineup for classify task."""
        sonnet_authority = Route("claude", "sonnet", "workhorse", "cli")
        policy_allowed = {
            "gpt-5.4-mini", "gpt-5.6-luna", "gpt-5.6-terra",
            "gpt-5.6-sol", "gpt-6-astra"
        }
        candidates = lineup_candidates("openai", "classify", policy_allowed)

        # Should have multiple tiers of OpenAI models
        self.assertGreater(len(candidates), 1)
        tiers = {c.tier for c in candidates}
        self.assertGreaterEqual(len(tiers), 2, "Should span multiple tiers (grunt, workhorse, orchestrator, executive)")

        # Create RunRecord with Sonnet as authority
        run = RunRecord(
            run_id="run-1",
            task="classify",
            accept_rule="matches labeled answer key",
            authority_holder=sonnet_authority,
            authority_limits={"max_cost_usd": 2},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=tuple(policy_allowed),
            hard_limits={"data": "public_only", "output": "structured"},
            budget={"max_cost_usd": 2, "deadline_sec": 120},
            tie_break_order=("cost", "latency"),
            retry_rule={"max_retries": 1, "fallback": "next_candidate"},
            model_snapshot_ref="snap-001",
        )

        # Start routing
        result = route_step(run, "start", candidates)

        # Sonnet (anthropic) should remain authority
        self.assertEqual(result.authority_holder, sonnet_authority)
        # Should have picked an OpenAI model
        self.assertIsNotNone(result.picked)
        self.assertEqual(result.picked.provider, "codex")


class TestRun2Input(unittest.TestCase):
    """Test case based on spec section 4 Run 2: review task, OpenAI authority, Anthropic target."""

    def test_run2_gpt_reviews_via_anthropic_lineup(self):
        """Run 2: GPT model (openai) routes across Claude lineup for review task."""
        # Use gpt-5.6-terra as a concrete OpenAI workhorse model
        gpt_authority = Route("codex", "gpt-5.6-terra", "workhorse", "cli")
        policy_allowed = {"haiku", "sonnet", "opus", "fable"}

        candidates = lineup_candidates("anthropic", "review", policy_allowed)

        # Should have multiple Claude models for review
        self.assertGreater(len(candidates), 0)

        # Create RunRecord with GPT as authority
        run = RunRecord(
            run_id="run-2",
            task="review",
            accept_rule="findings have evidence links to a checklist",
            authority_holder=gpt_authority,
            authority_limits={"max_cost_usd": 5},
            authority_movable=False,
            authority_move_rule=None,
            policy_version="2026-09-05.1",
            allowed_models=tuple(policy_allowed),
            hard_limits={"context_fit": "80k_tokens", "approved_for": "long_review", "tools": "none"},
            budget={"max_cost_usd": 5, "deadline_sec": 90},
            tie_break_order=("latency", "cost"),
            retry_rule={"max_retries": 1, "fallback": "next_candidate"},
            model_snapshot_ref="snap-001",
        )

        # Start routing
        result = route_step(run, "start", candidates)

        # GPT (openai/codex) should remain authority
        self.assertEqual(result.authority_holder, gpt_authority)
        # Should have picked a Claude model
        self.assertIsNotNone(result.picked)
        self.assertEqual(result.picked.provider, "claude")


class TestTieBreakOrder(unittest.TestCase):
    """Test tie-break ordering by cost and latency."""

    def test_rank_by_cost_then_latency(self):
        """Ranking respects tie_break_order: cost first, then latency."""
        from workerbees.lineup_router import rank

        pool = (
            Route("codex", "gpt-5.6-terra", "workhorse", "cli"),  # mid cost
            Route("codex", "gpt-6-astra", "executive", "cli"),     # premium cost
            Route("codex", "gpt-5.4-mini", "grunt", "cli"),        # cheap cost
        )

        ranked = rank(pool, ("cost", "latency"))

        # Cheapest should come first
        self.assertEqual(ranked[0].model, "gpt-5.4-mini")
        # Premium should come last
        self.assertEqual(ranked[-1].model, "gpt-6-astra")


if __name__ == "__main__":
    unittest.main()
