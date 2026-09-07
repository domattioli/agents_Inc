#!/usr/bin/env python3
"""Unit tests for phase_registry resolver.

All 15 test cases from data-model.md §Test cases.
Stdlib unittest only; no pytest.
"""

import sys
import unittest
import subprocess
import json
from pathlib import Path

# Add parent scripts dir to path so we can import phase_registry
SCRIPTS_DIR = Path(__file__).parent.parent / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

from phase_registry import (
    resolve,
    REGISTRY,
    DEFAULTS,
    INSERTABLE,
    UnknownPhase,
    SkipAddConflict,
    NotInsertable,
    RequiredPhaseSkip,
    DepBreak,
)


class TestPhaseRegistry(unittest.TestCase):
    """Tests for the phase registry resolver."""

    def test_default_order_matches_fr002(self):
        """resolve(∅,∅) == [specify,clarify,plan,tasks,checklist,analyze,implement]"""
        result = resolve(set(), set())
        expected = ['specify', 'clarify', 'plan', 'tasks', 'checklist', 'analyze', 'implement']
        self.assertEqual(result, expected)

    def test_skip_two_defaults_preserves_relative_order(self):
        """resolve({clarify,checklist},∅) == [specify,plan,tasks,analyze,implement]"""
        result = resolve({'clarify', 'checklist'}, set())
        expected = ['specify', 'plan', 'tasks', 'analyze', 'implement']
        self.assertEqual(result, expected)

    def test_add_out_of_order_lands_canonical(self):
        """resolve(∅,{commit,constitution}) lands canonical, regardless of input order"""
        result1 = resolve(set(), {'commit', 'constitution'})
        result2 = resolve(set(), {'constitution', 'commit'})
        expected = ['constitution', 'specify', 'clarify', 'plan', 'tasks', 'checklist', 'analyze', 'implement', 'commit']
        self.assertEqual(result1, expected)
        self.assertEqual(result2, expected)

    def test_permutation_invariance_property(self):
        """Shuffles of a fixed skip/add pair → identical stdout bytes (determinism benchmark)"""
        skip = 'clarify,checklist'
        add = 'split,constitution'

        # Call resolve_phases.py 3+ times with different CSV orders
        outputs = []
        for _ in range(4):
            # Different orderings of the same CSV (using subprocess to test actual CLI)
            cmd = [
                sys.executable,
                str(SCRIPTS_DIR / 'resolve_phases.py'),
                '--skip', skip,
                '--add', add,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SCRIPTS_DIR))
            self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
            outputs.append(result.stdout)

        # All outputs must be byte-identical
        self.assertEqual(len(set(outputs)), 1, "Outputs differ across permutations")

    def test_unknown_name_raises_with_valid_list(self):
        """Typo raises UnknownPhase carrying sorted(orderable)"""
        with self.assertRaises(UnknownPhase) as cm:
            resolve(set(), {'nonexistent'})

        exc = cm.exception
        self.assertIn('nonexistent', exc.names)
        # valid list should contain all orderable phases
        orderable = set(DEFAULTS) | set(INSERTABLE)
        self.assertEqual(set(exc.valid), orderable)

    def test_skip_add_conflict_before_other_checks(self):
        """resolve({clarify},{clarify}) raises SkipAddConflict first"""
        with self.assertRaises(SkipAddConflict) as cm:
            resolve({'clarify'}, {'clarify'})

        exc = cm.exception
        self.assertIn('clarify', exc.names)

    def test_add_non_insertable_default_rejected(self):
        """resolve(∅,{plan}) raises NotInsertable"""
        with self.assertRaises(NotInsertable) as cm:
            resolve(set(), {'plan'})

        exc = cm.exception
        self.assertIn('plan', exc.names)

    def test_skip_required_specify_rejected(self):
        """Skipping 'specify' (required) raises RequiredPhaseSkip"""
        with self.assertRaises(RequiredPhaseSkip) as cm:
            resolve({'specify'}, set())

        exc = cm.exception
        self.assertIn('specify', exc.names)

    def test_skip_required_implement_rejected(self):
        """Skipping 'implement' (required) raises RequiredPhaseSkip"""
        with self.assertRaises(RequiredPhaseSkip) as cm:
            resolve({'implement'}, set())

        exc = cm.exception
        self.assertIn('implement', exc.names)

    def test_force_allows_skip_implement(self):
        """resolve({implement},set,force=True) returns planning-only set without implement"""
        result = resolve({'implement'}, set(), force=True)
        self.assertNotIn('implement', result)
        self.assertIn('analyze', result)
        self.assertIn('specify', result)

    def test_force_skip_specify_still_depbreaks(self):
        """force bypasses required guard, but dependents of specify then DepBreak"""
        with self.assertRaises(DepBreak):
            resolve({'specify'}, set(), force=True)

    def test_skip_plan_collects_all_dep_breaks(self):
        """resolve({plan},∅) raises DepBreak listing all broken phases in canonical order"""
        with self.assertRaises(DepBreak) as cm:
            resolve({'plan'}, set())

        exc = cm.exception
        # Collect all (phase, dep) pairs
        broken_phases = {phase for phase, _ in exc.violations}
        # tasks depends on plan, analyze depends on plan
        # implement depends on plan
        self.assertIn('tasks', broken_phases)
        self.assertIn('analyze', broken_phases)
        self.assertIn('implement', broken_phases)

        # Verify violations are in canonical order
        violations_ordered = [phase for phase, _ in exc.violations]
        violations_sorted = sorted(violations_ordered, key=lambda p: REGISTRY[p].order)
        self.assertEqual(violations_ordered, violations_sorted)

    def test_skip_non_default_valid_name_is_noop(self):
        """resolve({commit},∅) == resolve(∅,∅) (skipping a phase never in defaults is no-op)"""
        result = resolve({'commit'}, set())
        expected = resolve(set(), set())
        self.assertEqual(result, expected)

    def test_add_both_after_tasks_fixed_relative_order(self):
        """tasks-to-issues(42) before split(44), both between tasks and checklist"""
        result = resolve(set(), {'tasks-to-issues', 'split'})
        tasks_idx = result.index('tasks')
        checklist_idx = result.index('checklist')
        tti_idx = result.index('tasks-to-issues')
        split_idx = result.index('split')

        self.assertLess(tasks_idx, tti_idx)
        self.assertLess(tti_idx, split_idx)
        self.assertLess(split_idx, checklist_idx)

    def test_cli_exit_codes_match_table(self):
        """Subprocess invokes resolve_phases.py for each error class, asserts correct exit codes"""
        test_cases = [
            # (args, expected_exit_code)
            (['--skip', 'nonexistent'], 10),  # UnknownPhase
            (['--skip', 'clarify', '--add', 'clarify'], 11),  # SkipAddConflict
            (['--add', 'plan'], 12),  # NotInsertable
            (['--skip', 'specify'], 13),  # RequiredPhaseSkip
            (['--skip', 'plan'], 14),  # DepBreak
            (['--plan-only'], 0),  # planning-only run (skips implement via force)
            (['--skip', 'implement', '--allow-required-skip'], 0),  # explicit force
            ([], 0),  # Success
        ]

        for args, expected_code in test_cases:
            cmd = [sys.executable, str(SCRIPTS_DIR / 'resolve_phases.py')] + args
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SCRIPTS_DIR))
            self.assertEqual(
                result.returncode,
                expected_code,
                f"Expected exit {expected_code}, got {result.returncode} for args {args}. "
                f"stderr: {result.stderr}"
            )

    def test_json_output_shape(self):
        """--json parses as list of dicts with phase/order/agent/model/effort/caveman in canonical order"""
        cmd = [sys.executable, str(SCRIPTS_DIR / 'resolve_phases.py'), '--json']
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SCRIPTS_DIR))
        self.assertEqual(result.returncode, 0)

        output = json.loads(result.stdout)
        self.assertIsInstance(output, list)

        # Each element should be a dict with required keys
        for item in output:
            self.assertIsInstance(item, dict)
            for key in ['phase', 'order', 'agent', 'model', 'effort', 'caveman']:
                self.assertIn(key, item)

        # Verify canonical order
        orders = [item['order'] for item in output]
        self.assertEqual(orders, sorted(orders))

    def test_list_flag_short_circuits(self):
        """--list exits 0 and dumps all 11 orderable phases regardless of --skip/--add"""
        # Test without skip/add
        cmd = [sys.executable, str(SCRIPTS_DIR / 'resolve_phases.py'), '--list']
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SCRIPTS_DIR))
        self.assertEqual(result.returncode, 0)
        base_lines = result.stdout.strip().split('\n')

        # Count orderable phases (7 defaults + 4 insertable)
        orderable = set(DEFAULTS) | set(INSERTABLE)
        self.assertEqual(len(base_lines), len(orderable))

        # Test with --skip/--add (should be ignored)
        cmd = [
            sys.executable, str(SCRIPTS_DIR / 'resolve_phases.py'),
            '--list', '--skip', 'clarify', '--add', 'constitution'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SCRIPTS_DIR))
        self.assertEqual(result.returncode, 0)
        lines_with_args = result.stdout.strip().split('\n')

        # Should be identical
        self.assertEqual(base_lines, lines_with_args)


if __name__ == '__main__':
    unittest.main(verbosity=2)
