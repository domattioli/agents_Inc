"""Workspace-local control and audit state machine for SQLite decisions/budgets.

Dual-write mode: controlled by WORKERBEES_STORE env var (jsonl|sqlite|both, default both).
When jsonl: no store writes, no dual-write operations.
When sqlite: writes to normalized 3NF schema.
When both: writes to both control.sqlite and normalized schema.

All operations follow FR-008 (swallow store errors, never break caller).
"""
from __future__ import annotations
import sqlite3, json, os, uuid
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
                c.execute("CREATE TABLE IF NOT EXISTS decisions (decision_id TEXT PRIMARY KEY,run_id TEXT,node_id TEXT,envelope_hash TEXT,allowed INT,reason_code TEXT,policy_version TEXT,checked_rules TEXT,created_at TEXT,sender TEXT,recipient TEXT,operation TEXT)")
                c.execute("CREATE TABLE IF NOT EXISTS reservations (run_id TEXT,node_id TEXT,calls INT,seconds REAL,released INT DEFAULT 0,created_at TEXT,PRIMARY KEY(run_id,node_id))")
                c.execute("CREATE TABLE IF NOT EXISTS replay_keys (message_id TEXT PRIMARY KEY,envelope_hash TEXT,artifact_ref TEXT,created_at TEXT)")
                c.execute("CREATE TABLE IF NOT EXISTS cancellations (run_id TEXT PRIMARY KEY,at TEXT)")
                c.execute("CREATE TABLE IF NOT EXISTS run_lease (workspace_key TEXT PRIMARY KEY,run_id TEXT,acquired_at TEXT)")
                c.execute("CREATE TABLE IF NOT EXISTS run_budgets (run_id TEXT PRIMARY KEY,max_calls INT,max_seconds REAL,created_at TEXT)")
                c.execute("CREATE TABLE IF NOT EXISTS approvals (approval_id TEXT PRIMARY KEY,run_id TEXT,requester TEXT,action TEXT,resource TEXT,artifact_hash TEXT,risk TEXT,rule_ids TEXT,expires_at TEXT,approver TEXT,decision TEXT,decided_at TEXT)")
                cols = {r[1] for r in c.execute("PRAGMA table_info(decisions)")}
                for name in ("sender", "recipient", "operation"):
                    if name not in cols:
                        c.execute(f"ALTER TABLE decisions ADD COLUMN {name} TEXT")
        except sqlite3.Error:
            pass

    def record_decision(self, decision: Decision, run_id: str, node_id: str, envelope_hash: str,
                        sender: str = "", recipient: str = "", operation: str = "") -> bool:
        try:
            rules = decision.checked_rules[:64] if decision.checked_rules else []
            rules = [r[:64] for r in rules]
            with self._conn() as c:
                c.execute("INSERT OR REPLACE INTO decisions (decision_id,run_id,node_id,envelope_hash,allowed,reason_code,policy_version,checked_rules,created_at,sender,recipient,operation) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (decision.decision_id, run_id, node_id, envelope_hash, int(decision.allowed), decision.reason_code, decision.policy_version, json.dumps(rules), datetime.utcnow().isoformat() + "Z", sender, recipient, operation))

            # Dual-write to normalized schema
            store_mode = os.environ.get("WORKERBEES_STORE", "both").lower()
            if store_mode not in ("jsonl", "sqlite", "both"):
                raise ValueError(f"Invalid WORKERBEES_STORE value: {store_mode!r}")
            if store_mode in ("sqlite", "both"):
                try:
                    _dual_write_decision(self.workspace, decision, run_id, node_id, envelope_hash,
                                         sender, recipient)
                except Exception:
                    # Swallow store errors per FR-008
                    pass

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
                if not self._claim_run_for_reservation(c, run_id, node_id):
                    return False
                c.execute("INSERT INTO reservations (run_id,node_id,calls,seconds,created_at) VALUES (?,?,?,?,?)", (run_id, node_id, calls, seconds, datetime.utcnow().isoformat() + "Z"))

            # Dual-write to normalized schema
            store_mode = os.environ.get("WORKERBEES_STORE", "both").lower()
            if store_mode not in ("jsonl", "sqlite", "both"):
                raise ValueError(f"Invalid WORKERBEES_STORE value: {store_mode!r}")
            if store_mode in ("sqlite", "both"):
                try:
                    _dual_write_lease(self.workspace, "default", run_id)
                    _dual_write_reservation(self.workspace, run_id, node_id, calls, seconds)
                except Exception:
                    # Swallow store errors per FR-008
                    pass

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
                c.execute("DELETE FROM run_lease WHERE run_id=?", (run_id,))
            if _store_enabled():
                _dual_write_transition(self.workspace, lambda s: s.release_reservation(node_id))
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

    def commit_usage(self, run_id: str, node_id: str, seconds: float) -> bool:
        """Attach observed duration to the retained call reservation."""
        try:
            with self._conn() as c:
                c.execute("UPDATE reservations SET seconds=? WHERE run_id=? AND node_id=? AND released=0",
                          (max(0.0, seconds), run_id, node_id))
            if _store_enabled():
                _dual_write_transition(
                    self.workspace,
                    lambda s: s.conn.execute("UPDATE reservation SET seconds=? WHERE request_id=? AND released=0",
                                             (max(0.0, seconds), node_id)))
            return True
        except sqlite3.Error:
            return False

    def record_run_budget(self, run_id: str, budget: Dict[str, Any]) -> Dict[str, Any]:
        """Persist first declared run limit; return the durable value."""
        max_calls = budget.get("max_calls")
        max_seconds = budget.get("max_seconds")
        try:
            with self._conn() as c:
                c.execute("INSERT OR IGNORE INTO run_budgets(run_id,max_calls,max_seconds,created_at) VALUES (?,?,?,?)",
                          (run_id, max_calls, max_seconds, datetime.utcnow().isoformat() + "Z"))
                row = c.execute("SELECT max_calls,max_seconds FROM run_budgets WHERE run_id=?", (run_id,)).fetchone()
            durable = {"max_calls": row["max_calls"], "max_seconds": row["max_seconds"]}
            if _store_enabled():
                _dual_write_run_budget(self.workspace, run_id, durable)
            return durable
        except sqlite3.Error as e:
            raise ControlError(f"Failed to record run budget: {e}")

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

    def claim_replay(self, message_id: str, envelope_hash: str) -> ReplayResult:
        """Atomically claim a message before invocation."""
        try:
            with self._conn() as c:
                c.execute("BEGIN IMMEDIATE")
                row = c.execute("SELECT envelope_hash,artifact_ref FROM replay_keys WHERE message_id=?", (message_id,)).fetchone()
                if row:
                    state = "duplicate" if row["envelope_hash"] == envelope_hash else "conflict"
                    return ReplayResult(state, row["artifact_ref"], "Message already claimed")
                c.execute("INSERT INTO replay_keys(message_id,envelope_hash,artifact_ref,created_at) VALUES (?,?,?,?)",
                          (message_id, envelope_hash, None, datetime.utcnow().isoformat() + "Z"))
            return ReplayResult("new")
        except sqlite3.Error as e:
            if self._is_readonly_error(e):
                return ReplayResult("error", reason="Database error")
            raise ControlError(f"Failed to claim replay key: {e}")

    def reserve_bounded(self, run_id: str, node_id: str, calls: int, seconds: float,
                        max_calls: Optional[int], max_seconds: Optional[float]) -> bool:
        try:
            with self._conn() as c:
                c.execute("BEGIN IMMEDIATE")
                if not self._claim_run_for_reservation(c, run_id, node_id):
                    return False
                row = c.execute("SELECT COALESCE(SUM(calls),0),COALESCE(SUM(seconds),0) FROM reservations WHERE run_id=? AND released=0", (run_id,)).fetchone()
                if max_calls is not None and row[0] + calls > max_calls:
                    c.execute("DELETE FROM run_lease WHERE run_id=?", (run_id,))
                    return False
                if max_seconds is not None and row[1] + seconds > max_seconds:
                    c.execute("DELETE FROM run_lease WHERE run_id=?", (run_id,))
                    return False
                c.execute("INSERT INTO reservations(run_id,node_id,calls,seconds,created_at) VALUES (?,?,?,?,?)",
                          (run_id, node_id, calls, seconds, datetime.utcnow().isoformat() + "Z"))
            return True
        except sqlite3.Error as e:
            raise ControlError(f"Failed bounded reservation: {e}")

    def _claim_run_for_reservation(self, c: sqlite3.Connection, run_id: str, node_id: str) -> bool:
        """Claim the workspace call slot. Busy attempts are denied and audited atomically."""
        now = datetime.utcnow().isoformat() + "Z"
        cur = c.execute("INSERT INTO run_lease(workspace_key,run_id,acquired_at) "
                        "SELECT 'default',?,? WHERE NOT EXISTS "
                        "(SELECT 1 FROM run_lease WHERE workspace_key='default')", (run_id, now))
        if cur.rowcount:
            return True
        c.execute("INSERT INTO decisions(decision_id,run_id,node_id,envelope_hash,allowed,reason_code,"
                  "policy_version,checked_rules,created_at,sender,recipient,operation) "
                  "VALUES (?,?,?,?,0,'run_busy','runtime',?,?,'','','reserve')",
                  (uuid.uuid4().hex, run_id, node_id, "", json.dumps(["run_lease"]), now))
        return False

    def store_artifact(self, message_id: str, envelope_hash: str, artifact_ref: str) -> bool:
        try:
            with self._conn() as c:
                c.execute("INSERT INTO replay_keys(message_id,envelope_hash,artifact_ref,created_at) VALUES (?,?,?,?) "
                          "ON CONFLICT(message_id) DO UPDATE SET artifact_ref=excluded.artifact_ref "
                          "WHERE replay_keys.envelope_hash=excluded.envelope_hash",
                          (message_id, envelope_hash, artifact_ref, datetime.utcnow().isoformat() + "Z"))

            # Dual-write to normalized schema
            store_mode = os.environ.get("WORKERBEES_STORE", "both").lower()
            if store_mode not in ("jsonl", "sqlite", "both"):
                raise ValueError(f"Invalid WORKERBEES_STORE value: {store_mode!r}")
            if store_mode in ("sqlite", "both"):
                try:
                    _dual_write_replay(self.workspace, message_id, envelope_hash, artifact_ref)
                except Exception:
                    # Swallow store errors per FR-008
                    pass

            return True
        except sqlite3.Error:
            return False

    def cancel(self, run_id: str) -> bool:
        try:
            with self._conn() as c:
                c.execute("INSERT OR REPLACE INTO cancellations (run_id,at) VALUES (?,?)", (run_id, datetime.utcnow().isoformat() + "Z"))

            # Dual-write to normalized schema
            store_mode = os.environ.get("WORKERBEES_STORE", "both").lower()
            if store_mode not in ("jsonl", "sqlite", "both"):
                raise ValueError(f"Invalid WORKERBEES_STORE value: {store_mode!r}")
            if store_mode in ("sqlite", "both"):
                try:
                    _dual_write_cancellation(self.workspace, run_id)
                except Exception:
                    # Swallow store errors per FR-008
                    pass

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
                        result = True
                    else:
                        return False
                else:
                    result = True

            # Dual-write to normalized schema
            store_mode = os.environ.get("WORKERBEES_STORE", "both").lower()
            if store_mode not in ("jsonl", "sqlite", "both"):
                raise ValueError(f"Invalid WORKERBEES_STORE value: {store_mode!r}")
            if store_mode in ("sqlite", "both"):
                try:
                    _dual_write_lease(self.workspace, "default", run_id)
                except Exception:
                    # Swallow store errors per FR-008
                    pass

            return result
        except sqlite3.Error:
            return False

    def release_lease(self, run_id: str) -> bool:
        try:
            with self._conn() as c:
                c.execute("DELETE FROM run_lease WHERE run_id=?", (run_id,))
            if _store_enabled():
                _dual_write_transition(self.workspace, lambda s: s.release_lease("default", run_id))
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

            # Dual-write to normalized schema
            store_mode = os.environ.get("WORKERBEES_STORE", "both").lower()
            if store_mode not in ("jsonl", "sqlite", "both"):
                raise ValueError(f"Invalid WORKERBEES_STORE value: {store_mode!r}")
            if store_mode in ("sqlite", "both"):
                try:
                    _dual_write_approval(self.workspace, approval_id, run_id, requester, action,
                                        resource, artifact_hash, risk, rule_ids, expires_at)
                except Exception:
                    # Swallow store errors per FR-008
                    pass

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
            if _store_enabled():
                _dual_write_transition(
                    self.workspace,
                    lambda s: s.decide_approval(approval_id, approver[:256], decision, now))
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


# Dual-write helpers (all swallow errors per FR-008)

def _store_enabled() -> bool:
    mode = os.environ.get("WORKERBEES_STORE", "both").lower()
    if mode not in ("jsonl", "sqlite", "both"):
        raise ValueError(f"Invalid WORKERBEES_STORE value: {mode!r}")
    return mode in ("sqlite", "both")


def _dual_write_transition(workspace: Path, operation) -> None:
    from workerbees.store import Store
    with Store(workspace / ".workerbees" / "workerbees.db") as store:
        operation(store)
        store.conn.commit()


def _ensure_normalized_request(store, run_id: str, node_id: str, now: str) -> None:
    family_id = f"synthetic-{run_id}"
    for operation in (
        lambda: store.insert_run(run_id, now),
        lambda: store.insert_family(family_id, run_id, label=None),
        lambda: store.insert_request(node_id, family_id, envelope_hash=None),
    ):
        try:
            operation()
        except sqlite3.IntegrityError:
            pass


def _dual_write_decision(workspace: Path, decision: Decision, run_id: str, node_id: str,
                         envelope_hash: str, sender: str, recipient: str) -> None:
    """Write decision to normalized 3NF schema. Idempotent via IntegrityError catch.

    Synthetic family: family_id = f"synthetic-{run_id}", request_id == node_id.
    Raises on real errors; swallowed by record_decision per FR-008.
    """
    from workerbees.store import Store

    d = workspace / ".workerbees"
    db_path = d / "workerbees.db"

    with Store(db_path) as store:
        now = datetime.utcnow().isoformat() + "Z"
        _ensure_normalized_request(store, run_id, node_id, now)
        rules = decision.checked_rules[:64] if decision.checked_rules else []
        rules = [r[:64] for r in rules]

        try:
            store.ensure_decision_code(decision.reason_code, int(decision.allowed))
        except sqlite3.IntegrityError:
            pass

        try:
            store.insert_decision(decision.decision_id, node_id, decision.reason_code,
                                 reason=None, policy_version=decision.policy_version,
                                 created_at=now)
        except sqlite3.IntegrityError:
            pass

        for ordinal, rule in enumerate(rules):
            try:
                store.insert_decision_rule(decision.decision_id, ordinal, rule)
            except sqlite3.IntegrityError:
                pass
        if sender and recipient:
            try:
                store.insert_decision_identity(decision.decision_id, sender, recipient)
            except sqlite3.IntegrityError:
                pass

        # Commit changes
        store.conn.commit()


def _dual_write_reservation(workspace: Path, run_id: str, node_id: str, calls: int, seconds: float) -> None:
    """Write reservation to normalized 3NF schema. Idempotent via IntegrityError catch.

    Synthetic family: family_id = f"synthetic-{run_id}", request_id == node_id.
    Raises on real errors; swallowed by reserve per FR-008.
    """
    from workerbees.store import Store

    d = workspace / ".workerbees"
    db_path = d / "workerbees.db"

    with Store(db_path) as store:
        family_id = f"synthetic-{run_id}"
        now = datetime.utcnow().isoformat() + "Z"

        try:
            # Ensure run/family/request exist
            store.insert_run(run_id, now)
        except sqlite3.IntegrityError:
            pass

        try:
            store.insert_family(family_id, run_id, label=None)
        except sqlite3.IntegrityError:
            pass

        try:
            store.insert_request(node_id, family_id, envelope_hash=None)
        except sqlite3.IntegrityError:
            pass

        try:
            store.insert_reservation(node_id, calls, seconds, released=0, created_at=now)
        except sqlite3.IntegrityError:
            pass

        # Commit changes
        store.conn.commit()


def _dual_write_run_budget(workspace: Path, run_id: str, budget: Dict[str, Any]) -> None:
    """Mirror the immutable per-run budget into canonical 3NF storage."""
    from workerbees.store import Store

    db_path = workspace / ".workerbees" / "workerbees.db"
    with Store(db_path) as store:
        try:
            store.insert_run(run_id, datetime.utcnow().isoformat() + "Z")
        except sqlite3.IntegrityError:
            pass
        try:
            store.insert_run_budget(run_id, budget.get("max_calls"), budget.get("max_seconds"))
        except sqlite3.IntegrityError:
            pass
        store.conn.commit()


def _dual_write_replay(workspace: Path, message_id: str, envelope_hash: str, artifact_ref: Optional[str]) -> None:
    """Write replay record to normalized 3NF schema. Idempotent via IntegrityError catch.

    Raises on real errors; swallowed by check_replay/store_artifact per FR-008.
    """
    from workerbees.store import Store

    d = workspace / ".workerbees"
    db_path = d / "workerbees.db"

    with Store(db_path) as store:
        now = datetime.utcnow().isoformat() + "Z"

        try:
            store.insert_replay(message_id, envelope_hash, artifact_ref, created_at=now)
        except sqlite3.IntegrityError:
            pass

        store.conn.commit()


def _dual_write_cancellation(workspace: Path, run_id: str) -> None:
    """Write cancellation to normalized 3NF schema. Idempotent via IntegrityError catch.

    Raises on real errors; swallowed by cancel per FR-008.
    """
    from workerbees.store import Store

    d = workspace / ".workerbees"
    db_path = d / "workerbees.db"

    with Store(db_path) as store:
        at = datetime.utcnow().isoformat() + "Z"

        try:
            store.insert_cancellation(run_id, at)
        except sqlite3.IntegrityError:
            pass

        store.conn.commit()


def _dual_write_lease(workspace: Path, workspace_key: str, run_id: str) -> None:
    """Write lease to normalized 3NF schema. Idempotent via IntegrityError catch.

    Raises on real errors; swallowed by acquire_lease per FR-008.
    """
    from workerbees.store import Store

    d = workspace / ".workerbees"
    db_path = d / "workerbees.db"

    with Store(db_path) as store:
        now = datetime.utcnow().isoformat() + "Z"

        try:
            store.insert_lease(workspace_key, run_id, now)
        except sqlite3.IntegrityError:
            pass

        store.conn.commit()


def _dual_write_approval(workspace: Path, approval_id: str, run_id: str, requester: str,
                        action: str, resource: str, artifact_hash: str, risk: str,
                        rule_ids: list, expires_at: str) -> None:
    """Write approval to normalized 3NF schema. Idempotent via IntegrityError catch.

    Raises on real errors; swallowed by request_approval per FR-008.
    """
    from workerbees.store import Store

    d = workspace / ".workerbees"
    db_path = d / "workerbees.db"

    with Store(db_path) as store:
        now = datetime.utcnow().isoformat() + "Z"
        try:
            store.insert_run(run_id, now)
        except sqlite3.IntegrityError:
            pass
        try:
            store.insert_approval(approval_id, run_id, requester, action, resource,
                                 artifact_hash, risk, expires_at)
        except sqlite3.IntegrityError:
            pass

        for ordinal, rule_id in enumerate(rule_ids):
            try:
                store.insert_approval_rule(approval_id, ordinal, rule_id)
            except sqlite3.IntegrityError:
                pass

        store.conn.commit()
