"""`agents-inc dispatch`: render, lint, snapshot, launch, and verify one delegation (D45, D46, D47).

Only the status line goes to stdout. Everything else lands in the run directory.
"""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "skills" / "workerbee" / "scripts"

CODEX_SLUGS = ("astra", "sol", "terra", "luna")
# Exact Claude model ids passed to `claude -p --model`. Keep this the only table.
CLAUDE_MODELS = {"fable": "claude-fable-5-1", "opus": "claude-opus-5-5",
                 "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-4-5-20251001"}
# Slot placeholder for the snapshot path; the wrapper fills it after capture.
SNAPSHOT_PLACEHOLDER = "<snapshot>"
FREE_SLUGS = ("gemini", "mistral", "openrouter")
DEFAULT_PERMISSION_MODE = "acceptEdits"
EXIT_OK, EXIT_RED, EXIT_USAGE, EXIT_REFUSED = 0, 1, 2, 3


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_agents_inc_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def default_parent() -> Path:
    base = os.environ.get("CLAUDE_SCRATCHPAD") or os.environ.get("TMPDIR") or "/tmp"
    return Path(base) / "agents-inc-runs"


def new_run_id(model: str) -> str:
    return f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{model}-{secrets.token_hex(3)}"


def render(slots_path: Path) -> tuple[int, str, str]:
    """Render via render_dispatch.main() in-process; return (rc, prompt, stderr)."""
    module = _load("render_dispatch")
    out, err = io.StringIO(), io.StringIO()
    saved = sys.argv
    sys.argv = ["render_dispatch.py", "--slots", str(slots_path)]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = module.main()
    finally:
        sys.argv = saved
    return rc, out.getvalue(), err.getvalue()


def _handoff_lint(module, path: Path, profile: str | None) -> tuple[int, str]:
    script = Path(os.environ.get("HOME", "")) / ".claude/skills/handoff-lint/scripts/handoff_lint.py"
    if not script.is_file():
        return 0, module.HANDOFF_WARNING + "\n"
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = module.run_handoff_lint(str(path), profile)
    return rc, err.getvalue()


def lint_prompt(path: Path, tier: str | None, model: str | None = None) -> tuple[list, str]:
    """Return (missing contract elements, log). handoff-lint findings are advisory:
    they go to the log (lint.txt) and never add to `missing`, so they never refuse."""
    module = _load("check_dispatch_prompt")
    missing = module.check(path.read_text(encoding="utf-8"), tier, model=model)
    rc, log = _handoff_lint(module, path, None)
    if rc:
        log = f"handoff-lint advisory (rc={rc}, not a refusal)\n" + log
    return missing, log


def inject_snapshot(prompt: str, snapshot_path: str) -> str:
    """Put the real snapshot path into the prompt: replace every placeholder,
    else append a `SNAPSHOT: <path>` line."""
    if SNAPSHOT_PLACEHOLDER in prompt:
        return prompt.replace(SNAPSHOT_PLACEHOLDER, snapshot_path)
    return prompt.rstrip("\n") + f"\nSNAPSHOT: {snapshot_path}\n"


def lint_report(path: Path) -> tuple[list, str]:
    module = _load("check_dispatch_prompt")
    missing = module.check_report(path.read_text(encoding="utf-8"))
    rc, log = _handoff_lint(module, path, "report")
    if rc:
        missing = list(missing) + ["handoff-lint"]
    return missing, log


def snapshot(*args: str, cwd: Path) -> tuple[int, str]:
    res = subprocess.run([sys.executable, str(SCRIPTS / "pre_dispatch_snapshot.py"), *args],
                         cwd=str(cwd), capture_output=True, text=True)
    return res.returncode, res.stdout + res.stderr


def allow_paths(files_in_scope: str) -> list[str]:
    """Paths named in the FILES_IN_SCOPE slot; prose such as "none (read-only)" yields nothing."""
    out = []
    for token in re.split(r"[\s,;]+", files_in_scope or ""):
        token = token.strip("`'\"()")
        if token and ("/" in token or "." in token) and not token.endswith(":"):
            out.append(token)
    return out


def claude_argv(model: str, permission_mode: str, resume: str | None = None) -> list[str]:
    exe = shutil.which("claude") or "claude"
    argv = [exe, "-p", "--model", CLAUDE_MODELS[model], "--permission-mode", permission_mode,
            "--output-format", "json"]
    if resume:
        argv += ["--resume", resume]
    return argv


def launch(kind: str, model: str, effort: str, cwd: Path, prompt: str, run_dir: Path,
           permission_mode: str = DEFAULT_PERMISSION_MODE, resume: str | None = None) -> dict:
    """Run the delegate. Return {"rc", "stdout", "stderr", "argv", "session_id"}."""
    if kind == "claude":
        argv = claude_argv(model, permission_mode, resume)
        res = subprocess.run(argv, input=prompt, cwd=str(cwd), capture_output=True, text=True)
        text, session = res.stdout, None
        try:
            data = json.loads(res.stdout)
            text, session = str(data.get("result", "")), data.get("session_id")
        except (ValueError, AttributeError):
            pass
        return {"rc": res.returncode, "stdout": text, "stderr": res.stderr, "argv": argv, "session_id": session}
    from .cli import _efforts, _paths
    from .receipt import InstallReceipt
    from .runtime import run_codex
    paths = _paths()
    receipt = InstallReceipt.load(paths.receipt)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = run_codex(model, effort, cwd, io.StringIO(prompt), receipt, _efforts(paths.current.resolve()))
    return {"rc": rc, "stdout": out.getvalue(), "stderr": err.getvalue(),
            "argv": ["run_codex", model, effort, str(cwd)], "session_id": None}


def _kind(model: str) -> str | None:
    if model in CODEX_SLUGS:
        return "codex"
    if model in CLAUDE_MODELS:
        return "claude"
    return None


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def _verify(spec: dict, run_dir: Path, out_path: Path) -> tuple[str, str, int]:
    missing, log = lint_report(out_path)
    report = "COMPLIANT" if not missing else f"NON-COMPLIANT:{missing}"
    allow = list(spec["gates"]["allow"])
    cwd = Path(spec["cwd"])
    try:
        allow.append(str(run_dir.resolve().relative_to(cwd.resolve())))
    except ValueError:
        pass
    args = ["verify", spec["snapshot"]]
    for a in allow:
        args += ["--allow", a]
    src, slog = snapshot(*args, cwd=cwd)
    changed = [ln[8:] for ln in slog.splitlines() if ln.startswith("CHANGED ")]
    snap = "clean" if src == 0 else ("CHANGED:" + ",".join(changed) if changed else f"ERROR:rc={src}")
    (run_dir / "verify.txt").write_text(f"report: {report}\n{log}\nsnapshot rc={src}\n{slog}", encoding="utf-8")
    return report, snap, src


WORKERS_SPAWNED_RE = re.compile(r"^\W*workers spawned:\s*(\d+)\W*$", re.IGNORECASE | re.MULTILINE)


def parse_workers_spawned(text: str) -> int | None:
    """Return n from the last `WORKERS SPAWNED: <integer>` report line (D48), else None."""
    hits = WORKERS_SPAWNED_RE.findall(text or "")
    return int(hits[-1]) if hits else None


def parse_fan_out(prompt: str) -> dict | None:
    """Return the D48 FAN_OUT budget from a rendered prompt as {width, total, depth}, else None."""
    found = _load("check_dispatch_prompt").parse_fan_out(prompt)
    return dict(zip(("width", "total", "depth"), found)) if found else None


def _fan_out_check(spec: dict, out_path: Path) -> str | None:
    """Record per-attempt `workers_spawned_attempts` and their sum in `workers_spawned`.
    Return a red reason (`workers-spawned-missing`, `fan-out-over-total`) or None."""
    n = parse_workers_spawned(out_path.read_text(encoding="utf-8"))
    attempts = spec.setdefault("workers_spawned_attempts", [])
    attempts.append(n)
    spec["workers_spawned"] = sum(a for a in attempts if a is not None)
    if n is None:
        return "workers-spawned-missing"
    budget = spec.get("fan_out")
    if budget and spec["workers_spawned"] > budget["total"]:
        return "fan-out-over-total"
    return None


def _outcome(spec: dict, report: str, vrc: int, rc: int, fan_reason: str | None) -> tuple[bool, str | None]:
    """Return (green, red reason)."""
    if fan_reason:
        return False, fan_reason
    if rc != 0:
        return False, "rc-nonzero"
    if report != "COMPLIANT":
        return False, "report-noncompliant"
    if vrc != 0:
        return False, "snapshot-not-clean"
    return True, None


def _status(spec: dict, report: str, snap: str, out_path: Path) -> str:
    reason = f" reason={spec['reason']}" if spec.get("reason") else ""
    return (f"dispatch {spec['run_id']} {spec['model']} rc={spec['rc']} report={report} snapshot={snap} "
            f"outcome={spec['outcome']}{reason} out={out_path}")


def _mirror(spec: dict, run_dir: Path, home_repo: str | None) -> None:
    """D46: copy run.json and prompt.md to <home>/specs/consumers/<repo>/runs/<run-id>/."""
    home = home_repo or os.environ.get("AGENTS_INC_HOME_REPO")
    if not home:
        print("run spec not mirrored: no home repo", file=sys.stderr)
        return
    dest = Path(home) / "specs" / "consumers" / Path(spec["cwd"]).name / "runs" / spec["run_id"]
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("run.json", "prompt.md"):
        if (run_dir / name).is_file():
            shutil.copyfile(run_dir / name, dest / name)


def _finish(spec: dict, run_dir: Path, out_path: Path, result: dict, home_repo: str | None) -> int:
    report, snap, vrc = _verify(spec, run_dir, out_path)
    fan_reason = _fan_out_check(spec, out_path)
    green, reason = _outcome(spec, report, vrc, result["rc"], fan_reason)
    spec["outcome"] = "green" if green else "red"
    spec["reason"] = reason
    _write_json(run_dir / "run.json", spec)
    print(_status(spec, report, snap, out_path))
    _mirror(spec, run_dir, home_repo)
    return EXIT_OK if green else EXIT_RED


def run(args) -> int:
    if getattr(args, "resume", None):
        return resume(args)
    if not args.slots or not args.model:
        print("dispatch: --slots and --model are required", file=sys.stderr)
        return EXIT_USAGE
    model = args.model
    kind = _kind(model)
    if kind is None:
        print(f"dispatch: {model} not supported, use agent.sh")
        return EXIT_USAGE
    slots_path = Path(args.slots).resolve()
    try:
        slots = json.loads(slots_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"dispatch: cannot read slots: {exc}", file=sys.stderr)
        return EXIT_USAGE
    cwd = Path(args.cwd or os.getcwd()).resolve()
    run_id = new_run_id(model)
    run_dir = Path(args.run_dir or default_parent()).resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(slots_path, run_dir / "slots.json")
    effort = args.effort or "medium"
    spec = {"run_id": run_id, "kind": kind, "slots": str(slots_path), "model": model, "effort": effort,
            "cwd": str(cwd), "chain": ["CoS", model], "snapshot": str(run_dir / "snapshot.json"),
            "gates": {"tier": args.tier, "allow": allow_paths(str(slots.get("FILES_IN_SCOPE", "")))},
            "permission_mode": slots.get("PERMISSION_MODE") or DEFAULT_PERMISSION_MODE,
            "rc": None, "outcome": None, "session_id": None}
    rc, prompt, err = render(slots_path)
    lint = run_dir / "lint.txt"
    if rc != 0:
        lint.write_text(f"render rc={rc}\n{err}", encoding="utf-8")
        spec["outcome"] = "refused-render"; _write_json(run_dir / "run.json", spec)
        print(f"dispatch {run_id} {model} refused render rc={rc} lint={lint}")
        return EXIT_REFUSED
    # Capture first so the real snapshot path reaches the prompt; lint after injection.
    src, slog = snapshot("capture", spec["snapshot"], cwd=cwd)
    if src != 0:
        spec["outcome"] = "snapshot-failed"; _write_json(run_dir / "run.json", spec)
        print(f"dispatch {run_id} {model} snapshot failed rc={src}: {slog.strip()}")
        return EXIT_RED
    prompt = inject_snapshot(prompt, spec["snapshot"])
    spec["fan_out"] = parse_fan_out(prompt)
    prompt_path = run_dir / "prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    missing, log = lint_prompt(prompt_path, args.tier, model)
    lint.write_text(("COMPLIANT\n" if not missing else f"NON-COMPLIANT missing: {missing}\n") + log, encoding="utf-8")
    if missing:
        spec["outcome"] = "refused-lint"; _write_json(run_dir / "run.json", spec)
        print(f"dispatch {run_id} {model} refused NON-COMPLIANT:{missing} lint={lint}")
        return EXIT_REFUSED
    if args.dry_run:
        spec["outcome"] = "dry-run"; _write_json(run_dir / "run.json", spec)
        print(f"dispatch {run_id} {model} dry-run prompt={prompt_path}")
        return EXIT_OK
    result = launch(kind, model, effort, cwd, prompt, run_dir, spec["permission_mode"])
    out_path = run_dir / "stdout.md"
    out_path.write_text(result["stdout"], encoding="utf-8")
    (run_dir / "stderr.txt").write_text(result["stderr"], encoding="utf-8")
    spec.update(rc=result["rc"], session_id=result.get("session_id"), argv=result.get("argv"))
    return _finish(spec, run_dir, out_path, result, getattr(args, "home_repo", None))


def resume(args) -> int:
    run_dir = Path(args.run_dir or default_parent()).resolve() / args.resume
    try:
        spec = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"dispatch: no run.json for {args.resume}", file=sys.stderr)
        return EXIT_USAGE
    if spec.get("kind") != "claude" or not spec.get("session_id"):
        print("resume unsupported for codex")
        return EXIT_USAGE
    if not args.message:
        print("dispatch: --resume needs --message", file=sys.stderr)
        return EXIT_USAGE
    result = launch("claude", spec["model"], spec["effort"], Path(spec["cwd"]), args.message, run_dir,
                    spec.get("permission_mode", DEFAULT_PERMISSION_MODE), resume=spec["session_id"])
    n = len(spec.get("resumes", [])) + 1
    out_path = run_dir / f"stdout.{n}.md"
    out_path.write_text(result["stdout"], encoding="utf-8")
    (run_dir / f"stderr.{n}.txt").write_text(result["stderr"], encoding="utf-8")
    spec.setdefault("resumes", []).append({"rc": result["rc"], "out": str(out_path)})
    spec["rc"] = result["rc"]
    if result.get("session_id"):
        spec["session_id"] = result["session_id"]
    return _finish(spec, run_dir, out_path, result, getattr(args, "home_repo", None))
