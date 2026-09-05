"""Append-only dispatch graph ledger — records delegated jobs as nodes with edges.

Data model: Node (dispatched job), Edge (implied by parent_id + edge_type), Run (groups nodes by run_id).
I/O: JSONL file at <workspace>/.workerbees/ledger.jsonl, idempotent by node id on read.
Lint: Three rules (depth, same_vendor_review, frontier_without_gate) with deterministic findings.
Export: JSON (round-trippable) and Mermaid (human-readable graph).
Rollup: Cost per root node (subscription calls + seconds).

All recording functions swallow errors per FR-008 (ledger failure never fails a brief).
"""
from __future__ import annotations
import datetime
import json
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
                    gate_reason: str | None = None) -> bool:
    """Record a job dispatch. Idempotent on node id (dedup on read). Never raises (FR-008).

    Returns True on success, False on any error.
    """
    try:
        d = workspace / ".workerbees"
        d.mkdir(parents=True, exist_ok=True)
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
            "timestamp": _now_iso()
        })
        with open(ledger_file, "a") as f:
            f.write(line + "\n")
        return True
    except Exception:
        return False  # Swallow all errors per FR-008


def record_return(workspace: Path, *, node_id: str, status: str, seconds: float,
                  subscription_calls: int) -> bool:
    """Record a job return (terminal status). Idempotent on node id. Never raises (FR-008).

    Returns True on success, False on any error.
    """
    try:
        d = workspace / ".workerbees"
        d.mkdir(parents=True, exist_ok=True)
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
        return True
    except Exception:
        return False  # Swallow all errors per FR-008


def load(workspace: Path) -> Ledger:
    """Load ledger from JSONL file; dedupe by node id (merge dispatch + return records).

    Returns empty Ledger + warnings on corrupt/missing file, never raises.
    """
    ledger_file = workspace / ".workerbees" / "ledger.jsonl"
    nodes: dict[str, Node] = {}
    warnings: list[str] = []

    if not ledger_file.exists():
        return Ledger(nodes={}, warnings=[])

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
