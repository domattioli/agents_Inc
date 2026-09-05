"""Tests for governance_demo.py"""
import unittest
import sys
import subprocess
from pathlib import Path

# Add tools directory to path
TOOLS_DIR = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from governance_demo import run_demo


class TestGovernanceDemo(unittest.TestCase):
    """Test governance demo with fake runner."""

    def test_governance_demo_with_fake_runner(self):
        """Run governance demo with --fake flag; assert outcomes."""
        results, decisions_count, ledger_nodes = run_demo(use_fake=True)

        # Assert 2 decisions recorded
        self.assertEqual(decisions_count, 2, "Expected 2 decisions recorded")

        # Assert 1 allowed, 1 denied
        self.assertTrue(results["allowed"]["allowed"], "Case A should be allowed")
        self.assertFalse(results["denied"]["allowed"], "Case B should be denied")

        # Assert 1 ledger node (only allowed case records dispatch/return)
        self.assertEqual(ledger_nodes, 1, "Expected 1 ledger node (only allowed dispatch)")

        # Assert denial has 0 runner calls (no worker_result)
        self.assertEqual(results["denied"]["status"], "denied")


if __name__ == "__main__":
    unittest.main()
