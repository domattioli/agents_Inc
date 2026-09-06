import re
import sqlite3
import unittest
from workerbees import schema


class TestSchema(unittest.TestCase):
    """Test suite for workerbees.schema module."""

    def setUp(self):
        """Create fresh in-memory DB and initialize schema."""
        self.conn = sqlite3.connect(':memory:')
        schema.init(self.conn)

    def tearDown(self):
        """Close connection."""
        self.conn.close()

    def test_schema_version_nonempty(self):
        """SCHEMA_VERSION must be a nonempty string."""
        self.assertIsInstance(schema.SCHEMA_VERSION, str)
        self.assertTrue(len(schema.SCHEMA_VERSION) > 0)

    def test_all_table_names_exist(self):
        """Every table in TABLES must exist in sqlite_master."""
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        existing_tables = {row[0] for row in cursor.fetchall()}
        for table_name in schema.TABLES:
            self.assertIn(
                table_name, existing_tables,
                f"Table {table_name} not found in database"
            )

    def test_all_view_names_exist(self):
        """Every view in VIEWS must exist in sqlite_master."""
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        )
        existing_views = {row[0] for row in cursor.fetchall()}
        for view_name in schema.VIEWS:
            self.assertIn(
                view_name, existing_views,
                f"View {view_name} not found in database"
            )

    def test_table_count_equals_42(self):
        """Exactly 42 tables must be created."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        )
        count = cursor.fetchone()[0]
        self.assertEqual(count, 42, f"Expected 42 tables, found {count}")

    def test_view_count_equals_2(self):
        """Exactly 2 views must be created."""
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='view'"
        )
        count = cursor.fetchone()[0]
        self.assertEqual(count, 2, f"Expected 2 views, found {count}")

    def test_queries_q1_through_q5_execute(self):
        """Each query q1..q5 must execute successfully with dummy params."""
        for q_id in ['q1', 'q2', 'q3', 'q4', 'q5']:
            sql = schema.QUERIES[q_id]
            # Extract all :placeholder names
            placeholders = re.findall(r':(\w+)', sql)
            # Build param dict with dummy values
            params = {ph: 'test_value' for ph in set(placeholders)}
            # Should execute without error (result may be empty)
            with self.subTest(query=q_id):
                try:
                    cursor = self.conn.execute(sql, params)
                    cursor.fetchall()
                except Exception as e:
                    self.fail(f"Query {q_id} failed to execute: {e}")

    def test_init_idempotent(self):
        """Calling init() twice on same conn must not raise and leave 42 tables."""
        # Call init again on existing initialized connection
        schema.init(self.conn)
        # Check table count is still 42
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        )
        count = cursor.fetchone()[0]
        self.assertEqual(
            count, 42,
            f"After second init(), expected 42 tables, found {count}"
        )

    def test_foreign_keys_pragma_enabled(self):
        """After init(), PRAGMA foreign_keys must be ON (return 1)."""
        cursor = self.conn.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()[0]
        self.assertEqual(
            result, 1,
            f"Expected PRAGMA foreign_keys=1, got {result}"
        )

    def test_query_names_parsed(self):
        """QUERY_NAMES must map q1..q5 to their names."""
        expected = {
            'q1': 'ancestry_depth',
            'q2': 'subtree_metrics',
            'q3': 'reviewer_other_vendor_lint',
            'q4': 'frontier_without_gate',
            'q5': 'graph_subtree_calls',
        }
        for q_id, q_name in expected.items():
            self.assertIn(q_id, schema.QUERY_NAMES)
            self.assertEqual(
                schema.QUERY_NAMES[q_id], q_name,
                f"Query {q_id} name mismatch"
            )

    def test_required_table_and_view_names_exist(self):
        """Hardcoded required tables and views must exist in sqlite_master."""
        required_tables = {
            'vendor', 'provider', 'model', 'route', 'artifact', 'snapshot',
            'agent', 'run', 'family', 'request', 'node', 'node_event',
            'usage', 'lineage', 'graph_edge', 'decision', 'reservation',
            'replay', 'lease', 'approval'
        }
        required_views = {'node_state', 'node_usage'}

        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        existing_tables = {row[0] for row in cursor.fetchall()}

        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        )
        existing_views = {row[0] for row in cursor.fetchall()}

        for table_name in required_tables:
            self.assertIn(
                table_name, existing_tables,
                f"Required table {table_name} not found in database"
            )

        for view_name in required_views:
            self.assertIn(
                view_name, existing_views,
                f"Required view {view_name} not found in database"
            )

    def test_init_rejects_wrong_schema_names(self):
        """init() must raise RuntimeError if db has wrong table/view names."""
        # Create a fresh in-memory connection with wrong schema
        wrong_conn = sqlite3.connect(':memory:')

        # Create 42 dummy tables with wrong names (not in schema.TABLES)
        for i in range(42):
            wrong_conn.execute(f"CREATE TABLE dummy_table_{i} (id INTEGER)")

        # Create 2 dummy views with wrong names (not in schema.VIEWS)
        wrong_conn.execute("CREATE VIEW dummy_view_0 AS SELECT 1")
        wrong_conn.execute("CREATE VIEW dummy_view_1 AS SELECT 1")

        # Calling schema.init() should raise RuntimeError
        with self.assertRaises(RuntimeError) as context:
            schema.init(wrong_conn)

        wrong_conn.close()

        # Verify the error message mentions mismatch
        error_msg = str(context.exception)
        self.assertIn("mismatch", error_msg.lower())

    def test_init_cleanly_idempotent_on_correct_schema(self):
        """init() must return cleanly when called on correctly initialized db."""
        # The connection in setUp already has correct schema
        # Calling init again should not raise
        try:
            schema.init(self.conn)
        except Exception as e:
            self.fail(f"init() raised unexpectedly on correct schema: {e}")

        # Verify schema is still intact
        cursor = self.conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        )
        count = cursor.fetchone()[0]
        self.assertEqual(count, 42)


if __name__ == '__main__':
    unittest.main()
