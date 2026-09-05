"""Workspace-local control and audit state machine for SQLite decisions/budgets."""
from __future__ import annotations
import sqlite3, json, os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from workerbees.envelope import Decision

class ControlError(Exception):
    """Control layer error."""
    pass

class ReplayResult:
    def __init__(self, state: str, artifact_ref: Optional[str]=None, reason: str=""):
        self.state, self.artifact_ref, self.reason = state, artifact_ref, reason

class Control:
    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        self.db_path = self.workspace / ".workerbees" / "control.sqlite"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_tables()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _is_readonly_error(self, e: sqlite3.Error) -> bool:
        """Check if error is readonly/unable-to-open."""
        return isinstance(e, (sqlite3.OperationalError, sqlite3.DatabaseError)) and (
            "readonly" in str(e).lower() or "unable to open" in str(e).lower()
            or "permission denied" in str(e).lower() or "is not a directory" in str(e).lower()
        )

    def _parse_iso(self, s: str) -> datetime:
        """Parse ISO 8601 string, handling trailing Z."""
        return datetime.fromisoformat(s.replace('Z', '+00:00'))

    def _ensure_tables(self) -> None:
        try:
            with self._conn() as c:
                c.execute("CREATE TABLE IF NOT EXISTS decisions (decision_id TEXT PRIMARY KEY,run_id TEXT,node_id TEXT,envelope_hash TEXT,allowed INT,reason_code TEXT,policy_version TEXT,checked_rules TEXT,created_at TEXT)")
                c.execute("CREATE TABLE IF NOT EXISTS reservations (run_id TEXT,node_id TEXT,calls INT,seconds REAL,released INT DEFAULT 0,created_at TEXT,PRIMARY KEY(run_id,node_id))")
                c.execute("CREATE TABLE IF NOT EXISTS replay_keys (message_id TEXT PRIMARY KEY,envelope_hash TEXT,artifact_ref TEXT,created_at TEXT)")
                c.execute("CREATE TABLE IF NOT EXISTS cancellations (run_id TEXT PRIMARY KEY,at TEXT)")
                c.execute("CREATE TABLE IF NOT EXISTS run_lease (workspace_key TEXT PRIMARY KEY,run_id TEXT,acquired_at TEXT)")
                c.execute("CREATE TABLE IF NOT EXISTS approvals (approval_id TEXT PRIMARY KEY,run_id TEXT,requester TEXT,action TEXT,resource TEXT,artifact_hash TEXT,risk TEXT,rule_ids TEXT,expires_at TEXT,approver TEXT,decision TEXT,decided_at TEXT)")
        except sqlite3.Error:
            pass

    def record_decision(self, decision: Decision, run_id: str, node_id: str, envelope_hash: str) -> bool:
        try:
            rules = decision.checked_rules[:64] if decision.checked_rules else []
            rules = [r[:64] for r in rules]
            with self._conn() as c:
                c.execute("INSERT INTO decisions (decision_id,run_id,node_id,envelope_hash,allowed,reason_code,policy_version,checked_rules,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                         (decision.decision_id, run_id, node_id, envelope_hash, int(decision.allowed), decision.reason_code, decision.policy_version, json.dumps(rules), datetime.utcnow().isoformat() + "Z"))
            return True
        except sqlite3.Error as e:
            if self._is_readonly_error(e):
                return False
            raise ControlError(f"Failed to record decision: {e}")

    def reserve(self, run_id: str, node_id: str, calls: int=1, seconds: float=0.0) -> bool:
        if calls < 0 or seconds < 0:
            return False
        try:
            with self._conn() as c:
                c.execute("BEGIN IMMEDIATE")
                c.execute("INSERT INTO reservations (run_id,node_id,calls,seconds,created_at) VALUES (?,?,?,?,?)", (run_id, node_id, calls, seconds, datetime.utcnow().isoformat() + "Z"))
            return True
        except sqlite3.Error as e:
            if self._is_readonly_error(e):
                return False
            raise ControlError(f"Failed to reserve: {e}")

    def release(self, run_id: str, node_id: str) -> bool:
        try:
            with self._conn() as c:
                c.execute("BEGIN IMMEDIATE")
                c.execute("UPDATE reservations SET released=1 WHERE run_id=? AND node_id=?", (run_id, node_id))
            return True
        except sqlite3.Error:
            return False

    def used(self, run_id: str) -> Dict[str, Any]:
        try:
            with self._conn() as c:
                row = c.execute("SELECT SUM(calls) as total_calls, SUM(seconds) as total_seconds FROM reservations WHERE run_id=? AND released=0", (run_id,)).fetchone()
            return {"calls": row["total_calls"] or 0, "seconds": row["total_seconds"] or 0.0}
        except sqlite3.Error:
            return {"calls": 0, "seconds": 0.0}

    def check_replay(self, message_id: str, envelope_hash: str) -> ReplayResult:
        try:
            with self._conn() as c:
                row = c.execute("SELECT envelope_hash, artifact_ref FROM replay_keys WHERE message_id=?", (message_id,)).fetchone()
            if row is None:
                return ReplayResult(state="new")
            stored_hash = row["envelope_hash"]
            if stored_hash == envelope_hash:
                return ReplayResult(state="duplicate", artifact_ref=row["artifact_ref"], reason="Same message ID and hash")
            else:
                return ReplayResult(state="conflict", artifact_ref=row["artifact_ref"], reason="Same message ID but different envelope hash")
        except sqlite3.Error as e:
            if self._is_readonly_error(e):
                return ReplayResult(state="error", reason="Database error")
            raise ControlError(f"Failed to check replay: {e}")

    def store_artifact(self, message_id: str, envelope_hash: str, artifact_ref: str) -> bool:
        try:
            with self._conn() as c:
                c.execute("INSERT OR REPLACE INTO replay_keys (message_id,envelope_hash,artifact_ref,created_at) VALUES (?,?,?,?)", (message_id, envelope_hash, artifact_ref, datetime.utcnow().isoformat() + "Z"))
            return True
        except sqlite3.Error:
            return False

    def cancel(self, run_id: str) -> bool:
        try:
            with self._conn() as c:
                c.execute("INSERT OR REPLACE INTO cancellations (run_id,at) VALUES (?,?)", (run_id, datetime.utcnow().isoformat() + "Z"))
            return True
        except sqlite3.Error:
            return False

    def is_cancelled(self, run_id: str) -> bool:
        try:
            with self._conn() as c:
                exists = c.execute("SELECT 1 FROM cancellations WHERE run_id=?", (run_id,)).fetchone() is not None
            return exists
        except sqlite3.Error:
            return True

    def acquire_lease(self, run_id: str) -> bool:
        try:
            with self._conn() as c:
                c.execute("BEGIN IMMEDIATE")
                now = datetime.utcnow().isoformat() + "Z"
                workspace_key = "default"
                cur = c.execute("INSERT INTO run_lease (workspace_key,run_id,acquired_at) SELECT ?,?,? WHERE NOT EXISTS (SELECT 1 FROM run_lease WHERE workspace_key=?)", (workspace_key, run_id, now, workspace_key))
                if cur.rowcount == 0:
                    row = c.execute("SELECT run_id FROM run_lease WHERE workspace_key=?", (workspace_key,)).fetchone()
                    if row and row["run_id"] == run_id:
                        return True
                    return False
            return True
        except sqlite3.Error:
            return False

    def release_lease(self, run_id: str) -> bool:
        try:
            with self._conn() as c:
                c.execute("DELETE FROM run_lease WHERE run_id=?", (run_id,))
            return True
        except sqlite3.Error:
            return False

    def request_approval(self, run_id: str, requester: str, action: str, resource: str, artifact_hash: str, risk: str, rule_ids: list, expires_at: str) -> Optional[str]:
        try:
            import uuid
            approval_id = str(uuid.uuid4())
            with self._conn() as c:
                c.execute("INSERT INTO approvals (approval_id,run_id,requester,action,resource,artifact_hash,risk,rule_ids,expires_at) VALUES (?,?,?,?,?,?,?,?,?)",
                         (approval_id, run_id, requester, action[:256], resource[:256], artifact_hash, risk[:256], json.dumps(rule_ids), expires_at))
            return approval_id
        except sqlite3.Error as e:
            if self._is_readonly_error(e):
                return None
            raise ControlError(f"Failed to request approval: {e}")

    def decide_approval(self, approval_id: str, approver: str, decision: str, now: str) -> bool:
        try:
            with self._conn() as c:
                c.execute("BEGIN IMMEDIATE")
                row = c.execute("SELECT requester, expires_at, decision FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
                if not row:
                    return False
                if row["decision"] is not None:
                    return False
                if row["requester"].strip().casefold() == approver.strip().casefold():
                    return False
                now_dt = self._parse_iso(now)
                expires_dt = self._parse_iso(row["expires_at"])
                if now_dt > expires_dt:
                    return False
                c.execute("UPDATE approvals SET approver=?, decision=?, decided_at=? WHERE approval_id=?", (approver[:256], decision, now, approval_id))
            return True
        except sqlite3.Error as e:
            if self._is_readonly_error(e):
                return False
            raise ControlError(f"Failed to decide approval: {e}")

    def approval_status(self, approval_id: str) -> str:
        try:
            with self._conn() as c:
                row = c.execute("SELECT decision, expires_at FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
            if not row:
                return "unknown"
            if row["decision"]:
                return row["decision"]
            expires = self._parse_iso(row["expires_at"])
            now = datetime.utcnow().astimezone()
            if expires < now:
                return "expired"
            return "pending"
        except sqlite3.Error as e:
            if self._is_readonly_error(e):
                return "error"
            raise ControlError(f"Failed to check approval status: {e}")

    def approval_binds(self, approval_id: str, action: str, resource: str, artifact_hash: str, now: str) -> bool:
        try:
            with self._conn() as c:
                row = c.execute("SELECT action, resource, artifact_hash, decision, expires_at FROM approvals WHERE approval_id=?", (approval_id,)).fetchone()
            if not row or row["decision"] != "approved":
                return False
            now_dt = self._parse_iso(now)
            expires_dt = self._parse_iso(row["expires_at"])
            if now_dt > expires_dt:
                return False
            return row["action"] == action and row["resource"] == resource and row["artifact_hash"] == artifact_hash
        except sqlite3.Error as e:
            if self._is_readonly_error(e):
                return False
            raise ControlError(f"Failed to check approval binding: {e}")
