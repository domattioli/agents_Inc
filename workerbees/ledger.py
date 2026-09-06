"""Append-only dispatch graph ledger — records delegated jobs as nodes with edges.

Data model: Node (dispatched job), Edge (implied by parent_id + edge_type), Run (groups nodes by run_id).
I/O: JSONL file at <workspace>/.workerbees/ledger.jsonl, idempotent by node id on read.
Lint: Three rules (depth, same_vendor_review, frontier_without_gate) with deterministic findings.
Export: JSON (round-trippable) and Mermaid (human-readable graph).
Rollup: Cost per root node (subscription calls + seconds).

Dual-write mode: controlled by WORKERBEES_STORE env var (jsonl|sqlite|both, default both).
When jsonl: JSONL only, no sqlite writes, byte-identical to pre-dual-write behavior.
When sqlite: normalized 3NF schema only, no JSONL.
When both: both JSONL and sqlite.

Synthetic family generation for dual-write:
- One family per run_id (family_id = f"synthetic-{run_id}")
- request_id == node_id (schema FK: node.node_id REFERENCES request(request_id))
- All writes are idempotent (duplicate inserts swallowed via IntegrityError catch)

All recording functions swallow errors per FR-008 (ledger failure never fails a brief).
"""
from __future__ import annotations
import datetime
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Node:
    """One delegated job (worker, reviewer, correction, doctor probe)."""
    id: str
    run_id: str
    model: str
    tier: str  # cheap | mid | frontier
    task: str
    provider: str
    parent_id: str | None
    edge_type: str | None  # reviews | corrects | probes | depends-on | None
    status: str  # dispatched | returned | needs-review | verified | paused | blocked | etc.
    seconds: float | None
    subscription_calls: int | None
    gate_reason: str | None
    timestamp: str  # ISO-8601 UTC


@dataclass(frozen=True)
class Finding:
    """Lint result."""
    rule: str  # depth | same_vendor_review | frontier_without_gate
    node_ids: list[str]
    message: str


@dataclass
class Ledger:
    """In-memory ledger state."""
    nodes: dict[str, Node]  # keyed by node id
    warnings: list[str]  # load warnings (corrupt lines, etc.)


def _now_iso() -> str:
    """Current time in ISO-8601 UTC with microsecond precision."""
    now = time.time()
    dt = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
    return dt.isoformat(timespec='microseconds').replace('+00:00', 'Z')


def record_dispatch(workspace: Path, *, node_id: str, run_id: str, model: str, tier: str,
                    task: str, provider: str, parent_id: str | None, edge_type: str | None,
                    gate_reason: str | None = None,
                    artifact_hash: str | None = None, artifact_size: int = 0) -> bool:
    """Record a job dispatch. Idempotent on node id (dedup on read). Never raises (FR-008).

    Dual-write mode controlled by WORKERBEES_STORE env var (jsonl|sqlite|both, default both).
    Returns True on success, False on any error.

    Raises ValueError if WORKERBEES_STORE has invalid value (checked before swallowing).
    """
    # Validate flag before try block so ValueError propagates
    store_mode = os.environ.get("WORKERBEES_STORE", "both").lower()
    if store_mode not in ("jsonl", "sqlite", "both"):
        raise ValueError(f"Invalid WORKERBEES_STORE value: {store_mode!r}")

    try:
        d = workspace / ".workerbees"
        d.mkdir(parents=True, exist_ok=True)

        # Write to JSONL if requested (jsonl or both modes)
        if store_mode in ("jsonl", "both"):
            ledger_file = d / "ledger.jsonl"
            line = json.dumps({
                "id": node_id,
                "run_id": run_id,
                "model": model,
                "tier": tier,
                "task": task,
                "provider": provider,
                "parent_id": parent_id,
                "edge_type": edge_type,
                "status": "dispatched",
                "seconds": None,
                "subscription_calls": None,
                "gate_reason": gate_reason,
                "artifact_hash": artifact_hash,
                "timestamp": _now_iso()
            })
            with open(ledger_file, "a") as f:
                f.write(line + "\n")

        # Write to sqlite if requested (both or sqlite modes)
        if store_mode in ("sqlite", "both"):
            _dual_write_dispatch(workspace, node_id, run_id, model, tier, task, provider,
                                parent_id, edge_type, gate_reason, artifact_hash, artifact_size)

        return True
    except Exception:
        return False  # Swallow all errors per FR-008


def _dual_write_dispatch(workspace: Path, node_id: str, run_id: str, model: str, tier: str,
                         task: str, provider: str, parent_id: str | None, edge_type: str | None,
                         gate_reason: str | None, artifact_hash: str | None = None,
                         artifact_size: int = 0) -> None:
    """Write dispatch event to normalized 3NF schema. Idempotent via IntegrityError catch.

    Creates synthetic family (family_id = f"synthetic-{run_id}") and request (request_id == node_id).
    Raises on real errors; swallowed by record_dispatch per FR-008.
    """
    from workerbees.store import Store
    import sqlite3

    d = workspace / ".workerbees"
    db_path = d / "workerbees.db"

    with Store(db_path) as store:
        now = _now_iso()

        # Synthetic family: one per run_id (stable, idempotent)
        family_id = f"synthetic-{run_id}"

        try:
            # Insert run (non-idempotent, but catch dup)
            store.insert_run(run_id, now)
        except sqlite3.IntegrityError:
            pass  # Run already exists

        try:
            # Insert synthetic family (one per run)
            store.insert_family(family_id, run_id, label=None)
        except sqlite3.IntegrityError:
            pass  # Family already exists for this run

        try:
            # Insert request (request_id == node_id, FK to family)
            store.insert_request(node_id, family_id, envelope_hash=None)
        except sqlite3.IntegrityError:
            pass  # Request already exists

        # Ensure provider and model are in DB
        store.ensure_provider(provider)
        store.ensure_model(model, vendor_id=None)

        # Create route binding
        try:
            route_id = store.ensure_route(provider, f"dispatch-{task}", model)
        except sqlite3.IntegrityError:
            route_id = None

        try:
            # Insert node (node_id IS request_id, FK to request)
            store.insert_node(node_id, route_id=route_id, tier=tier, task=task, created_at=now)
        except sqlite3.IntegrityError:
            pass  # Node already exists

        try:
            # Append dispatch event
            store.append_event(node_id, "dispatched", now, usage=None)
        except sqlite3.IntegrityError:
            pass  # Event already exists (shouldn't happen, but safe)

        # Write lineage (parent-child relationship)
        if parent_id and edge_type in ("corrects", "depends-on"):
            try:
                store.insert_lineage(node_id, parent_id)
            except sqlite3.IntegrityError:
                pass  # Lineage already exists

        # Write graph edge (edge type)
        if edge_type and parent_id:
            try:
                store.insert_graph_edge(node_id, parent_id, edge_type)
            except sqlite3.IntegrityError:
                pass  # Edge already exists

        if gate_reason:
            try:
                store.insert_frontier_gate(node_id, gate_reason)
            except sqlite3.IntegrityError:
                pass

        if artifact_hash and parent_id and edge_type:
            store.ensure_artifact(artifact_hash, artifact_size)
            try:
                store.insert_edge_artifact(node_id, parent_id, edge_type, 0,
                                           artifact_hash, "candidate")
            except sqlite3.IntegrityError:
                pass

        # Write legacy_parent (002 projection: all nodes with nullable parent/edge_type).
        # Probe nodes have parent_id=None and edge_type="probes"; this table holds them.
        try:
            store.insert_legacy_parent(node_id, parent_id, edge_type)
        except sqlite3.IntegrityError:
            pass  # Legacy parent already exists

        # Commit changes
        store.conn.commit()


def record_return(workspace: Path, *, node_id: str, status: str, seconds: float,
                  subscription_calls: int) -> bool:
    """Record a job return (terminal status). Idempotent on node id. Never raises (FR-008).

    Dual-write mode controlled by WORKERBEES_STORE env var (jsonl|sqlite|both, default both).
    Returns True on success, False on any error.

    Raises ValueError if WORKERBEES_STORE has invalid value (checked before swallowing).
    """
    # Validate flag before try block so ValueError propagates
    store_mode = os.environ.get("WORKERBEES_STORE", "both").lower()
    if store_mode not in ("jsonl", "sqlite", "both"):
        raise ValueError(f"Invalid WORKERBEES_STORE value: {store_mode!r}")

    try:
        d = workspace / ".workerbees"
        d.mkdir(parents=True, exist_ok=True)

        # Write to JSONL if requested (jsonl or both modes)
        if store_mode in ("jsonl", "both"):
            ledger_file = d / "ledger.jsonl"
            line = json.dumps({
                "id": node_id,
                "run_id": None,
                "model": None,
                "tier": None,
                "task": None,
                "provider": None,
                "parent_id": None,
                "edge_type": None,
                "status": status,
                "seconds": seconds,
                "subscription_calls": subscription_calls,
                "gate_reason": None,
                "timestamp": _now_iso()
            })
            with open(ledger_file, "a") as f:
                f.write(line + "\n")

        # Write to sqlite if requested (both or sqlite modes)
        if store_mode in ("sqlite", "both"):
            _dual_write_return(workspace, node_id, status, seconds, subscription_calls)

        return True
    except Exception:
        return False  # Swallow all errors per FR-008


def _dual_write_return(workspace: Path, node_id: str, status: str, seconds: float,
                       subscription_calls: int) -> None:
    """Write return event to normalized 3NF schema. Idempotent via IntegrityError catch.

    Appends event record to node. Raises on real errors; swallowed by record_return per FR-008.
    """
    from workerbees.store import Store
    import sqlite3

    d = workspace / ".workerbees"
    db_path = d / "workerbees.db"

    with Store(db_path) as store:
        now = _now_iso()
        usage = {
            "seconds": seconds,
            "subscription_calls": subscription_calls
        }

        try:
            # Append return event with usage
            store.append_event(node_id, status, now, usage=usage)
        except sqlite3.IntegrityError:
            # Seq collision unlikely, but if it happens, silently skip
            pass

        # Commit changes
        store.conn.commit()


def load(workspace: Path) -> Ledger:
    """Load ledger from JSONL file or sqlite DB; dedupe by node id.

    Loads from JSONL if it exists (compatibility mode).
    Falls back to sqlite if JSONL missing but workerbees.db exists (sqlite-only mode).
    Returns empty Ledger + warnings on corrupt/missing file, never raises.
    """
    ledger_file = workspace / ".workerbees" / "ledger.jsonl"
    nodes: dict[str, Node] = {}
    warnings: list[str] = []

    store_mode = os.environ.get("WORKERBEES_STORE", "both").lower()
    if store_mode not in ("jsonl", "sqlite", "both"):
        warnings.append(f"Invalid WORKERBEES_STORE value: {store_mode!r}")
        return Ledger(nodes=nodes, warnings=warnings)

    # Selected backend is authoritative. Both preserves JSONL compatibility.
    if ledger_file.exists() and store_mode != "sqlite":
        try:
            with open(ledger_file) as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        node_id = data.get("id", "")

                        if node_id not in nodes:
                            # First record for this id
                            node = Node(
                                id=node_id,
                                run_id=data.get("run_id"),
                                model=data.get("model"),
                                tier=data.get("tier"),
                                task=data.get("task"),
                                provider=data.get("provider"),
                                parent_id=data.get("parent_id"),
                                edge_type=data.get("edge_type"),
                                status=data.get("status", "unknown"),
                                seconds=data.get("seconds"),
                                subscription_calls=data.get("subscription_calls"),
                                gate_reason=data.get("gate_reason"),
                                timestamp=data.get("timestamp", "")
                            )
                            nodes[node_id] = node
                        else:
                            # Merge with existing: keep non-null fields, prefer later timestamp
                            existing = nodes[node_id]
                            new_timestamp = data.get("timestamp", "")
                            if (new_timestamp or "") > (existing.timestamp or ""):
                                # New record is later, merge in the updated fields
                                node = Node(
                                    id=node_id,
                                    run_id=data.get("run_id") or existing.run_id,
                                    model=data.get("model") or existing.model,
                                    tier=data.get("tier") or existing.tier,
                                    task=data.get("task") or existing.task,
                                    provider=data.get("provider") or existing.provider,
                                    parent_id=data.get("parent_id") or existing.parent_id,
                                    edge_type=data.get("edge_type") or existing.edge_type,
                                    status=data.get("status") or existing.status,
                                    seconds=data.get("seconds") if data.get("seconds") is not None else existing.seconds,
                                    subscription_calls=data.get("subscription_calls") if data.get("subscription_calls") is not None else existing.subscription_calls,
                                    gate_reason=data.get("gate_reason") or existing.gate_reason,
                                    timestamp=new_timestamp
                                )
                                nodes[node_id] = node
                    except json.JSONDecodeError:
                        warnings.append(f"Line {line_num}: invalid JSON")
        except OSError as e:
            warnings.append(f"Failed to read ledger file: {e}")

        return Ledger(nodes=nodes, warnings=warnings)

    # Fallback: try sqlite if JSONL missing (sqlite-only mode compatibility)
    db_file = workspace / ".workerbees" / "workerbees.db"
    if db_file.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_file))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Load nodes with all related data
            rows = cursor.execute("""
                SELECT n.node_id, n.route_id, n.tier, n.task, n.created_at,
                       r.model_id, r.provider_id,
                       (SELECT f.run_id FROM request req
                        JOIN family f ON req.family_id = f.family_id
                        WHERE req.request_id = n.node_id) as run_id
                FROM node n
                LEFT JOIN route r ON n.route_id = r.route_id
            """).fetchall()

            # Build parent_id and edge_type maps from legacy_parent (002 projection).
            # This table is the authority for both, and includes probe nodes (parent_id=None).
            parent_map = {}
            edge_map = {}
            legacy_rows = cursor.execute("SELECT child_id, parent_id, edge_type FROM legacy_parent").fetchall()
            for row in legacy_rows:
                parent_map[row["child_id"]] = row["parent_id"]
                edge_map[row["child_id"]] = row["edge_type"]

            # Build status and usage maps from node events
            status_map = {}
            cursor.execute("""
                SELECT n.node_id,
                       (SELECT ne.status FROM node_event ne
                        WHERE ne.node_id = n.node_id
                        ORDER BY ne.event_seq DESC LIMIT 1) as status
                FROM node n
            """)
            for row in cursor.fetchall():
                if row["status"]:
                    status_map[row["node_id"]] = row["status"]

            usage_map = {}
            cursor.execute("""
                SELECT n.node_id,
                       (SELECT u.seconds FROM node_event ne
                        JOIN usage u ON u.event_id = ne.event_id
                        WHERE ne.node_id = n.node_id
                        ORDER BY ne.event_seq DESC LIMIT 1) as seconds,
                       (SELECT u.subscription_calls FROM node_event ne
                        JOIN usage u ON u.event_id = ne.event_id
                        WHERE ne.node_id = n.node_id
                        ORDER BY ne.event_seq DESC LIMIT 1) as subscription_calls
                FROM node n
            """)
            for row in cursor.fetchall():
                usage_map[row["node_id"]] = (row["seconds"], row["subscription_calls"])

            for row in rows:
                node_id = row["node_id"]
                status = status_map.get(node_id, "unknown")
                seconds, subscription_calls = usage_map.get(node_id, (None, None))
                parent_id = parent_map.get(node_id)
                edge_type = edge_map.get(node_id)

                node = Node(
                    id=node_id,
                    run_id=row["run_id"],
                    model=row["model_id"],
                    tier=row["tier"],
                    task=row["task"],
                    provider=row["provider_id"],
                    parent_id=parent_id,
                    edge_type=edge_type,
                    status=status,
                    seconds=seconds,
                    subscription_calls=subscription_calls,
                    gate_reason=None,
                    timestamp=row["created_at"] or ""
                )
                nodes[node_id] = node

            conn.close()
        except Exception as e:
            warnings.append(f"Failed to load from sqlite: {e}")

    return Ledger(nodes=nodes, warnings=warnings)


def lint(ledger: Ledger) -> list[Finding]:
    """Check three lint rules on the ledger; return findings (no model calls, deterministic).

    Rules:
    1. depth: node with true depth > 1 (more than one parent-child edge from root)
    2. same_vendor_review: reviewer node with same provider as reviewed node
    3. frontier_without_gate: frontier tier node with null/empty gate_reason
    """
    findings: list[Finding] = []

    # Rule 1: depth (compute true depth by walking parent chain; flag if depth > 1)
    def compute_depth(node_id: str) -> int:
        """Return depth: 0 if no parent, 1 if root's child, 2+ if deeper."""
        depth = 0
        current_id = node_id
        while current_id and current_id in ledger.nodes:
            parent = ledger.nodes[current_id]
            if parent.parent_id is None:
                break
            depth += 1
            current_id = parent.parent_id
        return depth

    for node in ledger.nodes.values():
        if compute_depth(node.id) > 1:
            findings.append(Finding(
                rule="depth",
                node_ids=[node.id],
                message=f"Node {node.id} has depth > 1"
            ))

    # Rule 2: same_vendor_review
    for node in ledger.nodes.values():
        if node.edge_type == "reviews" and node.parent_id and node.parent_id in ledger.nodes:
            parent = ledger.nodes[node.parent_id]
            if node.provider == parent.provider:
                findings.append(Finding(
                    rule="same_vendor_review",
                    node_ids=[parent.id, node.id],
                    message=f"Reviewer {node.id} ({node.provider}) reviewing {parent.id} ({parent.provider})"
                ))

    # Rule 3: frontier_without_gate
    for node in ledger.nodes.values():
        if node.tier == "frontier":
            if not node.gate_reason or not node.gate_reason.strip():
                findings.append(Finding(
                    rule="frontier_without_gate",
                    node_ids=[node.id],
                    message=f"Frontier node {node.id} has no gate_reason"
                ))

    return findings


def to_json(ledger: Ledger) -> str:
    """Export ledger as JSON. Format: {"nodes": [...]}, round-trippable."""
    nodes_list = [
        {
            "id": n.id,
            "run_id": n.run_id,
            "model": n.model,
            "tier": n.tier,
            "task": n.task,
            "provider": n.provider,
            "parent_id": n.parent_id,
            "edge_type": n.edge_type,
            "status": n.status,
            "seconds": n.seconds,
            "subscription_calls": n.subscription_calls,
            "gate_reason": n.gate_reason,
            "timestamp": n.timestamp,
        }
        for n in ledger.nodes.values()
    ]
    return json.dumps({"nodes": nodes_list})


def from_json(s: str) -> Ledger:
    """Deserialize JSON to Ledger (inverse of to_json)."""
    try:
        data = json.loads(s)
        nodes: dict[str, Node] = {}
        for node_data in data.get("nodes", []):
            node = Node(
                id=node_data.get("id", ""),
                run_id=node_data.get("run_id"),
                model=node_data.get("model"),
                tier=node_data.get("tier"),
                task=node_data.get("task"),
                provider=node_data.get("provider"),
                parent_id=node_data.get("parent_id"),
                edge_type=node_data.get("edge_type"),
                status=node_data.get("status", "unknown"),
                seconds=node_data.get("seconds"),
                subscription_calls=node_data.get("subscription_calls"),
                gate_reason=node_data.get("gate_reason"),
                timestamp=node_data.get("timestamp", ""),
            )
            nodes[node.id] = node
        return Ledger(nodes=nodes, warnings=[])
    except json.JSONDecodeError:
        return Ledger(nodes={}, warnings=["Invalid JSON"])


def to_mermaid(ledger: Ledger) -> str:
    """Export ledger as Mermaid diagram (graph TD format).

    Escapes special characters in labels (", |, [, ]) for Mermaid syntax.
    """
    def escape_label(text: str) -> str:
        """Escape Mermaid special chars in labels."""
        text = text.replace('\\', '\\\\')  # Backslash first
        text = text.replace('"', '\\"')
        text = text.replace('|', '\\|')
        text = text.replace('[', '\\[')
        text = text.replace(']', '\\]')
        return text

    lines = ["graph TD"]
    # Add nodes
    for node in ledger.nodes.values():
        label = f"{node.task}/{node.model}"
        escaped_label = escape_label(label)
        lines.append(f'  {node.id}["{escaped_label}"]')
    # Add edges
    for node in ledger.nodes.values():
        if node.parent_id and node.edge_type:
            escaped_edge_type = escape_label(node.edge_type)
            lines.append(f'  {node.id} -->|{escaped_edge_type}| {node.parent_id}')
    return "\n".join(lines)


def rollup(ledger: Ledger) -> dict[str, dict[str, float | int]]:
    """Compute cost rollup per root node (subscriptions calls + seconds over subtree).

    Returns {root_id: {"calls": int, "seconds": float}}.
    """
    result: dict[str, dict[str, float | int]] = {}

    # Find all root nodes (parent_id is None)
    root_ids = {n.id for n in ledger.nodes.values() if n.parent_id is None}

    for root_id in root_ids:
        calls = 0
        seconds = 0.0
        # Walk the subtree via DFS following parent_id edges
        visited = set()
        stack = [root_id]
        while stack:
            nid = stack.pop()
            if nid in visited or nid not in ledger.nodes:
                continue
            visited.add(nid)
            node = ledger.nodes[nid]
            if node.subscription_calls is not None:
                calls += node.subscription_calls
            if node.seconds is not None:
                seconds += node.seconds
            # Find all children of this node
            for other in ledger.nodes.values():
                if other.parent_id == nid and other.id not in visited:
                    stack.append(other.id)
        result[root_id] = {"calls": calls, "seconds": seconds}

    return result
