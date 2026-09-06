#!/usr/bin/env python3
"""Migrate existing JSONL ledger + control.sqlite to 3NF store. Idempotent.

CLI: python3 tools/migrate_to_3nf.py <workspace> [--db PATH] [--dry-run]
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

# Add repo root to path so workerbees can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

def sha256_file(path: Path) -> str:
    """Compute SHA256 of file."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def migrate_ledger(workspace: Path, store, source_id: str, dry_run: bool = False) -> dict:
    """Migrate JSONL ledger to 3NF store. Idempotent. Returns counts."""
    from workerbees import ledger as ledger_module
    import sqlite3

    ledger = ledger_module.load(workspace)
    counts = {
        "run": 0, "family": 0, "request": 0, "node": 0, "node_event": 0,
        "lineage": 0, "graph_edge": 0, "legacy_parent": 0,
        "skipped_run": 0, "skipped_family": 0, "skipped_request": 0,
        "skipped_node": 0, "skipped_node_event": 0, "skipped_lineage": 0,
        "skipped_graph_edge": 0, "skipped_legacy_parent": 0,
        "issues": 0
    }

    if dry_run:
        return counts

    try:
        # Process each node
        now = ledger_module._now_iso()

        for node_id, node in ledger.nodes.items():
            # Ensure run exists
            try:
                store.insert_run(node.run_id or f"run-{node_id}", now)
                counts["run"] += 1
            except sqlite3.IntegrityError:
                counts["skipped_run"] += 1

            # Ensure family exists (synthetic per run)
            run_id = node.run_id or f"run-{node_id}"
            family_id = f"synthetic-{run_id}"
            try:
                store.insert_family(family_id, run_id, label=None)
                counts["family"] += 1
            except sqlite3.IntegrityError:
                counts["skipped_family"] += 1

            # Ensure request exists (request_id == node_id)
            try:
                store.insert_request(node_id, family_id, envelope_hash=None)
                counts["request"] += 1
            except sqlite3.IntegrityError:
                counts["skipped_request"] += 1

            # Ensure provider and model
            if node.provider:
                store.ensure_provider(node.provider)
            if node.model:
                store.ensure_model(node.model, vendor_id=None)

            # Create route
            route_id = None
            if node.provider and node.model:
                try:
                    route_id = store.ensure_route(node.provider, f"dispatch-{node.task}", node.model)
                except (sqlite3.IntegrityError, Exception):
                    pass

            # Insert node
            try:
                store.insert_node(node_id, route_id=route_id, tier=node.tier, task=node.task,
                                created_at=node.timestamp or now)
                counts["node"] += 1
            except sqlite3.IntegrityError:
                counts["skipped_node"] += 1

            # Append the terminal event and its observed usage.
            try:
                usage = None
                if node.seconds is not None or node.subscription_calls is not None:
                    usage = {
                        "seconds": node.seconds,
                        "subscription_calls": node.subscription_calls,
                    }
                store.append_event(node_id, node.status, node.timestamp or now, usage=usage)
                counts["node_event"] += 1
            except sqlite3.IntegrityError:
                counts["skipped_node_event"] += 1

            # Write lineage (parent-child)
            if node.parent_id:
                try:
                    store.insert_lineage(node_id, node.parent_id)
                    counts["lineage"] += 1
                except sqlite3.IntegrityError:
                    counts["skipped_lineage"] += 1

            # Write graph edge
            if node.edge_type and node.parent_id:
                try:
                    store.insert_graph_edge(node_id, node.parent_id, node.edge_type)
                    counts["graph_edge"] += 1
                except sqlite3.IntegrityError:
                    counts["skipped_graph_edge"] += 1

            # Write legacy_parent (002 projection: nullable parent, including probes)
            try:
                store.insert_legacy_parent(node_id, node.parent_id, node.edge_type)
                counts["legacy_parent"] += 1
            except sqlite3.IntegrityError:
                counts["skipped_legacy_parent"] += 1

        store.conn.commit()
    except Exception as e:
        store.conn.rollback()
        store.insert_import_issue(source_id, -1, "ledger_migration_error", str(e))
        counts["issues"] += 1

    return counts

def migrate_control(workspace: Path, store, source_id: str, dry_run: bool = False) -> dict:
    """Migrate control.sqlite to 3NF store. Idempotent. Returns counts."""
    import sqlite3

    counts = {
        "decision": 0, "decision_code": 0, "reservation": 0, "replay": 0,
        "cancellation": 0, "lease": 0, "approval": 0,
        "skipped_decision": 0, "skipped_decision_code": 0, "skipped_reservation": 0,
        "skipped_replay": 0, "skipped_cancellation": 0, "skipped_lease": 0,
        "skipped_approval": 0,
        "issues": 0
    }

    if dry_run:
        return counts

    control_db = workspace / ".workerbees" / "control.sqlite"
    if not control_db.exists():
        return counts

    try:
        with sqlite3.connect(str(control_db)) as ctrl_conn:
            ctrl_conn.row_factory = sqlite3.Row

            # Migrate decisions
            try:
                for row in ctrl_conn.execute("SELECT * FROM decisions").fetchall():
                    try:
                        store.ensure_decision_code(row["reason_code"] or "unknown", 1)
                        counts["decision_code"] += 1
                    except sqlite3.IntegrityError:
                        counts["skipped_decision_code"] += 1

                    try:
                        store.insert_decision(
                            row["decision_id"], row["node_id"], row["reason_code"] or "unknown",
                            reason=None, policy_version=row["policy_version"] or "",
                            created_at=row["created_at"] or ""
                        )
                        counts["decision"] += 1
                    except sqlite3.IntegrityError:
                        counts["skipped_decision"] += 1
            except (sqlite3.OperationalError, Exception):
                pass

            # Migrate reservations
            try:
                for row in ctrl_conn.execute("SELECT * FROM reservations").fetchall():
                    try:
                        store.insert_reservation(
                            row["node_id"], row["calls"], row["seconds"],
                            row["released"], row["created_at"]
                        )
                        counts["reservation"] += 1
                    except sqlite3.IntegrityError:
                        counts["skipped_reservation"] += 1
            except (sqlite3.OperationalError, Exception):
                pass

            # Migrate replay
            try:
                for row in ctrl_conn.execute("SELECT * FROM replay_keys").fetchall():
                    try:
                        store.insert_replay(
                            row["message_id"], row["envelope_hash"],
                            row["artifact_ref"], row["created_at"]
                        )
                        counts["replay"] += 1
                    except sqlite3.IntegrityError:
                        counts["skipped_replay"] += 1
            except (sqlite3.OperationalError, Exception):
                pass

            # Migrate cancellations
            try:
                for row in ctrl_conn.execute("SELECT * FROM cancellations").fetchall():
                    try:
                        store.insert_cancellation(row["run_id"], row["at"])
                        counts["cancellation"] += 1
                    except sqlite3.IntegrityError:
                        counts["skipped_cancellation"] += 1
            except (sqlite3.OperationalError, Exception):
                pass

            # Migrate run_lease
            try:
                for row in ctrl_conn.execute("SELECT * FROM run_lease").fetchall():
                    try:
                        store.insert_lease(row["workspace_key"], row["run_id"], row["acquired_at"])
                        counts["lease"] += 1
                    except sqlite3.IntegrityError:
                        counts["skipped_lease"] += 1
            except (sqlite3.OperationalError, Exception):
                pass

            # Migrate approvals
            try:
                for row in ctrl_conn.execute("SELECT * FROM approvals").fetchall():
                    try:
                        store.insert_approval(
                            row["approval_id"], row["run_id"], row["requester"],
                            row["action"], row["resource"], row["artifact_hash"],
                            row["risk"], row["expires_at"], row["approver"],
                            row["decision"], row["decided_at"]
                        )
                        counts["approval"] += 1
                    except sqlite3.IntegrityError:
                        counts["skipped_approval"] += 1
            except (sqlite3.OperationalError, Exception):
                pass

        store.conn.commit()
    except Exception as e:
        store.conn.rollback()
        store.insert_import_issue(source_id, -1, "control_migration_error", str(e))
        counts["issues"] += 1

    return counts

def main():
    parser = argparse.ArgumentParser(description="Migrate JSONL ledger + control.sqlite to 3NF store")
    parser.add_argument("workspace", type=Path, help="Workspace path")
    parser.add_argument("--db", type=Path, help="Store DB path (default: <workspace>/.workerbees/workerbees.db)")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    db_path = (args.db.resolve() if args.db else workspace / ".workerbees" / "workerbees.db")
    if not workspace.exists() and args.db is None:
        print("ERROR: missing workspace requires --db so the import issue can be recorded", file=sys.stderr)
        sys.exit(2)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Compute source SHA
    ledger_file = workspace / ".workerbees" / "ledger.jsonl"
    control_file = workspace / ".workerbees" / "control.sqlite"

    ledger_sha = sha256_file(ledger_file) if ledger_file.exists() else "nosource"
    control_sha = sha256_file(control_file) if control_file.exists() else "nosource"
    combined_sha = hashlib.sha256((ledger_sha + control_sha).encode()).hexdigest()
    source_id = combined_sha[:16]

    # Create or ensure artifact entry
    from workerbees.store import Store

    with Store(db_path) as store:
        if not workspace.exists():
            store.ensure_artifact(combined_sha, 0)
            store.insert_import_source(source_id, "ledger+control", combined_sha)
            store.insert_import_issue(source_id, 0, "workspace_not_found", str(workspace))
            store.conn.commit()
            print("Migration Report")
            print("=" * 50)
            print(f"Workspace: {workspace}")
            print(f"Store DB: {db_path}")
            print(f"Source ID: {source_id}")
            print("Issues recorded: 1")
            return
        # Check if already migrated before doing anything
        try:
            existing = store.conn.execute(
                "SELECT COUNT(*) as cnt FROM import_source WHERE source_id=?", (source_id,)
            ).fetchone()
            if existing and existing[0] > 0:
                # Already migrated, report summary and exit
                print("Migration Report")
                print("=" * 50)
                print(f"Workspace: {workspace}")
                print(f"Store DB: {db_path}")
                print(f"Source ID: {source_id}")
                print()
                print("Already migrated (skipping).")
                print()
                print(f"Total written: 0")
                print(f"Total skipped (idempotent): 0")
                print(f"Issues recorded: 0")
                return
        except (sqlite3.OperationalError, Exception):
            pass  # Table may not exist yet, continue

        # Record import source
        try:
            store.ensure_artifact(combined_sha, 0)
            store.insert_import_source(source_id, "ledger+control", combined_sha)
        except sqlite3.IntegrityError:
            pass  # Already recorded

        store.conn.commit()

        # Migrate ledger
        counts_ledger = migrate_ledger(workspace, store, source_id, args.dry_run)

        # Migrate control.sqlite
        counts_control = migrate_control(workspace, store, source_id, args.dry_run)

        # Combine counts
        all_counts = {**counts_ledger, **counts_control}

        # Report
        print("Migration Report")
        print("=" * 50)
        if args.dry_run:
            print("(dry-run: no writes)")
        print(f"Workspace: {workspace}")
        print(f"Store DB: {db_path}")
        print(f"Source ID: {source_id}")
        print()
        print("Ledger migration:")
        for k, v in counts_ledger.items():
            if not k.startswith("skipped") and v > 0:
                print(f"  {k}: {v}")
        for k, v in counts_ledger.items():
            if k.startswith("skipped") and v > 0:
                print(f"  {k}: {v}")
        print()
        print("Control migration:")
        for k, v in counts_control.items():
            if not k.startswith("skipped") and v > 0:
                print(f"  {k}: {v}")
        for k, v in counts_control.items():
            if k.startswith("skipped") and v > 0:
                print(f"  {k}: {v}")

        written = sum(v for k, v in all_counts.items() if not k.startswith("skipped") and "issue" not in k)
        skipped = sum(v for k, v in all_counts.items() if k.startswith("skipped"))
        issues = all_counts.get("issues", 0)

        print()
        print(f"Total written: {written}")
        print(f"Total skipped (idempotent): {skipped}")
        print(f"Issues recorded: {issues}")

if __name__ == "__main__":
    main()
