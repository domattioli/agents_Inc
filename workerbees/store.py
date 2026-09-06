"""Write API over normalized 3NF schema. Mirrors ledger/control emissions into DB tables.

RAISES on constraint violations—no swallowing. Reference-data helpers idempotent;
fact/event tables non-idempotent (duplicate PK raises IntegrityError).
"""
from __future__ import annotations
import sqlite3
import uuid
from pathlib import Path
from typing import Optional


class Store:
    """Write API over 3NF dispatch schema.

    Idempotent on reference data (vendors, models, routes, etc.).
    Non-idempotent on fact/event tables (node_event, decision, usage, ...).
    Always PRAGMA foreign_keys=ON.
    """

    def __init__(self, conn_or_path: sqlite3.Connection | str | Path) -> None:
        """Init DB conn. Calls schema.init(conn). Sets PRAGMA foreign_keys=ON.

        Args: conn_or_path: sqlite3.Connection or path str/Path to DB file.
        """
        from workerbees import schema

        if isinstance(conn_or_path, sqlite3.Connection):
            self.conn = conn_or_path
            self.owns_conn = False
        else:
            self.conn = sqlite3.connect(str(conn_or_path))
            self.owns_conn = True

        schema.init(self.conn)
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        """Close conn if owned."""
        if self.owns_conn:
            self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # Reference-data helpers (idempotent upserts)

    def ensure_vendor(self, vendor_id: str) -> str:
        """Idempotent insert vendor. Returns vendor_id."""
        self.conn.execute(
            "INSERT OR IGNORE INTO vendor(vendor_id) VALUES (?)",
            (vendor_id,)
        )
        return vendor_id

    def ensure_provider(self, provider_id: str) -> str:
        """Idempotent insert provider. Returns provider_id."""
        self.conn.execute(
            "INSERT OR IGNORE INTO provider(provider_id) VALUES (?)",
            (provider_id,)
        )
        return provider_id

    def ensure_model(self, model_id: str, vendor_id: Optional[str] = None,
                     model_name: str = "") -> str:
        """Idempotent insert model. Returns model_id."""
        self.conn.execute(
            "INSERT OR IGNORE INTO model(model_id,vendor_id,model_name) VALUES (?,?,?)",
            (model_id, vendor_id, model_name or "")
        )
        return model_id

    def ensure_artifact(self, sha256: str, size_bytes: int) -> str:
        """Idempotent insert artifact. Returns sha256."""
        self.conn.execute(
            "INSERT OR IGNORE INTO artifact(sha256,size_bytes) VALUES (?,?)",
            (sha256, size_bytes)
        )
        return sha256

    def ensure_route(self, provider_id: str, route_name: str, model_id: Optional[str],
                     route_id: Optional[str] = None) -> str:
        """Route alias freeze: (provider,route_name,model) binding immutable.

        Same (provider,route_name,model_id) triple: returns existing route_id.
        Same (provider,route_name) but DIFFERENT model_id: allocates NEW revision.
        Old row binding remains unchanged (3NF snapshot).

        Args: provider_id, route_name, model_id, optional route_id (auto-generated if None).
        Returns: route_id (existing if match, new if model changed).
        Raises: IntegrityError on malformed input (no provider/model in DB).
        """
        # Check if (provider,route_name,model_id) already exists in ANY revision
        existing_row = self.conn.execute(
            "SELECT route_id FROM route "
            "WHERE provider_id=? AND route_name=? AND model_id=? "
            "LIMIT 1",
            (provider_id, route_name, model_id)
        ).fetchone()

        if existing_row is not None:
            # Exact match found in any revision: return existing route_id (idempotent)
            return existing_row[0]

        # No match for this (provider,route_name,model_id): need to allocate new route_id
        # Check if (provider,route_name) exists to compute next revision
        max_rev_row = self.conn.execute(
            "SELECT MAX(revision) FROM route "
            "WHERE provider_id=? AND route_name=?",
            (provider_id, route_name)
        ).fetchone()

        max_rev = max_rev_row[0] if max_rev_row[0] is not None else -1
        new_rev = max_rev + 1

        if route_id is None:
            route_id = str(uuid.uuid4())

        self.conn.execute(
            "INSERT INTO route(route_id,provider_id,route_name,revision,model_id) "
            "VALUES (?,?,?,?,?)",
            (route_id, provider_id, route_name, new_rev, model_id)
        )
        return route_id

    # Run/family/request

    def insert_run(self, run_id: str, created_at: str, outcome: Optional[str] = None) -> None:
        """Insert run (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO run(run_id,created_at,outcome) VALUES (?,?,?)",
            (run_id, created_at, outcome)
        )

    def insert_family(self, family_id: str, run_id: str, label: Optional[str] = None) -> None:
        """Insert family (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO family(family_id,run_id,label) VALUES (?,?,?)",
            (family_id, run_id, label)
        )

    def insert_request(self, request_id: str, family_id: str,
                       envelope_hash: Optional[str] = None) -> None:
        """Insert request (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO request(request_id,family_id,envelope_hash) VALUES (?,?,?)",
            (request_id, family_id, envelope_hash)
        )

    # Node & events

    def insert_node(self, node_id: str, route_id: Optional[str] = None,
                    tier: Optional[str] = None, task: Optional[str] = None,
                    created_at: str = "") -> None:
        """Insert node (fact table, non-idempotent). node_id IS request_id.

        Raises IntegrityError on duplicate or missing request_id FK.
        """
        self.conn.execute(
            "INSERT INTO node(node_id,route_id,tier,task,created_at) VALUES (?,?,?,?,?)",
            (node_id, route_id, tier, task, created_at)
        )

    def append_event(self, node_id: str, status: str, occurred_at: str,
                     usage: Optional[dict] = None) -> int:
        """Allocate and append event to node. Auto-increment event_seq per node.

        If usage dict provided, writes matching usage row keyed on returned event_id.
        Usage dict: seconds, subscription_calls, input_tokens, output_tokens,
                    reasoning_tokens, cost_micro_usd (all optional).

        Returns: event_id (sqlite AUTOINCREMENT).
        Raises: IntegrityError on duplicate seq or missing node_id.
        Note: seq allocation is SELECT-MAX-then-INSERT and therefore TOCTOU under
        concurrent writers on same node, but fails CLOSED via UNIQUE(node_id,event_seq)—
        one writer gets IntegrityError, never silent interleave—caller must retry.
        """
        # Get next seq for this node
        row = self.conn.execute(
            "SELECT MAX(event_seq) FROM node_event WHERE node_id=?",
            (node_id,)
        ).fetchone()
        max_seq = row[0] if row[0] is not None else -1
        next_seq = max_seq + 1

        # Use SAVEPOINT for atomicity: if usage insert fails, rollback both inserts
        self.conn.execute("SAVEPOINT append_event_sp")
        try:
            # Insert event
            cur = self.conn.execute(
                "INSERT INTO node_event(node_id,event_seq,status,occurred_at) "
                "VALUES (?,?,?,?)",
                (node_id, next_seq, status, occurred_at)
            )
            event_id = cur.lastrowid

            # Insert usage if provided
            if usage is not None:
                self.conn.execute(
                    "INSERT INTO usage(event_id,seconds,subscription_calls,input_tokens,"
                    "output_tokens,reasoning_tokens,cost_micro_usd) VALUES (?,?,?,?,?,?,?)",
                    (event_id, usage.get("seconds"), usage.get("subscription_calls"),
                     usage.get("input_tokens"), usage.get("output_tokens"),
                     usage.get("reasoning_tokens"), usage.get("cost_micro_usd"))
                )
        except Exception:
            # Rollback to savepoint on any exception (including usage CHECK violations)
            self.conn.execute("ROLLBACK TO append_event_sp")
            raise  # Re-raise original exception unchanged
        else:
            # Release savepoint on success (not strictly required, but good hygiene)
            self.conn.execute("RELEASE append_event_sp")

        return event_id

    # Lineage & graph

    def insert_lineage(self, child_id: str, parent_id: str) -> None:
        """Insert lineage edge (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO lineage(child_id,parent_id) VALUES (?,?)",
            (child_id, parent_id)
        )

    def insert_graph_edge(self, source_id: str, target_id: str,
                          edge_type: str) -> None:
        """Insert graph edge (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO graph_edge(source_id,target_id,edge_type) VALUES (?,?,?)",
            (source_id, target_id, edge_type)
        )

    def insert_legacy_parent(self, child_id: str, parent_id: Optional[str] = None,
                             edge_type: Optional[str] = None) -> None:
        """Insert legacy parent (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO legacy_parent(child_id,parent_id,edge_type) VALUES (?,?,?)",
            (child_id, parent_id, edge_type)
        )

    def insert_edge_artifact(self, source_id: str, target_id: str, edge_type: str,
                             ordinal: int, sha256: str, role: str) -> None:
        """Insert edge artifact (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO edge_artifact(source_id,target_id,edge_type,ordinal,sha256,role) "
            "VALUES (?,?,?,?,?,?)",
            (source_id, target_id, edge_type, ordinal, sha256, role)
        )

    # Frontier & decisions

    def insert_frontier_gate(self, node_id: str, reason: str) -> None:
        """Insert frontier gate (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO frontier_gate(node_id,reason) VALUES (?,?)",
            (node_id, reason)
        )

    def ensure_decision_code(self, reason_code: str, allowed: int) -> None:
        """Idempotent insert decision_code. allowed: 0 or 1."""
        self.conn.execute(
            "INSERT OR IGNORE INTO decision_code(reason_code,allowed) VALUES (?,?)",
            (reason_code, allowed)
        )

    def insert_decision(self, decision_id: str, request_id: str, reason_code: str,
                        reason: Optional[str] = None, policy_version: str = "",
                        created_at: str = "") -> None:
        """Insert decision (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO decision(decision_id,request_id,reason_code,reason,"
            "policy_version,created_at) VALUES (?,?,?,?,?,?)",
            (decision_id, request_id, reason_code, reason, policy_version, created_at)
        )

    def insert_decision_snapshot(self, decision_id: str, snapshot_hash: str) -> None:
        """Insert decision_snapshot (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO decision_snapshot(decision_id,snapshot_hash) VALUES (?,?)",
            (decision_id, snapshot_hash)
        )

    def insert_decision_rule(self, decision_id: str, ordinal: int, rule_id: str) -> None:
        """Insert decision_rule (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO decision_rule(decision_id,ordinal,rule_id) VALUES (?,?,?)",
            (decision_id, ordinal, rule_id)
        )

    def insert_decision_identity(self, decision_id: str, authenticated_sender_id: str,
                                 recipient_id: str) -> None:
        """Insert decision_identity (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO decision_identity(decision_id,authenticated_sender_id,recipient_id) "
            "VALUES (?,?,?)",
            (decision_id, authenticated_sender_id, recipient_id)
        )

    # Reservations, replay, control

    def insert_reservation(self, request_id: str, calls: int, seconds: float,
                           released: int, created_at: str) -> None:
        """Insert reservation (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO reservation(request_id,calls,seconds,released,created_at) "
            "VALUES (?,?,?,?,?)",
            (request_id, calls, seconds, released, created_at)
        )

    def insert_replay(self, message_id: str, envelope_hash: str,
                      artifact_ref: Optional[str] = None, created_at: str = "") -> None:
        """Insert replay (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO replay(message_id,envelope_hash,artifact_ref,created_at) "
            "VALUES (?,?,?,?)",
            (message_id, envelope_hash, artifact_ref, created_at)
        )

    def insert_cancellation(self, run_id: str, at: str) -> None:
        """Insert cancellation (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO cancellation(run_id,at) VALUES (?,?)",
            (run_id, at)
        )

    def insert_lease(self, workspace_key: str, run_id: str, acquired_at: str) -> None:
        """Insert lease (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO lease(workspace_key,run_id,acquired_at) VALUES (?,?,?)",
            (workspace_key, run_id, acquired_at)
        )

    # Envelope tables

    def insert_envelope_identity(self, envelope_hash: str) -> None:
        """Insert envelope_identity (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO envelope_identity(envelope_hash) VALUES (?)",
            (envelope_hash,)
        )

    def insert_envelope(self, envelope_hash: str, message_id: str, task_id: str,
                        parent_task_id: Optional[str], correlation_id: str, sender: str,
                        recipient: str, intent: str, operation: str, protocol: str,
                        schema_name: str, classification: str, created_at: str,
                        expires_at: Optional[str] = None, deadline: Optional[str] = None,
                        reply_to: Optional[str] = None,
                        payload_sha: Optional[str] = None) -> None:
        """Insert envelope (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO envelope(envelope_hash,message_id,task_id,parent_task_id,"
            "correlation_id,sender,recipient,intent,operation,protocol,schema_name,"
            "classification,created_at,expires_at,deadline,reply_to,payload_sha) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (envelope_hash, message_id, task_id, parent_task_id, correlation_id,
             sender, recipient, intent, operation, protocol, schema_name,
             classification, created_at, expires_at, deadline, reply_to, payload_sha)
        )

    def insert_envelope_artifact(self, envelope_hash: str, ordinal: int, sha256: str,
                                 kind: str) -> None:
        """Insert envelope_artifact (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO envelope_artifact(envelope_hash,ordinal,sha256,kind) "
            "VALUES (?,?,?,?)",
            (envelope_hash, ordinal, sha256, kind)
        )

    def insert_envelope_field(self, envelope_hash: str, section: str, pointer: str,
                              type_: str, value: Optional[str] = None) -> None:
        """Insert envelope_field (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO envelope_field(envelope_hash,section,pointer,type,value) "
            "VALUES (?,?,?,?,?)",
            (envelope_hash, section, pointer, type_, value)
        )

    # Node artifacts

    def insert_node_artifact(self, node_id: str, sha256: str, role: str) -> None:
        """Insert node_artifact (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO node_artifact(node_id,sha256,role) VALUES (?,?,?)",
            (node_id, sha256, role)
        )

    # Approvals

    def insert_approval(self, approval_id: str, run_id: str, requester: str,
                        action: str, resource: str, artifact_hash: str, risk: str,
                        expires_at: str, approver: Optional[str] = None,
                        decision: Optional[str] = None,
                        decided_at: Optional[str] = None) -> None:
        """Insert approval (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO approval(approval_id,run_id,requester,action,resource,"
            "artifact_hash,risk,expires_at,approver,decision,decided_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (approval_id, run_id, requester, action, resource, artifact_hash, risk,
             expires_at, approver, decision, decided_at)
        )

    def insert_approval_rule(self, approval_id: str, ordinal: int, rule_id: str) -> None:
        """Insert approval_rule (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO approval_rule(approval_id,ordinal,rule_id) VALUES (?,?,?)",
            (approval_id, ordinal, rule_id)
        )

    # Import tables

    def insert_import_source(self, source_id: str, kind: str, source_sha: str) -> None:
        """Insert import_source (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO import_source(source_id,kind,source_sha) VALUES (?,?,?)",
            (source_id, kind, source_sha)
        )

    def insert_import_issue(self, source_id: str, record_no: int, code: str,
                            detail: Optional[str] = None) -> None:
        """Insert import_issue (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO import_issue(source_id,record_no,code,detail) VALUES (?,?,?,?)",
            (source_id, record_no, code, detail)
        )

    # Governance tables

    def ensure_governance_document(self, sha256: str, governance_version: str,
                                   policy_version: str) -> None:
        """Idempotent insert governance_document with version metadata.

        Args: sha256 (governance_sha), governance_version, policy_version (both required).
        Raises: IntegrityError on malformed input.
        """
        self.conn.execute(
            "INSERT OR IGNORE INTO governance_document(governance_sha,governance_version,"
            "policy_version) VALUES (?,?,?)",
            (sha256, governance_version, policy_version)
        )

    def insert_snapshot(self, snapshot_hash: str, governance_sha: str, protocols_sha: str,
                        routing_sha: str) -> None:
        """Insert snapshot (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO snapshot(snapshot_hash,governance_sha,protocols_sha,routing_sha) "
            "VALUES (?,?,?,?)",
            (snapshot_hash, governance_sha, protocols_sha, routing_sha)
        )

    def insert_agent(self, snapshot_hash: str, agent_id: str, name: str, type_: str,
                     enabled: int, clearance: str, max_depth: Optional[int] = None,
                     runtime: Optional[str] = None, endpoint: Optional[str] = None,
                     created_date: Optional[str] = None) -> None:
        """Insert agent (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO agent(snapshot_hash,agent_id,name,type,enabled,clearance,"
            "max_depth,runtime,endpoint,created_date) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (snapshot_hash, agent_id, name, type_, enabled, clearance, max_depth,
             runtime, endpoint, created_date)
        )

    def insert_capability(self, snapshot_hash: str, capability_id: str) -> None:
        """Insert capability (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO capability(snapshot_hash,capability_id) VALUES (?,?)",
            (snapshot_hash, capability_id)
        )

    def insert_agent_capability(self, snapshot_hash: str, agent_id: str,
                                capability_id: str) -> None:
        """Insert agent_capability (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO agent_capability(snapshot_hash,agent_id,capability_id) "
            "VALUES (?,?,?)",
            (snapshot_hash, agent_id, capability_id)
        )

    def insert_relationship(self, snapshot_hash: str, source_id: str, target_id: str,
                            relationship_type: str, max_depth: Optional[int] = None,
                            requires_approval: int = 0) -> None:
        """Insert relationship (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO relationship(snapshot_hash,source_id,target_id,"
            "relationship_type,max_depth,requires_approval) VALUES (?,?,?,?,?,?)",
            (snapshot_hash, source_id, target_id, relationship_type, max_depth,
             requires_approval)
        )

    def insert_relationship_param(self, snapshot_hash: str, source_id: str, target_id: str,
                                  relationship_type: str, ordinal: int, value: str) -> None:
        """Insert relationship_param (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO relationship_param(snapshot_hash,source_id,target_id,"
            "relationship_type,ordinal,value) VALUES (?,?,?,?,?,?)",
            (snapshot_hash, source_id, target_id, relationship_type, ordinal, value)
        )

    def insert_run_budget(self, run_id: str, max_calls: Optional[int] = None,
                          max_seconds: Optional[float] = None) -> None:
        """Insert run_budget (fact table, non-idempotent). Raises IntegrityError on duplicate."""
        self.conn.execute(
            "INSERT INTO run_budget(run_id,max_calls,max_seconds) VALUES (?,?,?)",
            (run_id, max_calls, max_seconds)
        )
