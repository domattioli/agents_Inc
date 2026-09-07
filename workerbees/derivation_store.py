"""Additive derivation storage -- binds RunRecord (workerbees/lineup_router.py) into an
append-only JSONL store for audit/replay, per CONTEXT.md's "Derivation" glossary entry
and specs/009-cross-vendor-dispatch/routing-contract.md section 2.

Separate file/schema from workerbees/ledger.py (Node/Edge/Run model) by design: RunRecord's
shape (candidates_considered, retries, authority_change_events, tie_break_order, etc.) does
not match ledger.py's Node fields, and ledger.py's dedup/lint logic assumes the Node shape.
Mixing schemas into one JSONL file would break both. Reuses ledger._now_iso() for a
consistent timestamp format across the two stores; does not touch ledger.py's Node/Edge/Run
behavior or its dual-write logic (additive only, per job 4 scope).

Persistence convention: append-only JSONL at <workspace>/.workerbees/derivations.jsonl,
one full RunRecord snapshot per persist call (not a partial event like ledger.py's
dispatch/return split) -- idempotent-by-run_id on read: last line for a given run_id wins.

Replay: load_run_record() reconstructs a RunRecord from the persisted JSON; replay_pick()
recomputes `picked` from `candidates_considered` alone (never trusting the stored `picked`
field) to prove policy-choice determinism (CONTEXT.md "Derivation").
"""
from __future__ import annotations
import dataclasses
import json
from pathlib import Path

from workerbees.ledger import _now_iso
from workerbees.lineup_router import RunRecord
from workerbees.router import Route

_FILE_NAME = "derivations.jsonl"


def _derivations_path(workspace: Path) -> Path:
    d = workspace / ".workerbees"
    d.mkdir(parents=True, exist_ok=True)
    return d / _FILE_NAME


def _route_from_dict(d: dict | None) -> Route | None:
    """Reconstruct a Route dataclass from its persisted dict form, or None."""
    if d is None:
        return None
    return Route(provider=d["provider"], model=d["model"], tier=d["tier"], cmd_kind=d["cmd_kind"])


def persist_run_record(workspace: Path, run: RunRecord) -> bool:
    """Append one full RunRecord snapshot to the append-only derivations.jsonl.

    Idempotent-by-run_id on read (last write for a run_id wins) -- the JSONL file itself
    is append-only, never rewritten in place, matching ledger.py's convention.
    Never raises; returns False on any error (same swallow-errors contract as ledger.py's
    record_dispatch/record_return, so a persistence failure never fails a run).
    """
    try:
        payload = dataclasses.asdict(run)
        payload["_persisted_at"] = _now_iso()
        path = _derivations_path(workspace)
        with open(path, "a") as f:
            f.write(json.dumps(payload) + "\n")
        return True
    except Exception:
        return False


def load_run_record(workspace: Path, run_id: str) -> RunRecord | None:
    """Reconstruct the persisted RunRecord for run_id -- last matching line wins.

    Returns None if the file is missing or no line matches run_id. Never raises.
    """
    path = workspace / ".workerbees" / _FILE_NAME
    if not path.exists():
        return None
    last_payload = None
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("run_id") == run_id:
                    last_payload = data
    except OSError:
        return None
    if last_payload is None:
        return None
    return _record_from_dict(last_payload)


def _record_from_dict(data: dict) -> RunRecord:
    """Inverse of dataclasses.asdict(run) -- restores Route-typed fields; everything
    else (candidates_considered/retries/authority_change_events entries) round-trips
    as plain dicts, matching how lineup_router.py's with_pick/with_retry/
    with_authority_change already store their nested "route"/"from"/"to" sub-fields
    (as dicts, not Route objects) -- so no further reconstruction is needed there."""
    return RunRecord(
        run_id=data["run_id"],
        task=data["task"],
        accept_rule=data["accept_rule"],
        authority_holder=_route_from_dict(data["authority_holder"]),
        authority_limits=data["authority_limits"],
        authority_movable=data["authority_movable"],
        authority_move_rule=data["authority_move_rule"],
        policy_version=data["policy_version"],
        allowed_models=tuple(data["allowed_models"]),
        hard_limits=data["hard_limits"],
        budget=data["budget"],
        tie_break_order=tuple(data["tie_break_order"]),
        retry_rule=data["retry_rule"],
        model_snapshot_ref=data["model_snapshot_ref"],
        candidates_considered=tuple(data.get("candidates_considered", ())),
        picked=_route_from_dict(data.get("picked")),
        retries=tuple(data.get("retries", ())),
        authority_change_events=tuple(data.get("authority_change_events", ())),
        pre_approved_larger_pool=tuple(_route_from_dict(r) for r in data.get("pre_approved_larger_pool", ())),
        pre_approved_backup_list=tuple(_route_from_dict(r) for r in data.get("pre_approved_backup_list", ())),
    )


def replay_pick(run: RunRecord) -> Route | None:
    """Recompute `picked` from `candidates_considered` alone (never trusting run.picked),
    proving policy-choice determinism (CONTEXT.md "Derivation": "same Run + same policy +
    same model-list snapshot + same event history -> same route picked").

    Algorithm: candidates_considered is an append-only history across every route_step()
    call in the run's lifetime (start / failure re-rank / capability escalation / ...).
    Each call's with_pick() marks exactly one entry `kept: True` (the top of that call's
    ranking) and the rest `kept: False`. The run's CURRENT pick is therefore the LAST
    kept=True entry in the history (later calls supersede earlier ones) -- recompute by
    walking the history in order and keeping the last kept=True route seen.
    Returns None if no entry was ever kept (empty-pool terminal case).
    """
    last_kept = None
    for entry in run.candidates_considered:
        if entry.get("kept"):
            last_kept = entry.get("route")
    if last_kept is None:
        return None
    return Route(provider=last_kept["provider"], model=last_kept["model"],
                 tier=last_kept["tier"], cmd_kind=last_kept["cmd_kind"])
