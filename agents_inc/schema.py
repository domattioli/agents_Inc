import re
import sqlite3
from pathlib import Path

SCHEMA_VERSION = "2026-09-05.1"
SCHEMA_DOC = Path(__file__).parent.parent / "docs" / "governance" / "SCHEMA-3NF.md"

def _parse_blocks():
    """Parse SQL blocks from SCHEMA_DOC (on first use, not at import)."""
    try:
        doc_text = SCHEMA_DOC.read_text()
    except OSError as exc:
        raise FileNotFoundError(
            f"agents_inc.schema: schema doc not found at {SCHEMA_DOC}; the 3NF "
            "store needs docs/governance/SCHEMA-3NF.md shipped beside agents_inc/"
        ) from exc

    # Find all fenced sql blocks
    block_pattern = r'```sql\n(.*?)\n```'
    blocks = re.findall(block_pattern, doc_text, re.DOTALL)

    if not blocks:
        raise ValueError("No SQL blocks found in schema doc")

    ddl_blocks = []
    queries = {}
    query_names = {}

    for block in blocks:
        block_stripped = block.strip()
        lines = block_stripped.split('\n')

        # Find first non-blank line
        first_nonempty = None
        for line in lines:
            if line.strip():
                first_nonempty = line.strip()
                break

        # Check if it's a query block (starts with -- qN name)
        if first_nonempty and re.match(r'^--\s+q\d+\s+', first_nonempty):
            match = re.match(r'^--\s+(q\d+)\s+(\w+)', first_nonempty)
            if match:
                q_id = match.group(1)
                q_name = match.group(2)
                queries[q_id] = block_stripped
                query_names[q_id] = q_name
        else:
            # DDL block
            ddl_blocks.append(block_stripped)

    if len(ddl_blocks) != 4:
        raise ValueError(f"Expected exactly 4 DDL blocks, got {len(ddl_blocks)}")
    if len(queries) != 5:
        raise ValueError(f"Expected exactly 5 query blocks (q1..q5), got {len(queries)}")

    ddl = '\n'.join(ddl_blocks)

    return ddl, queries, query_names

_LAZY = {}
_LAZY_NAMES = ("DDL", "QUERIES", "QUERY_NAMES", "TABLES", "VIEWS")
__all__ = list(_LAZY_NAMES)


def _load():
    """Parse the schema doc once and cache DDL, queries, table and view names."""
    if not _LAZY:
        ddl, queries, query_names = _parse_blocks()
        tables = {m.group(1) for m in re.finditer(r'CREATE\s+TABLE\s+(\w+)\s*\(', ddl)}
        views = {m.group(1) for m in re.finditer(r'CREATE\s+VIEW\s+(\w+)\s+AS', ddl)}
        _LAZY.update(DDL=ddl, QUERIES=queries, QUERY_NAMES=query_names,
                     TABLES=frozenset(tables), VIEWS=frozenset(views))
    return _LAZY


def __getattr__(name):
    # PEP 562: DDL, QUERIES, QUERY_NAMES, TABLES, VIEWS resolve on first access,
    # so importing this module works in a tree without docs/.
    if name in _LAZY_NAMES:
        return _load()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """Make lazy-loaded names discoverable in dir() and introspection."""
    return sorted(list(_LAZY_NAMES) + ['init', '__all__'])

def init(conn):
    """Initialize DB with schema. Idempotent. Sets PRAGMA foreign_keys=ON."""
    conn.execute("PRAGMA foreign_keys = ON")

    # Check if schema already present by comparing object names
    cursor = conn.execute(
        "SELECT name, type FROM sqlite_master "
        "WHERE type IN ('table', 'view')"
    )
    existing_names = set()
    for row in cursor.fetchall():
        name = row[0]
        # Exclude sqlite internal names
        if not name.startswith('sqlite_'):
            existing_names.add(name)

    lazy = _load()
    expected_names = lazy["TABLES"] | lazy["VIEWS"]

    # If schema fully present, return early (idempotent)
    if existing_names == expected_names:
        return

    # If empty database, initialize fresh
    if len(existing_names) == 0:
        conn.executescript(lazy["DDL"])
        return

    # Otherwise, mismatch detected (partial, extra, or wrong objects)
    missing = expected_names - existing_names
    unexpected = existing_names - expected_names
    raise RuntimeError(
        f"Schema mismatch: missing={sorted(missing)}, unexpected={sorted(unexpected)}"
    )
