#!/usr/bin/env python3
"""Small, local job runner for the Codex Bridge delegation legs.

Jobs are deliberately file-backed rather than service-backed: they survive the calling
shell, are inspectable with ordinary tools, and never require a daemon or credentials in
their metadata.  Provider calls stay in the existing wrapper scripts.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = Path(os.environ.get("CODEX_BRIDGE_SCRIPTS_DIR", SCRIPT_DIR))
STATE_DIR = Path(
    os.environ.get("CODEX_BRIDGE_AGENT_STATE_DIR", Path.home() / ".codex-bridge" / "agents")
)
MODE = os.environ.get("CODEX_BRIDGE_MODE", "standard")
VALID_MODES = {"standard", "budget", "ultra"}
ANTHROPIC = {"haiku", "sonnet", "opus", "fable", "anthropic"}
CANONICAL = {
    "gemini": "gemini-flash",
    "gemini-flash": "gemini-flash",
    "gemini-lite": "gemini-flash-lite",
    "gemini-flash-lite": "gemini-flash-lite",
    "gemini-deep": "gemini-deep",
    "mistral": "mistral",
    "openrouter": "openrouter",
    "codex": "codex",
    "ask": "codex",
}
TERMINAL = {"returned", "verified", "needs-review", "failed", "interrupted", "cancelled"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def die(message: str, code: int = 2) -> None:
    print(f"agent: {message}", file=sys.stderr)
    raise SystemExit(code)


def ensure_mode() -> None:
    if MODE not in VALID_MODES:
        die("invalid CODEX_BRIDGE_MODE: " + MODE + " (accepted values: standard, budget, ultra)")


def ensure_state_dir() -> None:
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(STATE_DIR, 0o700)
    except OSError:
        pass


def job_dir(job_id: str) -> Path:
    if not job_id or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in job_id):
        die("invalid job id")
    return STATE_DIR / job_id


def metadata_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.json"


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def read_job(job_id: str) -> dict[str, Any]:
    path = metadata_path(job_id)
    try:
        with path.open(encoding="utf-8") as handle:
            job = json.load(handle)
    except FileNotFoundError:
        die(f"job not found: {job_id}", 1)
    except (OSError, json.JSONDecodeError) as error:
        die(f"cannot read job {job_id}: {error}", 1)
    if not isinstance(job, dict):
        die(f"invalid job metadata: {job_id}", 1)
    return job


def save_job(job: dict[str, Any]) -> None:
    write_json(metadata_path(job["id"]), job)


def write_artifact(job: dict[str, Any]) -> None:
    """Publish a stable, provider-neutral terminal record for external consumers.

    A supervisor may translate or summarize this record later.  The runner never
    invokes a translator itself, which preserves ultra mode's provider boundary.
    """
    directory = job_dir(job["id"])
    write_json(directory / "result.json", {
        "schema": "codex-bridge-agent-result-v1",
        "job_id": job["id"],
        "parent_id": job.get("parent_id"),
        "backend": job.get("backend"),
        "task_class": job.get("task_class"),
        "status": job.get("status"),
        "attempt": job.get("attempt"),
        "exit_code": job.get("exit_code"),
        "completed_at": job.get("finished_at"),
        "error": job.get("error"),
        "output_path": str(directory / "result.txt"),
        "stderr_path": str(directory / "stderr.txt"),
    })


def canonical_backend(backend: str) -> str:
    backend = backend.lower()
    if backend in ANTHROPIC:
        if MODE == "ultra":
            die(f"ultra mode refuses Anthropic backend '{backend}'", 5)
        die(f"backend '{backend}' has no local wrapper", 2)
    if backend not in CANONICAL:
        die("unsupported backend: " + backend + " (use auto, codex, gemini, gemini-lite, gemini-deep, mistral, or openrouter)")
    return CANONICAL[backend]


def route_backend(task_class: str) -> str:
    route = SCRIPTS_DIR / "route.sh"
    try:
        selected = subprocess.run(
            [str(route), "pick", task_class], text=True, capture_output=True, check=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        die(f"cannot select backend: {error}", 1)
    if selected.returncode:
        detail = selected.stderr.strip() or selected.stdout.strip() or f"route exit {selected.returncode}"
        die(detail, selected.returncode)
    return canonical_backend(selected.stdout.strip())


def make_command(job: dict[str, Any]) -> list[str]:
    backend = job["backend"]
    prompt = job["prompt"]
    if backend == "codex":
        command = [str(SCRIPTS_DIR / "ask.sh")]
        if job.get("reset"):
            command.append("--reset")
    elif backend.startswith("gemini"):
        tier = {"gemini-flash": "digest", "gemini-flash-lite": "cheap", "gemini-deep": "deep"}[backend]
        command = [str(SCRIPTS_DIR / "gask.sh"), "--tier", tier]
    elif backend == "mistral":
        command = [str(SCRIPTS_DIR / "mask.sh"), "--tier", job.get("tier", "code")]
        if job.get("agent"):
            command.append("--agent")
        if job.get("reset"):
            command.append("--reset")
    elif backend == "openrouter":
        command = [str(SCRIPTS_DIR / "oask.sh")]
    else:  # Metadata is only written by this runner, but fail closed if it was tampered with.
        die(f"job {job['id']} has unsupported backend '{backend}'", 1)
    command.append(prompt)
    return command


def classify_error(text: str) -> str:
    route = SCRIPTS_DIR / "route.sh"
    try:
        result = subprocess.run(
            [str(route), "classify", text[:1000]], text=True, capture_output=True, check=False, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip() in {"quota", "transient", "unknown"}:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown"


def report_route(backend: str, outcome: str, error: str = "") -> None:
    # Health bookkeeping must never hide a provider result.
    route = SCRIPTS_DIR / "route.sh"
    health_backend = "gemini-flash" if backend == "gemini-deep" else backend
    try:
        subprocess.run([str(route), "report", health_backend, outcome, error[:200]], check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass


def start_job(job: dict[str, Any]) -> None:
    command = [sys.executable, str(Path(__file__).resolve()), "_run", job["id"]]
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
            env=os.environ.copy(),
        )
    except OSError as error:
        job.update(status="failed", finished_at=now(), error=f"could not start worker: {error}")
        save_job(job)
        die(job["error"], 1)
    # Do not write metadata after spawning: a fast worker may already have
    # recorded its terminal result, and a parent-side write would clobber it.


def run_worker(job_id: str) -> int:
    ensure_mode()
    job = read_job(job_id)
    if job.get("status") in TERMINAL:
        return 0
    job.update(status="running", started_at=now(), error=None)
    save_job(job)
    attempts = int(job.get("retries", 0)) + 1
    result_path = job_dir(job_id) / "result.txt"
    stderr_path = job_dir(job_id) / "stderr.txt"

    for attempt in range(1, attempts + 1):
        job["attempt"] = attempt
        job["status"] = "running" if attempt == 1 else "retrying"
        save_job(job)
        try:
            completed = subprocess.run(make_command(job), text=True, capture_output=True, check=False)
        except OSError as error:
            completed = None
            output, errors, code = "", str(error), 127
        else:
            output, errors, code = completed.stdout, completed.stderr, completed.returncode

        result_path.write_text(output, encoding="utf-8")
        stderr_path.write_text(errors, encoding="utf-8")
        os.chmod(result_path, 0o600)
        os.chmod(stderr_path, 0o600)
        if code == 0:
            job.update(status="returned", finished_at=now(), exit_code=0, error=None, verified_at=None)
            save_job(job)
            write_artifact(job)
            report_route(job["backend"], "ok")
            return 0

        detail = (errors or output or f"backend exited {code}").strip()
        kind = classify_error(detail)
        job.update(exit_code=code, error=detail[-1000:])
        save_job(job)
        report_route(job["backend"], kind, detail)
        if attempt < attempts and kind == "transient":
            time.sleep(min(attempt, 3))
            continue
        break

    job.update(status="failed", finished_at=now())
    save_job(job)
    write_artifact(job)
    return int(job.get("exit_code") or 1)


def brief(job: dict[str, Any]) -> dict[str, Any]:
    return {key: job.get(key) for key in (
        "id", "parent_id", "status", "backend", "task_class", "agent", "attempt", "retries",
        "created_at", "started_at", "finished_at", "verified_at", "exit_code", "error",
    )}


def print_job(job: dict[str, Any], as_json: bool) -> None:
    view = brief(job)
    if as_json:
        print(json.dumps(view, sort_keys=True))
        return
    for key, value in view.items():
        if value is not None:
            print(f"{key}: {value}")


def mark_verified(job_id: str, verdict: str) -> None:
    """Mark a returned job as verified or needs-review.

    Only allowed when status is 'returned'. Updates status and sets verified_at timestamp.
    """
    if verdict not in {"verified", "needs-review"}:
        die(f"invalid verdict: {verdict} (must be 'verified' or 'needs-review')", 2)
    job = read_job(job_id)
    if job.get("status") != "returned":
        die(f"cannot mark job {job_id}: status is '{job.get('status')}' (must be 'returned')", 1)
    job.update(status=verdict, verified_at=now())
    save_job(job)
    write_artifact(job)


def wait_for(job_id: str, as_json: bool = False, interval: float = 0.1) -> int:
    while True:
        job = read_job(job_id)
        if job.get("status") in TERMINAL:
            print_job(job, as_json)
            return 0 if job["status"] in {"returned", "verified", "needs-review"} else int(job.get("exit_code") or 1)
        time.sleep(interval)


def submit(args: argparse.Namespace, parent_id: str | None = None, followup: bool = False) -> int:
    ensure_mode()
    ensure_state_dir()
    backend = canonical_backend(args.backend) if args.backend != "auto" else route_backend(args.task_class)
    if followup:
        parent = read_job(parent_id or "")
        if parent.get("backend") not in {"codex", "mistral"}:
            die(f"job {parent['id']} uses {parent.get('backend')}; follow-up is supported only for codex or mistral (openrouter is stateless)", 2)
        backend = parent["backend"]
        agent = bool(parent.get("agent"))
        if backend == "mistral" and not agent:
            die(f"job {parent['id']} used a stateless Mistral completion; use --agent when submitting it", 2)
        tier = parent.get("tier", "code")
    else:
        agent = bool(args.agent)
        tier = args.tier
    if backend == "mistral" and args.agent:
        agent = True
    if backend != "mistral" and agent:
        die("--agent is supported only with mistral (openrouter is stateless single-turn)", 2)
    if backend.startswith("gemini") and args.reset:
        die("--reset is unsupported for stateless Gemini jobs", 2)

    job_id = "job-" + secrets.token_hex(8)
    directory = job_dir(job_id)
    directory.mkdir(mode=0o700)
    job = {
        "id": job_id,
        "parent_id": parent_id,
        "status": "queued",
        "backend": backend,
        "task_class": args.task_class,
        "prompt": args.prompt,
        "agent": agent,
        "tier": tier,
        "reset": bool(args.reset),
        "retries": args.retries,
        "attempt": 0,
        "created_at": now(),
        "started_at": None,
        "finished_at": None,
        "verified_at": None,
        "exit_code": None,
        "error": None,
    }
    save_job(job)
    start_job(job)
    if args.wait:
        return wait_for(job_id, args.json)
    print(job_id)
    return 0


def command_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent.sh",
        description="Dispatch governed local Codex, Gemini, and Mistral jobs.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def add_submit_flags(target: argparse.ArgumentParser) -> None:
        target.add_argument("--backend", default="auto", help="auto, codex, gemini, gemini-lite, gemini-deep, or mistral")
        target.add_argument("--class", dest="task_class", default="review", help="route task class when backend is auto")
        target.add_argument("--agent", action="store_true", help="use the persistent Mistral agent")
        target.add_argument("--tier", choices=("cheap", "code", "deep"), default="code", help="Mistral tier")
        target.add_argument("--reset", action="store_true", help="reset a persistent Codex or Mistral-agent session")
        target.add_argument("--retries", type=int, default=0, choices=range(0, 4), metavar="N", help="retry transient failures (0-3)")
        target.add_argument("--wait", action="store_true", help="wait and print the terminal status")
        target.add_argument("--json", action="store_true", help="with --wait, print terminal status as JSON")
        target.add_argument("prompt")

    add_submit_flags(commands.add_parser("submit", help="queue one job"))
    follow = commands.add_parser("follow-up", help="continue a Codex or Mistral-agent job")
    follow.add_argument("job_id")
    follow.add_argument("--wait", action="store_true")
    follow.add_argument("--json", action="store_true")
    follow.add_argument("prompt")
    status = commands.add_parser("status", help="show one job")
    status.add_argument("job_id")
    status.add_argument("--json", action="store_true")
    result = commands.add_parser("result", help="print saved job output or its structured artifact")
    result.add_argument("job_id")
    result.add_argument("--stderr", action="store_true", help="print saved stderr instead")
    result.add_argument("--json", action="store_true", help="print the provider-neutral result artifact")
    wait = commands.add_parser("wait", help="wait for a job")
    wait.add_argument("job_id")
    wait.add_argument("--json", action="store_true")
    verify = commands.add_parser("verify", help="mark a returned job as verified or needs-review")
    verify.add_argument("job_id")
    verify.add_argument("--verdict", choices=("verified", "needs-review"), required=True)
    commands.add_parser("list", help="list jobs") .add_argument("--json", action="store_true")
    commands.add_parser("_run", help=argparse.SUPPRESS).add_argument("job_id")
    return parser


def main() -> int:
    parser = command_parser()
    args = parser.parse_args()
    if args.command == "submit":
        return submit(args)
    if args.command == "follow-up":
        parent = read_job(args.job_id)
        namespace = argparse.Namespace(
            backend=parent.get("backend", ""), task_class=parent.get("task_class", "review"), agent=parent.get("agent", False),
            tier=parent.get("tier", "code"), reset=False, retries=parent.get("retries", 0), wait=args.wait, json=args.json, prompt=args.prompt,
        )
        return submit(namespace, parent_id=args.job_id, followup=True)
    if args.command == "_run":
        return run_worker(args.job_id)
    if args.command == "status":
        print_job(read_job(args.job_id), args.json)
        return 0
    if args.command == "wait":
        return wait_for(args.job_id, args.json)
    if args.command == "verify":
        mark_verified(args.job_id, args.verdict)
        return 0
    if args.command == "result":
        read_job(args.job_id)
        if args.json:
            path = job_dir(args.job_id) / "result.json"
            try:
                print(path.read_text(encoding="utf-8"), end="")
            except FileNotFoundError:
                die(f"result artifact not available for {args.job_id}", 1)
            return 0
        path = job_dir(args.job_id) / ("stderr.txt" if args.stderr else "result.txt")
        try:
            print(path.read_text(encoding="utf-8"), end="")
        except FileNotFoundError:
            die(f"result not available for {args.job_id}", 1)
        return 0
    if args.command == "list":
        ensure_state_dir()
        jobs = []
        for path in sorted(STATE_DIR.glob("job-*/job.json"), reverse=True):
            try:
                jobs.append(brief(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError):
                continue
        if args.json:
            print(json.dumps(jobs, sort_keys=True))
        else:
            for job in jobs:
                print(f"{job['id']} {job['status']} {job['backend']} class={job['task_class']} attempts={job['attempt']}")
        return 0
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
