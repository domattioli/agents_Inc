"""agents_inc.schema must import from a tree without docs/ (installed bundle)."""
import importlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestSchemaWithoutDocs(unittest.TestCase):
    def _tree(self, tmp, with_doc):
        shutil.copytree(ROOT / "agents_inc", Path(tmp) / "agents_inc",
                        ignore=shutil.ignore_patterns("__pycache__"))
        if with_doc:
            doc = Path(tmp) / "docs" / "governance"
            doc.mkdir(parents=True)
            shutil.copy2(ROOT / "docs" / "governance" / "SCHEMA-3NF.md", doc)

    def _py(self, tmp, code):
        return subprocess.run([sys.executable, "-c", code], cwd=tmp,
                              capture_output=True, text=True)

    def test_import_works_without_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._tree(tmp, with_doc=False)
            r = self._py(tmp, "import agents_inc.schema as s; print(s.SCHEMA_VERSION)")
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_missing_doc_gives_clear_error_on_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._tree(tmp, with_doc=False)
            r = self._py(tmp, "import agents_inc.schema as s; s.DDL")
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("SCHEMA-3NF.md", r.stderr)

    def test_bundle_ships_schema_doc(self):
        from agents_inc.install import bundle
        self.assertIn("docs/governance/SCHEMA-3NF.md", bundle.FILE_ALLOWLIST)
        with tempfile.TemporaryDirectory() as tmp:
            self._tree(tmp, with_doc=True)
            r = self._py(tmp, "import sqlite3, agents_inc.schema as s; "
                              "c = sqlite3.connect(':memory:'); s.init(c); print(len(s.TABLES))")
            self.assertEqual(r.returncode, 0, r.stderr)


class TestSchemaStarImport(unittest.TestCase):
    """Verify lazy-loaded names are discoverable via star import."""

    def test_star_import_exposes_ddl(self):
        """Test that `from agents_inc.schema import *` exposes DDL."""
        importlib.reload(sys.modules.get("agents_inc.schema") or __import__("agents_inc.schema"))
        namespace = {}
        exec("from agents_inc.schema import *", namespace)
        self.assertIn("DDL", namespace)
        self.assertIsInstance(namespace["DDL"], str)

    def test_star_import_exposes_queries(self):
        """Test that `from agents_inc.schema import *` exposes QUERIES."""
        namespace = {}
        exec("from agents_inc.schema import *", namespace)
        self.assertIn("QUERIES", namespace)
        self.assertIsInstance(namespace["QUERIES"], dict)

    def test_star_import_exposes_tables(self):
        """Test that `from agents_inc.schema import *` exposes TABLES."""
        namespace = {}
        exec("from agents_inc.schema import *", namespace)
        self.assertIn("TABLES", namespace)
        self.assertIsInstance(namespace["TABLES"], frozenset)


if __name__ == "__main__":
    unittest.main()
