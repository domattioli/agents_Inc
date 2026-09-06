import sqlite3
import unittest
from datetime import datetime, timezone
from workerbees.store import Store
from workerbees import schema


class TestStoreBasics(unittest.TestCase):
    """Test suite for workerbees.store.Store."""

    def setUp(self) -> None:
        """Create fresh in-memory DB and Store."""
        self.conn = sqlite3.connect(':memory:')
        self.store = Store(self.conn)

    def tearDown(self) -> None:
        """Close store."""
        self.store.close()

    def test_store_init_with_connection(self) -> None:
        """Store init via sqlite3.Connection works."""
        self.assertIsNotNone(self.store.conn)
        # Verify foreign_keys pragma is on
        result = self.store.conn.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(result, 1)

    def test_store_init_with_path(self, tmp_path=None) -> None:
        """Store init via file path works."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test.db"
            with Store(db_path) as s:
                result = s.conn.execute("PRAGMA foreign_keys").fetchone()[0]
                self.assertEqual(result, 1)

    def test_ensure_vendor_idempotent(self) -> None:
        """ensure_vendor is idempotent."""
        v1 = self.store.ensure_vendor("openai")
        v2 = self.store.ensure_vendor("openai")
        self.assertEqual(v1, v2)
        # Verify only one row in vendor table
        count = self.store.conn.execute("SELECT COUNT(*) FROM vendor").fetchone()[0]
        self.assertEqual(count, 1)

    def test_ensure_provider_idempotent(self) -> None:
        """ensure_provider is idempotent."""
        p1 = self.store.ensure_provider("openrouter")
        p2 = self.store.ensure_provider("openrouter")
        self.assertEqual(p1, p2)
        count = self.store.conn.execute("SELECT COUNT(*) FROM provider").fetchone()[0]
        self.assertEqual(count, 1)

    def test_ensure_model_idempotent(self) -> None:
        """ensure_model is idempotent."""
        self.store.ensure_vendor("openai")
        m1 = self.store.ensure_model("gpt-4", vendor_id="openai", model_name="gpt-4")
        m2 = self.store.ensure_model("gpt-4", vendor_id="openai", model_name="gpt-4")
        self.assertEqual(m1, m2)
        count = self.store.conn.execute("SELECT COUNT(*) FROM model").fetchone()[0]
        self.assertEqual(count, 1)

    def test_ensure_artifact_idempotent(self) -> None:
        """ensure_artifact is idempotent."""
        a1 = self.store.ensure_artifact("abc123", 1024)
        a2 = self.store.ensure_artifact("abc123", 1024)
        self.assertEqual(a1, a2)
        count = self.store.conn.execute("SELECT COUNT(*) FROM artifact").fetchone()[0]
        self.assertEqual(count, 1)


class TestStoreRouteFreeze(unittest.TestCase):
    """Test route alias freeze semantics (3NF snapshot)."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.store = Store(self.conn)
        self.store.ensure_provider("openrouter")
        self.store.ensure_vendor("anthropic")
        self.store.ensure_model("haiku", vendor_id="anthropic", model_name="haiku")
        self.store.ensure_model("sonnet", vendor_id="anthropic", model_name="sonnet")

    def tearDown(self) -> None:
        self.store.close()

    def test_route_same_model_returns_same_id(self) -> None:
        """ensure_route with same (provider,route_name,model) returns same route_id."""
        r1 = self.store.ensure_route("openrouter", "cheap-claude", "haiku")
        r2 = self.store.ensure_route("openrouter", "cheap-claude", "haiku")
        self.assertEqual(r1, r2)

    def test_route_different_model_returns_new_id(self) -> None:
        """ensure_route with same (provider,route_name) but different model returns new route_id."""
        r1 = self.store.ensure_route("openrouter", "cheap-claude", "haiku")
        r2 = self.store.ensure_route("openrouter", "cheap-claude", "sonnet")
        self.assertNotEqual(r1, r2)

    def test_route_old_binding_unchanged(self) -> None:
        """After route change, old route row still resolves to original model (3NF snapshot)."""
        r1 = self.store.ensure_route("openrouter", "cheap-claude", "haiku")
        r2 = self.store.ensure_route("openrouter", "cheap-claude", "sonnet")

        # Query old route: must still resolve to haiku
        row1 = self.store.conn.execute(
            "SELECT model_id FROM route WHERE route_id=?", (r1,)
        ).fetchone()
        self.assertEqual(row1[0], "haiku")

        # Query new route: must resolve to sonnet
        row2 = self.store.conn.execute(
            "SELECT model_id FROM route WHERE route_id=?", (r2,)
        ).fetchone()
        self.assertEqual(row2[0], "sonnet")

    def test_route_revision_increments_on_change(self) -> None:
        """Route revision increments when model changes."""
        r1 = self.store.ensure_route("openrouter", "cheap-claude", "haiku")
        r2 = self.store.ensure_route("openrouter", "cheap-claude", "sonnet")

        rev1 = self.store.conn.execute(
            "SELECT revision FROM route WHERE route_id=?", (r1,)
        ).fetchone()[0]
        rev2 = self.store.conn.execute(
            "SELECT revision FROM route WHERE route_id=?", (r2,)
        ).fetchone()[0]

        self.assertEqual(rev1, 0)
        self.assertEqual(rev2, 1)


class TestStoreForeignKeyEnforcement(unittest.TestCase):
    """Test FK constraint enforcement."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.store = Store(self.conn)

    def tearDown(self) -> None:
        self.store.close()

    def test_insert_node_missing_request_fk_raises(self) -> None:
        """Inserting node with non-existent request_id raises IntegrityError."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.insert_node("orphan-node", route_id=None, created_at="2026-01-01T00:00:00Z")

    def test_insert_decision_missing_request_fk_raises(self) -> None:
        """Inserting decision with non-existent request_id raises IntegrityError."""
        self.store.ensure_decision_code("test_code", allowed=1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.insert_decision(
                "dec1", request_id="missing_request", reason_code="test_code",
                created_at="2026-01-01T00:00:00Z"
            )


class TestStoreFactTableUniquenessDuplicate(unittest.TestCase):
    """Test A: FD/uniqueness — fact tables raise on duplicate PKs."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.store = Store(self.conn)
        self._setup_fixtures()

    def _setup_fixtures(self) -> None:
        """Pre-populate DB with minimal valid data."""
        # Run
        self.run_id = "run1"
        self.store.insert_run(self.run_id, "2026-01-01T00:00:00Z")

        # Family
        self.family_id = "fam1"
        self.store.insert_family(self.family_id, self.run_id)

        # Request (node_id IS request_id per schema)
        self.request_id = "req1"
        self.node_id = self.request_id  # node.node_id references request.request_id
        self.store.insert_request(self.request_id, self.family_id)

        # Node
        self.store.insert_node(self.node_id, created_at="2026-01-01T00:00:00Z")

        # Provider, Model, Route
        self.store.ensure_provider("provider1")
        self.store.ensure_model("model1")
        self.route_id = self.store.ensure_route("provider1", "route1", "model1")

    def tearDown(self) -> None:
        self.store.close()

    def test_duplicate_run_raises(self) -> None:
        """Duplicate run PK raises IntegrityError."""
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.insert_run(self.run_id, "2026-01-01T00:00:00Z")

    def test_duplicate_node_event_raises(self) -> None:
        """Duplicate node_event PK raises IntegrityError."""
        event_id = self.store.append_event(self.node_id, "dispatched", "2026-01-01T00:00:00Z")
        # Try to insert with same event_id (directly, not via append_event)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.conn.execute(
                "INSERT INTO node_event(event_id,node_id,event_seq,status,occurred_at) "
                "VALUES (?,?,?,?,?)",
                (event_id, self.node_id, 99, "returned", "2026-01-01T00:00:00Z")
            )

    def test_duplicate_decision_raises(self) -> None:
        """Duplicate decision PK raises IntegrityError."""
        self.store.ensure_decision_code("test_code", 1)
        self.store.insert_decision(
            "dec1", self.request_id, "test_code", created_at="2026-01-01T00:00:00Z"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.insert_decision(
                "dec1", self.request_id, "test_code", created_at="2026-01-01T00:00:00Z"
            )

    def test_duplicate_usage_raises(self) -> None:
        """Duplicate usage PK raises IntegrityError."""
        # Create an event
        event_id = self.store.append_event(self.node_id, "returned", "2026-01-01T00:00:00Z",
                                           usage={"seconds": 1.5})
        # Try to insert another usage with same event_id
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.conn.execute(
                "INSERT INTO usage(event_id,seconds) VALUES (?,?)",
                (event_id, 2.5)
            )

    def test_duplicate_frontier_gate_raises(self) -> None:
        """Duplicate frontier_gate PK raises IntegrityError."""
        self.store.insert_frontier_gate(self.node_id, "reached_frontier")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.insert_frontier_gate(self.node_id, "another_reason")

    def test_duplicate_lineage_raises(self) -> None:
        """Duplicate lineage PK raises IntegrityError."""
        # Create a second request/node as parent
        parent_req_id = "parent_req"
        parent_node_id = parent_req_id
        self.store.insert_request(parent_req_id, self.family_id)
        self.store.insert_node(parent_node_id, created_at="2026-01-01T00:00:00Z")

        self.store.insert_lineage(self.node_id, parent_node_id)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.insert_lineage(self.node_id, parent_node_id)


class TestStoreNoStoredDerivedColumns(unittest.TestCase):
    """Test B: NO derived columns stored (3NF repairs)."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.store = Store(self.conn)

    def tearDown(self) -> None:
        self.store.close()

    def _get_columns(self, table_name: str) -> list[str]:
        """Get all column names from table."""
        cursor = self.conn.execute(f"PRAGMA table_info({table_name})")
        return [row[1] for row in cursor.fetchall()]

    def test_node_no_vendor_column(self) -> None:
        """node table must NOT have a vendor column (3NF repair)."""
        cols = self._get_columns("node")
        self.assertNotIn("vendor", cols, "node must not have vendor column")

    def test_node_no_run_id_column(self) -> None:
        """node table must NOT have run_id column (3NF repair)."""
        cols = self._get_columns("node")
        self.assertNotIn("run_id", cols, "node must not have run_id column")

    def test_reservation_no_family_id_column(self) -> None:
        """reservation table must NOT have family_id column (3NF repair)."""
        cols = self._get_columns("reservation")
        self.assertNotIn("family_id", cols, "reservation must not have family_id column")

    def test_reservation_no_run_id_column(self) -> None:
        """reservation table must NOT have run_id column (3NF repair)."""
        cols = self._get_columns("reservation")
        self.assertNotIn("run_id", cols, "reservation must not have run_id column")

    def test_decision_no_run_id_column(self) -> None:
        """decision table must NOT have run_id column (3NF repair)."""
        cols = self._get_columns("decision")
        self.assertNotIn("run_id", cols, "decision must not have run_id column")

    def test_decision_no_node_id_column(self) -> None:
        """decision table must NOT have node_id column (3NF repair)."""
        cols = self._get_columns("decision")
        self.assertNotIn("node_id", cols, "decision must not have node_id column")


class TestStoreAppendEvent(unittest.TestCase):
    """Test E: append_event allocates 0,1,2...; duplicate seq raises."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.store = Store(self.conn)
        self.run_id = "run1"
        self.store.insert_run(self.run_id, "2026-01-01T00:00:00Z")
        self.family_id = "fam1"
        self.store.insert_family(self.family_id, self.run_id)
        self.request_id = "req1"
        self.node_id = self.request_id  # node.node_id IS request.request_id
        self.store.insert_request(self.request_id, self.family_id)
        self.store.insert_node(self.node_id, created_at="2026-01-01T00:00:00Z")

    def tearDown(self) -> None:
        self.store.close()

    def test_append_event_allocates_seq_0(self) -> None:
        """First append_event for node allocates seq=0."""
        self.store.append_event(self.node_id, "dispatched", "2026-01-01T00:00:00Z")
        row = self.store.conn.execute(
            "SELECT event_seq FROM node_event WHERE node_id=?",
            (self.node_id,)
        ).fetchone()
        self.assertEqual(row[0], 0)

    def test_append_event_allocates_seq_1_2_3(self) -> None:
        """Multiple append_event calls allocate 0,1,2,..."""
        self.store.append_event(self.node_id, "dispatched", "2026-01-01T00:00:00Z")
        self.store.append_event(self.node_id, "in_progress", "2026-01-01T00:00:01Z")
        self.store.append_event(self.node_id, "returned", "2026-01-01T00:00:02Z")

        rows = self.store.conn.execute(
            "SELECT event_seq FROM node_event WHERE node_id=? ORDER BY event_seq",
            (self.node_id,)
        ).fetchall()
        seqs = [row[0] for row in rows]
        self.assertEqual(seqs, [0, 1, 2])

    def test_append_event_duplicate_seq_raises(self) -> None:
        """Inserting event with duplicate (node_id,event_seq) raises IntegrityError."""
        # Use append_event which auto-allocates
        self.store.append_event(self.node_id, "dispatched", "2026-01-01T00:00:00Z")

        # Try to manually insert with same seq
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.conn.execute(
                "INSERT INTO node_event(node_id,event_seq,status,occurred_at) "
                "VALUES (?,?,?,?)",
                (self.node_id, 0, "duplicate_status", "2026-01-01T00:00:00Z")
            )


class TestStoreUsageViewAccess(unittest.TestCase):
    """Test F: usage row from append_event reachable via node_usage view."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.store = Store(self.conn)
        self.run_id = "run1"
        self.store.insert_run(self.run_id, "2026-01-01T00:00:00Z")
        self.family_id = "fam1"
        self.store.insert_family(self.family_id, self.run_id)
        self.request_id = "req1"
        self.node_id = self.request_id  # node.node_id IS request.request_id
        self.store.insert_request(self.request_id, self.family_id)
        self.store.insert_node(self.node_id, created_at="2026-01-01T00:00:00Z")

    def tearDown(self) -> None:
        self.store.close()

    def test_usage_from_append_event_in_node_usage_view(self) -> None:
        """Usage row written via append_event is reachable via node_usage view."""
        usage_data = {
            "seconds": 1.5,
            "subscription_calls": 10,
            "input_tokens": 100,
            "output_tokens": 200,
            "reasoning_tokens": 50,
            "cost_micro_usd": 500
        }
        self.store.append_event(self.node_id, "returned", "2026-01-01T00:00:00Z",
                                usage=usage_data)

        # Query via node_usage view
        row = self.store.conn.execute(
            "SELECT seconds,subscription_calls,input_tokens,output_tokens,"
            "reasoning_tokens,cost_micro_usd FROM node_usage WHERE node_id=?",
            (self.node_id,)
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1.5)  # seconds
        self.assertEqual(row[1], 10)   # subscription_calls
        self.assertEqual(row[2], 100)  # input_tokens
        self.assertEqual(row[3], 200)  # output_tokens
        self.assertEqual(row[4], 50)   # reasoning_tokens
        self.assertEqual(row[5], 500)  # cost_micro_usd

    def test_usage_null_fields_skipped(self) -> None:
        """Usage with only partial fields sets others to NULL."""
        usage_data = {"seconds": 2.0, "cost_micro_usd": 100}
        self.store.append_event(self.node_id, "returned", "2026-01-01T00:00:00Z",
                                usage=usage_data)

        row = self.store.conn.execute(
            "SELECT seconds,subscription_calls,cost_micro_usd FROM node_usage WHERE node_id=?",
            (self.node_id,)
        ).fetchone()

        self.assertEqual(row[0], 2.0)
        self.assertIsNone(row[1])  # subscription_calls not provided
        self.assertEqual(row[2], 100)


class TestStoreComplexScenarios(unittest.TestCase):
    """Integration tests combining multiple constraints."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.store = Store(self.conn)

    def tearDown(self) -> None:
        self.store.close()

    def test_full_dispatch_scenario(self) -> None:
        """Full dispatch flow: run→family→request→node→events."""
        # Setup
        run_id = "run1"
        self.store.insert_run(run_id, "2026-01-01T00:00:00Z", outcome="accepted")

        fam_id = "fam1"
        self.store.insert_family(fam_id, run_id, label="test_family")

        req_id = "req1"
        node_id = req_id  # node.node_id IS request.request_id
        self.store.insert_request(req_id, fam_id)

        self.store.ensure_provider("provider1")
        self.store.ensure_model("model1")
        route_id = self.store.ensure_route("provider1", "route1", "model1")

        self.store.insert_node(node_id, route_id=route_id, tier="cheap", task="eval",
                               created_at="2026-01-01T00:00:00Z")

        # Add events
        ev0 = self.store.append_event(node_id, "dispatched", "2026-01-01T00:00:00Z")
        ev1 = self.store.append_event(node_id, "returned", "2026-01-01T00:00:01Z",
                                      usage={"seconds": 1.0, "cost_micro_usd": 10})

        # Verify state
        event_rows = self.store.conn.execute(
            "SELECT event_seq,status FROM node_event WHERE node_id=? ORDER BY event_seq",
            (node_id,)
        ).fetchall()
        self.assertEqual(len(event_rows), 2)
        self.assertEqual(event_rows[0], (0, "dispatched"))
        self.assertEqual(event_rows[1], (1, "returned"))

        # Verify usage reachable
        usage_row = self.store.conn.execute(
            "SELECT cost_micro_usd FROM node_usage WHERE node_id=?",
            (node_id,)
        ).fetchone()
        self.assertEqual(usage_row[0], 10)


class TestStoreRouteIdempotentRevert(unittest.TestCase):
    """Test BLOCKER 1: ensure_route idempotent under revert."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.store = Store(self.conn)
        self.store.ensure_provider("openrouter")
        self.store.ensure_vendor("anthropic")
        self.store.ensure_model("haiku", vendor_id="anthropic", model_name="haiku")
        self.store.ensure_model("sonnet", vendor_id="anthropic", model_name="sonnet")

    def tearDown(self) -> None:
        self.store.close()

    def test_route_revert_returns_same_route_id(self) -> None:
        """ensure_route: haiku -> sonnet -> haiku returns same route_id for haiku (rev0)."""
        # First call: allocate route for haiku
        r1 = self.store.ensure_route("openrouter", "cheap-claude", "haiku")

        # Second call: switch to sonnet (allocates new route_id, rev1)
        r2 = self.store.ensure_route("openrouter", "cheap-claude", "sonnet")
        self.assertNotEqual(r1, r2, "Switching model should allocate new route_id")

        # Third call: revert to haiku (MUST return r1, not allocate a third route_id)
        r3 = self.store.ensure_route("openrouter", "cheap-claude", "haiku")
        self.assertEqual(r1, r3, "Reverting to original model must return same route_id, not allocate new one")

        # Verify exactly 2 route rows for this (provider, route_name)
        rows = self.store.conn.execute(
            "SELECT COUNT(*) FROM route WHERE provider_id=? AND route_name=?",
            ("openrouter", "cheap-claude")
        ).fetchone()
        self.assertEqual(rows[0], 2, "Must have exactly 2 routes (rev0 for haiku, rev1 for sonnet)")

        # Verify rev0 still resolves to haiku
        old_row = self.store.conn.execute(
            "SELECT model_id FROM route WHERE route_id=?", (r1,)
        ).fetchone()
        self.assertEqual(old_row[0], "haiku", "Original route_id must still resolve to haiku")


class TestStoreAppendEventAtomicity(unittest.TestCase):
    """Test BLOCKER 2: append_event atomicity with usage violation."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.store = Store(self.conn)
        self.run_id = "run1"
        self.store.insert_run(self.run_id, "2026-01-01T00:00:00Z")
        self.family_id = "fam1"
        self.store.insert_family(self.family_id, self.run_id)
        self.request_id = "req1"
        self.node_id = self.request_id
        self.store.insert_request(self.request_id, self.family_id)
        self.store.insert_node(self.node_id, created_at="2026-01-01T00:00:00Z")

    def tearDown(self) -> None:
        self.store.close()

    def test_append_event_usage_violation_rolls_back(self) -> None:
        """append_event with usage violation raises IntegrityError and rolls back both event and usage."""
        # Try to append event with invalid usage (seconds < 0 violates CHECK)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.append_event(
                self.node_id,
                "returned",
                "2026-01-01T00:00:00Z",
                usage={"seconds": -5}  # Violates CHECK(seconds >= 0)
            )

        # Commit to finalize transaction
        self.store.conn.commit()

        # Verify NO node_event rows were inserted (rollback worked)
        event_count = self.store.conn.execute(
            "SELECT COUNT(*) FROM node_event WHERE node_id=?", (self.node_id,)
        ).fetchone()[0]
        self.assertEqual(event_count, 0, "node_event should not exist after failed append_event")

        # Verify NO usage rows exist either
        usage_count = self.store.conn.execute(
            "SELECT COUNT(*) FROM usage"
        ).fetchone()[0]
        self.assertEqual(usage_count, 0, "usage table should be empty after failed append_event")


class TestStoreGovernanceDocumentVersions(unittest.TestCase):
    """Test BLOCKER 3: governance_document stores and retrieves version strings."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.store = Store(self.conn)

    def tearDown(self) -> None:
        self.store.close()

    def test_governance_document_version_strings_round_trip(self) -> None:
        """ensure_governance_document stores and retrieves governance_version and policy_version."""
        gov_sha = "abc123def456"
        gov_version = "v2.1.0"
        policy_version = "policy-2026-01"

        # Create artifact first (FK constraint)
        self.store.ensure_artifact(gov_sha, size_bytes=1024)

        # Insert with version strings
        self.store.ensure_governance_document(gov_sha, gov_version, policy_version)

        # Query back
        row = self.store.conn.execute(
            "SELECT governance_version, policy_version FROM governance_document WHERE governance_sha=?",
            (gov_sha,)
        ).fetchone()

        self.assertIsNotNone(row, "governance_document row should exist")
        self.assertEqual(row[0], gov_version, f"governance_version should be '{gov_version}', not empty string")
        self.assertEqual(row[1], policy_version, f"policy_version should be '{policy_version}', not empty string")


if __name__ == "__main__":
    unittest.main()
