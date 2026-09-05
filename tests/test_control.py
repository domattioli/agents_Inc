import unittest
import tempfile
import sqlite3
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from workerbees.control import Control, ReplayResult
from workerbees.envelope import Decision


class TestControlDecisions(unittest.TestCase):
    """Test decision recording and retrieval."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)
        self.control = Control(self.workspace)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_record_decision_stores_and_retrieves(self):
        """Test that decisions are durable and readable."""
        decision = Decision(
            allowed=True,
            decision_id="dec-001",
            reason_code="AUTHORIZED",
            reason="User is authorized",
            policy_version="v1.0",
            checked_rules=["rule_1", "rule_2"]
        )

        # Record decision
        result = self.control.record_decision(decision, "run-001", "node-001", "hash-abc")
        self.assertTrue(result)

        # Verify it's in the database
        conn = sqlite3.connect(str(self.control.db_path))
        cur = conn.cursor()
        cur.execute("SELECT * FROM decisions WHERE decision_id = ?", ("dec-001",))
        row = cur.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], "dec-001")  # decision_id
        self.assertEqual(row[4], 1)  # allowed (True -> 1)
        self.assertEqual(row[5], "AUTHORIZED")  # reason_code
        checked_rules = json.loads(row[7])
        self.assertEqual(checked_rules, ["rule_1", "rule_2"])

    def test_record_decision_denied(self):
        """Test recording a denied decision."""
        decision = Decision(
            allowed=False,
            decision_id="dec-002",
            reason_code="UNAUTHORIZED",
            reason="Insufficient permissions",
            policy_version="v1.0",
            checked_rules=["rule_3"]
        )

        result = self.control.record_decision(decision, "run-002", "node-002", "hash-def")
        self.assertTrue(result)

        conn = sqlite3.connect(str(self.control.db_path))
        cur = conn.cursor()
        cur.execute("SELECT allowed, reason_code FROM decisions WHERE decision_id = ?", ("dec-002",))
        row = cur.fetchone()
        conn.close()

        self.assertEqual(row[0], 0)  # allowed False -> 0
        self.assertEqual(row[1], "UNAUTHORIZED")


class TestControlReservations(unittest.TestCase):
    """Test budget reservations and release."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)
        self.control = Control(self.workspace)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_reserve_and_release(self):
        """Test reservation creation and release."""
        # Reserve budget
        result = self.control.reserve("run-001", "node-001", calls=5, seconds=10.0)
        self.assertTrue(result)

        # Check it's unreleased
        used = self.control.used("run-001")
        self.assertEqual(used["calls"], 5)
        self.assertEqual(used["seconds"], 10.0)

        # Release it
        result = self.control.release("run-001", "node-001")
        self.assertTrue(result)

        # Check it's no longer counted
        used = self.control.used("run-001")
        self.assertEqual(used["calls"], 0)
        self.assertEqual(used["seconds"], 0.0)

    def test_multiple_reservations_sum(self):
        """Test that multiple reservations sum correctly."""
        self.control.reserve("run-001", "node-001", calls=3, seconds=5.0)
        self.control.reserve("run-001", "node-002", calls=2, seconds=3.0)

        used = self.control.used("run-001")
        self.assertEqual(used["calls"], 5)
        self.assertEqual(used["seconds"], 8.0)

        # Release one
        self.control.release("run-001", "node-001")

        used = self.control.used("run-001")
        self.assertEqual(used["calls"], 2)
        self.assertEqual(used["seconds"], 3.0)

    def test_used_empty_run(self):
        """Test used() on run with no reservations."""
        used = self.control.used("run-nonexistent")
        self.assertEqual(used["calls"], 0)
        self.assertEqual(used["seconds"], 0.0)


class TestControlReplay(unittest.TestCase):
    """Test replay key deduplication and conflict detection."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)
        self.control = Control(self.workspace)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_replay_new_message(self):
        """Test detecting a new message."""
        result = self.control.check_replay("msg-001", "hash-abc123")
        self.assertEqual(result.state, "new")
        self.assertIsNone(result.artifact_ref)

    def test_replay_duplicate_message(self):
        """Test detecting a duplicate (same ID and hash)."""
        # Store first
        self.control.store_artifact("msg-001", "hash-abc123", "artifact-ref-1")

        # Check replay
        result = self.control.check_replay("msg-001", "hash-abc123")
        self.assertEqual(result.state, "duplicate")
        self.assertEqual(result.artifact_ref, "artifact-ref-1")

    def test_replay_conflict_message(self):
        """Test detecting a conflict (same ID, different hash)."""
        # Store first message
        self.control.store_artifact("msg-001", "hash-abc123", "artifact-ref-1")

        # Check with different hash
        result = self.control.check_replay("msg-001", "hash-different")
        self.assertEqual(result.state, "conflict")
        self.assertEqual(result.artifact_ref, "artifact-ref-1")


class TestControlCancellation(unittest.TestCase):
    """Test run cancellation tracking."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)
        self.control = Control(self.workspace)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_cancel_and_check(self):
        """Test marking and checking cancellation."""
        # Initially not cancelled
        self.assertFalse(self.control.is_cancelled("run-001"))

        # Cancel
        result = self.control.cancel("run-001")
        self.assertTrue(result)

        # Now it's cancelled
        self.assertTrue(self.control.is_cancelled("run-001"))


class TestControlLease(unittest.TestCase):
    """Test exclusive run lease acquisition and release."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)
        self.control = Control(self.workspace)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_acquire_lease_exclusive(self):
        """Test that second acquire fails until release."""
        # First acquire succeeds
        result = self.control.acquire_lease("run-001")
        self.assertTrue(result)

        # Second acquire with different run fails
        result = self.control.acquire_lease("run-002")
        self.assertFalse(result)

        # Same run can re-acquire
        result = self.control.acquire_lease("run-001")
        self.assertTrue(result)

    def test_release_lease(self):
        """Test lease release and subsequent acquire by different run."""
        # Acquire with run-001
        self.control.acquire_lease("run-001")

        # Release
        result = self.control.release_lease("run-001")
        self.assertTrue(result)

        # Now run-002 can acquire
        result = self.control.acquire_lease("run-002")
        self.assertTrue(result)


class TestControlErrorHandling(unittest.TestCase):
    """Test error handling when database is unavailable."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)
        self.control = Control(self.workspace)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_record_decision_readonly_db_returns_false(self):
        """Test that recording to read-only DB returns False, doesn't raise."""
        # Make DB directory read-only
        db_dir = self.control.db_path.parent
        db_dir.chmod(0o444)

        try:
            decision = Decision(
                allowed=True,
                decision_id="dec-003",
                reason_code="TEST",
                reason="test",
                policy_version="v1.0"
            )

            # Should return False, not raise
            result = self.control.record_decision(decision, "run-003", "node-003", "hash-xyz")
            self.assertFalse(result)
        finally:
            # Restore permissions for cleanup
            db_dir.chmod(0o755)


class TestApprovals(unittest.TestCase):
    """Test governance approvals API."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmpdir.name)
        self.control = Control(self.workspace)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_self_approval_rejected(self):
        """Test that requester cannot be the approver."""
        approval_id = self.control.request_approval(
            "run-001", "alice", "delete", "file.txt", "hash123", "high", ["rule1"], "2099-01-01T00:00:00Z"
        )
        self.assertIsNotNone(approval_id)
        result = self.control.decide_approval(approval_id, "alice", "approved", "2026-09-05T00:00:00Z")
        self.assertFalse(result)

    def test_expired_approval_rejected(self):
        """Test that expired approvals cannot be decided."""
        approval_id = self.control.request_approval(
            "run-001", "alice", "delete", "file.txt", "hash123", "high", ["rule1"], "2020-01-01T00:00:00Z"
        )
        self.assertIsNotNone(approval_id)
        result = self.control.decide_approval(approval_id, "bob", "approved", "2026-09-05T00:00:00Z")
        self.assertFalse(result)

    def test_approved_binds_exact_action(self):
        """Test that approved binding requires exact action match."""
        approval_id = self.control.request_approval(
            "run-001", "alice", "delete", "file.txt", "hash123", "high", ["rule1"], "2099-01-01T00:00:00Z"
        )
        self.control.decide_approval(approval_id, "bob", "approved", "2026-09-05T00:00:00Z")

        # Exact match binds
        self.assertTrue(self.control.approval_binds(approval_id, "delete", "file.txt", "hash123"))

        # Different action does not bind
        self.assertFalse(self.control.approval_binds(approval_id, "read", "file.txt", "hash123"))

    def test_changed_artifact_hash_binds_false(self):
        """Test that changed artifact_hash causes binding to fail."""
        approval_id = self.control.request_approval(
            "run-001", "alice", "delete", "file.txt", "hash123", "high", ["rule1"], "2099-01-01T00:00:00Z"
        )
        self.control.decide_approval(approval_id, "bob", "approved", "2026-09-05T00:00:00Z")

        # Different artifact_hash does not bind
        self.assertFalse(self.control.approval_binds(approval_id, "delete", "file.txt", "hash456"))

    def test_double_decide_rejected(self):
        """Test that approvals cannot be decided twice."""
        approval_id = self.control.request_approval(
            "run-001", "alice", "delete", "file.txt", "hash123", "high", ["rule1"], "2099-01-01T00:00:00Z"
        )
        result1 = self.control.decide_approval(approval_id, "bob", "approved", "2026-09-05T00:00:00Z")
        self.assertTrue(result1)

        # Second decide fails
        result2 = self.control.decide_approval(approval_id, "charlie", "denied", "2026-09-06T00:00:00Z")
        self.assertFalse(result2)


if __name__ == "__main__":
    unittest.main()
