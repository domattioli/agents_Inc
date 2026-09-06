#!/usr/bin/env python3
"""Governance Task 10: end-to-end governance check."""
import os, sys, json, sqlite3, tempfile, shutil
from pathlib import Path
from datetime import datetime
from workerbees.registry import Registry
from workerbees.gateway import Gateway
from workerbees.envelope import Envelope
from workerbees.router import pick_model
from workerbees.adapters import base
from workerbees.ledger import load as load_ledger, to_mermaid

def fake_run_worker(cmd, stdin_text, cwd=None, timeout=300):
    return base.WorkerResult("returned", "PONG", "", 0)

def run_demo(use_fake=False):
    original_mode = os.environ.get("WORKERBEES_GOVERNANCE")
    os.environ["WORKERBEES_GOVERNANCE"] = "enforce"
    tmpdir = Path(tempfile.mkdtemp(prefix="governance_demo_"))
    try:
        registry = Registry.load("workerbees")
        gateway = Gateway(workspace=tmpdir, registry=registry, mode="enforce")
        runner = fake_run_worker if use_fake else base.run_worker
        results = {}

        # Case A: Allowed (supervisor→worker, extract)
        print("=" * 60 + "\nCASE A: ALLOWED (supervisor→worker, extract)\n" + "=" * 60)
        env_a = Envelope(
            message_id="msg-allow-001", task_id="task-allow-001", parent_task_id=None,
            correlation_id="corr-allow-001", sender="agent-supervisor-01",
            recipient="agent-worker-01", intent="extract", operation="request",
            protocol="v1", schema="request_v1", payload={"prompt":"reply exactly PONG"},
            data_classification="internal", created_at=datetime.utcnow().isoformat()+"Z"
        )
        result_a = gateway.dispatch(env_a, context={"authenticated_sender":env_a.sender},
                                    runner=runner, route=pick_model("extract","cheap",{"claude"},False))
        results["allowed"] = {
            "decision_id": result_a.decision.decision_id, "allowed": result_a.decision.allowed,
            "reason_code": result_a.decision.reason_code, "reason": result_a.decision.reason,
            "policy_version": result_a.decision.policy_version, "status": result_a.status,
            "node_id": result_a.node_id, "decision_recorded": result_a.decision_recorded
        }
        print(f"Decision: {json.dumps(results['allowed'], indent=2)}")
        print(f"Worker result: {result_a.worker_result}")

        # Case B: Denied (worker→reviewer, no edge exists)
        print("\n" + "=" * 60 + "\nCASE B: DENIED (worker→reviewer, no edge)\n" + "=" * 60)
        env_b = Envelope(
            message_id="msg-deny-001", task_id="task-deny-001", parent_task_id=None,
            correlation_id="corr-deny-001", sender="agent-worker-01",
            recipient="agent-reviewer-01", intent="review", operation="request",
            protocol="v1", schema="request_v1", payload={"prompt":"reply exactly PONG"},
            data_classification="internal", created_at=datetime.utcnow().isoformat()+"Z"
        )
        result_b = gateway.dispatch(env_b, context={"authenticated_sender":env_b.sender},
                                    runner=runner, route=pick_model("review","cheap",{"claude"},False))
        results["denied"] = {
            "decision_id": result_b.decision.decision_id, "allowed": result_b.decision.allowed,
            "reason_code": result_b.decision.reason_code, "reason": result_b.decision.reason,
            "policy_version": result_b.decision.policy_version, "status": result_b.status,
            "node_id": result_b.node_id, "decision_recorded": result_b.decision_recorded
        }
        print(f"Decision: {json.dumps(results['denied'], indent=2)}")
        print(f"Worker result: {result_b.worker_result}")

        # Query control.sqlite
        print("\n" + "=" * 60 + "\nCONTROL.SQLITE DECISIONS\n" + "=" * 60)
        db_path = tmpdir / ".workerbees" / "control.sqlite"
        decisions_count = 0
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            decisions_count = conn.execute("SELECT COUNT(*) as cnt FROM decisions").fetchone()["cnt"]
            print(f"Total decisions recorded: {decisions_count}")
            for row in conn.execute("SELECT decision_id, allowed, reason_code FROM decisions ORDER BY created_at"):
                print(f"  {row['decision_id']}: allowed={row['allowed']}, reason={row['reason_code']}")
            conn.close()

        # Query ledger
        print("\n" + "=" * 60 + "\nLEDGER NODES AND MERMAID\n" + "=" * 60)
        ledger = load_ledger(tmpdir)
        print(f"Ledger nodes: {len(ledger.nodes)}")
        for node_id, node in ledger.nodes.items():
            print(f"  {node_id}: task={node.task}, status={node.status}, provider={node.provider}")
        print("\nMermaid diagram:")
        print(to_mermaid(ledger))

        print("\n" + "=" * 60 + "\nSUMMARY\n" + "=" * 60)
        print(f"Allowed case: {results['allowed']['allowed']}")
        print(f"Denied case: {results['denied']['allowed']}")
        print(f"Total decisions recorded: {decisions_count}")
        print(f"Ledger nodes: {len(ledger.nodes)}")

        return results, decisions_count, len(ledger.nodes)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        if original_mode: os.environ["WORKERBEES_GOVERNANCE"] = original_mode
        else: os.environ.pop("WORKERBEES_GOVERNANCE", None)

if __name__ == "__main__":
    run_demo("--fake" in sys.argv)
