"""Tests for dispatch graph ledger module (TDD — tests first)."""
import json
import tempfile
import unittest
from pathlib import Path
from workerbees.ledger import (
    Node, Finding, Ledger,
    record_dispatch, record_return, load,
    lint, to_json, from_json, to_mermaid, rollup
)


class LedgerFoundationTest(unittest.TestCase):
    """Phase 2: Foundational ledger data model and I/O."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def test_node_creation_with_required_fields(self):
        """T004: Node creation has all required fields."""
        node = Node(
            id="n1",
            run_id="r1",
            model="haiku",
            tier="cheap",
            task="extract",
            provider="claude",
            parent_id=None,
            edge_type=None,
            status="dispatched",
            seconds=None,
            subscription_calls=None,
            gate_reason=None,
            timestamp="2026-09-05T12:00:00Z"
        )
        self.assertEqual(node.id, "n1")
        self.assertEqual(node.model, "haiku")
        self.assertEqual(node.tier, "cheap")
        self.assertEqual(node.status, "dispatched")
        self.assertIsNone(node.seconds)

    def test_idempotent_append_by_node_id(self):
        """T005: Same node written twice collapses to one on load."""
        # Write node twice with same id
        record_dispatch(self.ws, node_id="n1", run_id="r1", model="haiku", tier="cheap",
                       task="extract", provider="claude", parent_id=None, edge_type=None)
        record_dispatch(self.ws, node_id="n1", run_id="r1", model="haiku", tier="cheap",
                       task="extract", provider="claude", parent_id=None, edge_type=None)
        # Load and verify dedup
        ledger = load(self.ws)
        self.assertEqual(len(ledger.nodes), 1)
        self.assertIn("n1", ledger.nodes)

    def test_record_dispatch_creates_file(self):
        """T002: record_dispatch creates ledger file."""
        record_dispatch(self.ws, node_id="n1", run_id="r1", model="haiku", tier="cheap",
                       task="extract", provider="claude", parent_id=None, edge_type=None)
        ledger_file = self.ws / ".workerbees" / "ledger.jsonl"
        self.assertTrue(ledger_file.exists())

    def test_record_return_updates_node(self):
        """T002: record_return updates status/seconds/calls."""
        record_dispatch(self.ws, node_id="n1", run_id="r1", model="haiku", tier="cheap",
                       task="extract", provider="claude", parent_id=None, edge_type=None)
        record_return(self.ws, node_id="n1", status="returned", seconds=1.5, subscription_calls=1)
        ledger = load(self.ws)
        node = ledger.nodes.get("n1")
        self.assertIsNotNone(node)
        self.assertEqual(node.status, "returned")
        self.assertEqual(node.seconds, 1.5)
        self.assertEqual(node.subscription_calls, 1)

    def test_load_empty_workspace(self):
        """T003: load() on empty workspace returns empty Ledger + no warnings."""
        ledger = load(self.ws)
        self.assertEqual(len(ledger.nodes), 0)
        self.assertEqual(len(ledger.warnings), 0)

    def test_load_corrupt_file_returns_empty(self):
        """T003: Corrupt file returns empty Ledger + warning."""
        d = self.ws / ".workerbees"
        d.mkdir(parents=True, exist_ok=True)
        (d / "ledger.jsonl").write_text("not valid json\n")
        ledger = load(self.ws)
        self.assertEqual(len(ledger.nodes), 0)
        self.assertGreater(len(ledger.warnings), 0)

    def test_load_dedup_last_write_wins(self):
        """T003: Dedup keeps node with latest timestamp."""
        d = self.ws / ".workerbees"
        d.mkdir(parents=True, exist_ok=True)
        ledger_file = d / "ledger.jsonl"
        # Write two lines with same id, different timestamps/status
        line1 = json.dumps({
            "id": "n1", "run_id": "r1", "model": "haiku", "tier": "cheap",
            "task": "extract", "provider": "claude", "parent_id": None,
            "edge_type": None, "status": "dispatched", "seconds": None,
            "subscription_calls": None, "gate_reason": None,
            "timestamp": "2026-09-05T12:00:00Z"
        })
        line2 = json.dumps({
            "id": "n1", "run_id": "r1", "model": "haiku", "tier": "cheap",
            "task": "extract", "provider": "claude", "parent_id": None,
            "edge_type": None, "status": "returned", "seconds": 1.5,
            "subscription_calls": 1, "gate_reason": None,
            "timestamp": "2026-09-05T12:00:05Z"
        })
        ledger_file.write_text(f"{line1}\n{line2}\n")
        ledger = load(self.ws)
        node = ledger.nodes.get("n1")
        self.assertEqual(node.status, "returned")  # Later timestamp wins
        self.assertEqual(node.seconds, 1.5)


class LedgerUserStory1Test(unittest.TestCase):
    """Phase 3: User Story 1 — Audit who did what."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def test_worker_and_reviewer_create_2_nodes_with_reviews_edge(self):
        """T006: Worker + reviewer produces 2 nodes + 1 'reviews' edge."""
        # Record worker
        record_dispatch(self.ws, node_id="worker1", run_id="r1", model="haiku", tier="cheap",
                       task="extract", provider="claude", parent_id=None, edge_type=None)
        record_return(self.ws, node_id="worker1", status="returned", seconds=2.0, subscription_calls=1)
        # Record reviewer
        record_dispatch(self.ws, node_id="reviewer1", run_id="r1", model="gpt-5-mini", tier="cheap",
                       task="review", provider="codex", parent_id="worker1", edge_type="reviews")
        record_return(self.ws, node_id="reviewer1", status="returned", seconds=1.5, subscription_calls=1)

        ledger = load(self.ws)
        self.assertEqual(len(ledger.nodes), 2)

        reviewer_node = ledger.nodes.get("reviewer1")
        self.assertEqual(reviewer_node.parent_id, "worker1")
        self.assertEqual(reviewer_node.edge_type, "reviews")


class LedgerUserStory2Test(unittest.TestCase):
    """Phase 4: User Story 2 — Catch a bad hierarchy (lint rules)."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        self.ledger = Ledger(nodes={}, warnings=[])

    def test_lint_depth_rule(self):
        """T009: Depth > 1 triggers finding."""
        # Create 3-level hierarchy: grandparent -> parent -> child
        grandparent = Node("gp", "r1", "haiku", "cheap", "extract", "claude", None, None,
                          "returned", 1.0, 1, None, "2026-09-05T12:00:00Z")
        parent = Node("p", "r1", "haiku", "cheap", "extract", "claude", "gp", "reviews",
                     "returned", 1.0, 1, None, "2026-09-05T12:00:01Z")
        child = Node("c", "r1", "haiku", "cheap", "extract", "claude", "p", "reviews",
                    "returned", 1.0, 1, None, "2026-09-05T12:00:02Z")
        ledger = Ledger(nodes={"gp": grandparent, "p": parent, "c": child}, warnings=[])

        findings = lint(ledger)
        depth_findings = [f for f in findings if f.rule == "depth"]
        self.assertEqual(len(depth_findings), 1)
        self.assertIn("c", depth_findings[0].node_ids)

    def test_lint_same_vendor_review_rule(self):
        """T010: Same vendor review triggers finding."""
        worker = Node("w", "r1", "haiku", "cheap", "extract", "claude", None, None,
                     "returned", 1.0, 1, None, "2026-09-05T12:00:00Z")
        reviewer = Node("rv", "r1", "haiku", "cheap", "review", "claude", "w", "reviews",
                       "returned", 1.0, 1, None, "2026-09-05T12:00:01Z")
        ledger = Ledger(nodes={"w": worker, "rv": reviewer}, warnings=[])

        findings = lint(ledger)
        same_vendor_findings = [f for f in findings if f.rule == "same_vendor_review"]
        self.assertEqual(len(same_vendor_findings), 1)
        self.assertIn("w", same_vendor_findings[0].node_ids)
        self.assertIn("rv", same_vendor_findings[0].node_ids)

    def test_lint_frontier_without_gate_rule(self):
        """T011: Frontier tier without gate_reason triggers finding."""
        frontier_node = Node("f", "r1", "gpt-6-astra", "frontier", "extract", "codex", None, None,
                           "returned", 1.0, 1, None, "2026-09-05T12:00:00Z")
        ledger = Ledger(nodes={"f": frontier_node}, warnings=[])

        findings = lint(ledger)
        gate_findings = [f for f in findings if f.rule == "frontier_without_gate"]
        self.assertEqual(len(gate_findings), 1)
        self.assertIn("f", gate_findings[0].node_ids)

    def test_lint_frontier_with_gate_passes(self):
        """T011: Frontier tier WITH gate_reason passes."""
        frontier_node = Node("f", "r1", "gpt-6-astra", "frontier", "extract", "codex", None, None,
                           "returned", 1.0, 1, "user requested escalation", "2026-09-05T12:00:00Z")
        ledger = Ledger(nodes={"f": frontier_node}, warnings=[])

        findings = lint(ledger)
        gate_findings = [f for f in findings if f.rule == "frontier_without_gate"]
        self.assertEqual(len(gate_findings), 0)

    def test_lint_clean_ledger_no_findings(self):
        """Clean ledger produces zero findings."""
        worker = Node("w", "r1", "haiku", "cheap", "extract", "claude", None, None,
                     "returned", 1.0, 1, None, "2026-09-05T12:00:00Z")
        reviewer = Node("rv", "r1", "gpt-5-mini", "cheap", "review", "codex", "w", "reviews",
                       "returned", 1.0, 1, None, "2026-09-05T12:00:01Z")
        ledger = Ledger(nodes={"w": worker, "rv": reviewer}, warnings=[])

        findings = lint(ledger)
        self.assertEqual(len(findings), 0)


class LedgerUserStory3Test(unittest.TestCase):
    """Phase 5: User Story 3 — Export and analyze."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def test_json_export_round_trip(self):
        """T014: JSON export and round-trip preserves all fields."""
        node1 = Node("n1", "r1", "haiku", "cheap", "extract", "claude", None, None,
                    "returned", 2.0, 1, None, "2026-09-05T12:00:00Z")
        node2 = Node("n2", "r1", "gpt-5-mini", "cheap", "review", "codex", "n1", "reviews",
                    "returned", 1.5, 1, None, "2026-09-05T12:00:01Z")
        original_ledger = Ledger(nodes={"n1": node1, "n2": node2}, warnings=[])

        # Export
        json_str = to_json(original_ledger)
        # Round-trip
        restored_ledger = from_json(json_str)

        self.assertEqual(len(restored_ledger.nodes), 2)
        restored_n1 = restored_ledger.nodes.get("n1")
        self.assertEqual(restored_n1.model, "haiku")
        self.assertEqual(restored_n1.status, "returned")
        restored_n2 = restored_ledger.nodes.get("n2")
        self.assertEqual(restored_n2.edge_type, "reviews")

    def test_mermaid_export(self):
        """T016: Mermaid export has nodes and edges."""
        node1 = Node("n1", "r1", "haiku", "cheap", "extract", "claude", None, None,
                    "returned", 2.0, 1, None, "2026-09-05T12:00:00Z")
        node2 = Node("n2", "r1", "gpt-5-mini", "cheap", "review", "codex", "n1", "reviews",
                    "returned", 1.5, 1, None, "2026-09-05T12:00:01Z")
        ledger = Ledger(nodes={"n1": node1, "n2": node2}, warnings=[])

        mermaid_str = to_mermaid(ledger)
        self.assertIn("n1", mermaid_str)
        self.assertIn("n2", mermaid_str)
        self.assertIn("reviews", mermaid_str)

    def test_rollup_cost_per_root(self):
        """T017: Rollup computes per-root subtree sums."""
        # Root worker
        worker = Node("w", "r1", "haiku", "cheap", "extract", "claude", None, None,
                     "returned", 2.0, 2, None, "2026-09-05T12:00:00Z")
        # Reviewer child
        reviewer = Node("rv", "r1", "gpt-5-mini", "cheap", "review", "codex", "w", "reviews",
                       "returned", 1.5, 1, None, "2026-09-05T12:00:01Z")
        ledger = Ledger(nodes={"w": worker, "rv": reviewer}, warnings=[])

        rollup_data = rollup(ledger)
        self.assertIn("w", rollup_data)
        self.assertEqual(rollup_data["w"]["calls"], 3)  # 2 + 1
        self.assertEqual(rollup_data["w"]["seconds"], 3.5)  # 2.0 + 1.5


class LedgerEdgeCasesTest(unittest.TestCase):
    """Phase 7: Edge cases and robustness."""

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())

    def test_missing_ledger_file_returns_empty_ledger(self):
        """T025: Missing ledger file returns empty Ledger + no warning."""
        ledger = load(self.ws)
        self.assertEqual(len(ledger.nodes), 0)
        # Missing file is expected, not an error
        self.assertEqual(len(ledger.warnings), 0)

    def test_record_dispatch_never_raises(self):
        """FR-008: Ledger write failure never raises."""
        # Create a read-only directory to force permission error
        d = self.ws / ".workerbees"
        d.mkdir(parents=True, exist_ok=True)
        readonly = self.ws / ".workerbees_readonly"
        readonly.mkdir(parents=True, exist_ok=True)
        # record_dispatch should not raise even with permission issues
        try:
            record_dispatch(readonly, node_id="n1", run_id="r1", model="haiku", tier="cheap",
                           task="extract", provider="claude", parent_id=None, edge_type=None)
        except Exception as e:
            self.fail(f"record_dispatch raised {type(e).__name__}: {e}")

    def test_lint_true_depth_chain(self):
        """Test: lint flags nodes at depth > 1 (b and c), not a."""
        # Build chain: root -> a -> b -> c
        record_dispatch(self.ws, node_id="root", run_id="r1", model="haiku", tier="cheap",
                       task="extract", provider="claude", parent_id=None, edge_type=None)
        record_dispatch(self.ws, node_id="a", run_id="r1", model="haiku", tier="cheap",
                       task="extract", provider="claude", parent_id="root", edge_type="corrects")
        record_dispatch(self.ws, node_id="b", run_id="r1", model="haiku", tier="cheap",
                       task="extract", provider="claude", parent_id="a", edge_type="corrects")
        record_dispatch(self.ws, node_id="c", run_id="r1", model="haiku", tier="cheap",
                       task="extract", provider="claude", parent_id="b", edge_type="corrects")

        ledger = load(self.ws)
        findings = lint(ledger)
        depth_findings = [f for f in findings if f.rule == "depth"]

        # Should have 2 depth findings (for b and c, not root or a)
        self.assertEqual(len(depth_findings), 2)
        flagged_ids = set()
        for f in depth_findings:
            flagged_ids.update(f.node_ids)
        # b and c should be flagged, not root or a
        self.assertIn("b", flagged_ids)
        self.assertIn("c", flagged_ids)
        self.assertNotIn("root", flagged_ids)
        self.assertNotIn("a", flagged_ids)


if __name__ == "__main__":
    unittest.main()
