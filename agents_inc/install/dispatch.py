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


# D51 Claude Worker confinement (mirrors D49), applied only under the broker.
WORKER_PATH = "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin"
# USER is required: without it `claude auth status` reports loggedIn false (keychain account lookup).
WORKER_ENV_KEYS = ("HOME", "USER", "TERM", "LANG", "TMPDIR")
SECRET_ENV_RE = re.compile(r"KEY|TOKEN|SECRET", re.IGNORECASE)
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
# Same-vendor exception: ~/.claude stays readable and writable for the Claude Worker; ~/.codex is denied.
CLAUDE_WORKER_DENY = (".ssh", ".config", ".codex-bridge", ".codex", ".local", ".aws", ".gnupg", ".netrc")


def worker_env(exe: str, base: dict | None = None) -> dict:
    """Explicit minimal env for a broker-launched Claude Worker: fixed PATH plus the claude directory,
    HOME, USER, TERM, LANG, TMPDIR. Nothing else passes, so no *KEY*/*TOKEN*/*SECRET* or bridge token."""
    base = os.environ if base is None else base
    env = {"PATH": WORKER_PATH + ":" + os.path.dirname(os.path.abspath(exe))}
    for key in WORKER_ENV_KEYS:
        if key in base:
            env[key] = base[key]
    return {k: v for k, v in env.items() if not SECRET_ENV_RE.search(k)}


def _sb(path) -> str:
    text = os.path.realpath(str(path))
    if any(ch in text for ch in ('"', "\\", "\n")):
        raise ValueError(f"path not expressible in sandbox profile: {text!r}")
    return text


# ~/.claude subpaths a Claude Worker may read and write; everything else under ~/.claude and
# ~/.claude.json* is denied (no credentials or api key cache in reports). Login comes from the keychain.
CLAUDE_HOME_ALLOW = ("projects", "todos", "statsig")
# Read-only: settings.json hooks run scripts from here; an unreadable hook fails closed and blocks tools.
# settings.json is read-only so a Worker cannot persist hooks for later unsandboxed sessions.
CLAUDE_HOME_READ = ("scripts", "settings.json")


def sandbox_available() -> bool:
    return sys.platform == "darwin" and os.access(SANDBOX_EXEC, os.X_OK)


def claude_scratch_dir() -> str:
    """Claude Code's Bash tool scratch root (/private/tmp/claude-<uid>); the only /private/tmp write grant."""
    return f"/private/tmp/claude-{os.getuid()}"


def claude_sandbox_profile(cwd: Path, home: Path, tmpdir: str, deny_paths: tuple = ()) -> str:
    """sandbox-exec profile: writes only to cwd, the child tmpdir, claude_scratch_dir(), /dev, the login keychain, and the
    CLAUDE_HOME_ALLOW subpaths; reads and writes denied under the D49 home deny list, ~/.claude.json*,
    and ~/.claude outside CLAUDE_HOME_ALLOW. deny_paths (the broker run directory, the Lead's isolated CODEX_HOME) are
    unreadable and unwritable except the child's own tmpdir, even when they sit under a granted cwd."""
    h = _sb(home)
    claude_ok = [f"{h}/.claude/{name}" for name in CLAUDE_HOME_ALLOW]
    writable = [_sb(cwd), _sb(tmpdir), claude_scratch_dir(), f"{h}/Library/Keychains", "/dev"] + claude_ok
    keep = " ".join(f'(require-not (subpath "{w}"))' for w in writable)
    deny = " ".join(f'(subpath "{h}/{name}")' for name in CLAUDE_WORKER_DENY)
    claude_read = claude_ok + [f"{h}/.claude/{name}" for name in CLAUDE_HOME_READ]
    claude_keep = " ".join(f'(require-not (subpath "{w}"))' for w in claude_read)
    broker_deny = "".join(
        f'(deny file-read* file-write* (require-all (subpath "{_sb(d)}") (require-not (subpath "{_sb(tmpdir)}"))))\n'
        for d in deny_paths)
    return ("(version 1)\n(allow default)\n"
            f"(deny file-write* (require-all {keep}))\n"
            + broker_deny +
            f"(deny file-read* file-write* {deny})\n"
            f'(deny file-read* file-write* (regex #"^{re.escape(h)}/\\.claude\\.json"))\n'
            f'(deny file-read* file-write* (require-all (subpath "{h}/.claude") {claude_keep}))\n'
            f'(deny file-write* {" ".join(f"(subpath \"{h}/.claude/{n}\")" for n in CLAUDE_HOME_READ)})\n')


def _child_tmp(run_dir: Path) -> Path:
    """Broker-owned per-child temp dir; the Worker's only TMPDIR (never inherited /tmp)."""
    tmp = Path(run_dir) / "tmp"
    tmp.mkdir(mode=0o700)
    return tmp.resolve()


def launch(kind: str, model: str, effort: str, cwd: Path, prompt: str, run_dir: Path,
           permission_mode: str = DEFAULT_PERMISSION_MODE, resume: str | None = None) -> dict:
    """Run the delegate. Return {"rc", "stdout", "stderr", "argv", "session_id"}."""
    if kind == "claude":
        argv = claude_argv(model, permission_mode, resume)
        extra = {}
        if _BROKER_SAFE_WRITES:
            if not sandbox_available():
                raise RuntimeError("no-sandbox-backend")  # never run a broker Claude Worker unconfined
            env = worker_env(argv[0])
            env["TMPDIR"] = str(_child_tmp(run_dir))
            extra["env"] = env
            profile = Path(run_dir) / "sandbox.sb"
            _wtext(profile, claude_sandbox_profile(Path(cwd), Path(env.get("HOME") or Path.home()), env["TMPDIR"],
                                                   _BROKER_DENY))
            argv = [SANDBOX_EXEC, "-f", str(profile)] + argv
        res = subprocess.run(argv, input=prompt, cwd=str(cwd), capture_output=True, text=True, **extra)
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
    env = None
    if _BROKER_SAFE_WRITES:
        env = worker_env(str(receipt.codex_path or "/usr/bin/false"))
        env["TMPDIR"] = str(_child_tmp(run_dir))
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = run_codex(model, effort, cwd, io.StringIO(prompt), receipt, _efforts(paths.current.resolve()), env=env,
                       extra_deny=_BROKER_DENY if _BROKER_SAFE_WRITES else (), isolate_home=_BROKER_SAFE_WRITES)
    return {"rc": rc, "stdout": out.getvalue(), "stderr": err.getvalue(),
            "argv": ["run_codex", model, effort, str(cwd)], "session_id": None}


def _kind(model: str) -> str | None:
    if model in CODEX_SLUGS:
        return "codex"
    if model in CLAUDE_MODELS:
        return "claude"
    return None


# D51: True while the broker runs a Worker. Artifact writes then never follow a
# planted link and never overwrite (run.json is replaced atomically instead).
_BROKER_SAFE_WRITES = False
_BROKER_DENY: tuple = ()  # D51: broker run directory (+ isolated CODEX_HOME) denied to Claude Workers
_LAUNCHES = 0  # Worker launches started by run(); the broker charges fan-out from this, not from disk


def _wtext(path: Path, text: str) -> None:
    if _BROKER_SAFE_WRITES:
        _write_new(path, text)
    else:
        path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    if _BROKER_SAFE_WRITES:
        _atomic_write_json(path, data, overwrite=True)
    else:
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
    _wtext(run_dir / "verify.txt", f"report: {report}\n{log}\nsnapshot rc={src}\n{slog}")
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
    if not green and result["rc"] == EXIT_USAGE:
        return EXIT_USAGE  # keep a child usage error distinct from red (broker request status 2)
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
    if _BROKER_SAFE_WRITES:
        _wtext(run_dir / "slots.json", slots_path.read_text(encoding="utf-8"))
    else:
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
        _wtext(lint, f"render rc={rc}\n{err}")
        spec["outcome"] = "refused-render"; _write_json(run_dir / "run.json", spec)
        print(f"dispatch {run_id} {model} refused render rc={rc} lint={lint}")
        return EXIT_REFUSED
    if _BROKER_SAFE_WRITES and SCOPE_LINE not in prompt:
        _wtext(lint, "rendered prompt lacks the SCOPE BOILERPLATE line\n")
        spec["outcome"] = "refused-scope"; _write_json(run_dir / "run.json", spec)
        print(f"dispatch {run_id} {model} refused scope-boilerplate-missing lint={lint}")
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
    _wtext(prompt_path, prompt)
    missing, log = lint_prompt(prompt_path, args.tier, model)
    _wtext(lint, ("COMPLIANT\n" if not missing else f"NON-COMPLIANT missing: {missing}\n") + log)
    if missing:
        spec["outcome"] = "refused-lint"; _write_json(run_dir / "run.json", spec)
        print(f"dispatch {run_id} {model} refused NON-COMPLIANT:{missing} lint={lint}")
        return EXIT_REFUSED
    if args.dry_run:
        spec["outcome"] = "dry-run"; _write_json(run_dir / "run.json", spec)
        print(f"dispatch {run_id} {model} dry-run prompt={prompt_path}")
        return EXIT_OK
    global _LAUNCHES
    _LAUNCHES += 1
    result = launch(kind, model, effort, cwd, prompt, run_dir, spec["permission_mode"])
    out_path = run_dir / "stdout.md"
    _wtext(out_path, result["stdout"])
    _wtext(run_dir / "stderr.txt", result["stderr"])
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


# ---------------------------------------------------------------------------
# D51 credential-blind dispatch broker: `agents-inc dispatch --serve <run-dir>`.
# The Lead writes <id>.request.json (via .tmp rename) and lead.done into
# <run-dir>/inbox/, its only write grant. The broker validates each request against
# broker-owned run.json, runs one D47 dispatch under <run-dir>/workers/<id>/, and
# writes <run-dir>/<id>.report.md then <run-dir>/<id>.result.json. Sequential only (MVP).
# ---------------------------------------------------------------------------
REQUEST_SCHEMA_VERSION = 1
REQUEST_MAX_BYTES = 64 * 1024
REQUEST_KEYS = frozenset({"schema_version", "request_id", "model", "effort", "tier", "slots"})
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
REQUEST_FILE_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_-]{0,63})\.request\.json$")
SLOT_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
# Slots a request may never set: the broker owns these through run.json.
BROKER_OWNED_SLOTS = frozenset({"PERMISSION_MODE"})
# Efforts for a model without `supported_efforts` in models.json (Claude: `claude -p` ignores effort).
DEFAULT_EFFORTS = ("low", "medium", "high", "max")
INBOX = "inbox"  # the only Lead-writable path in a run directory (D51)
LEAD_DONE = "lead.done"
SCOPE_LINE = "SCOPE BOILERPLATE: repo-scoped writes only"
# Request text that points the credential-bearing Worker at secrets is refused.
CREDENTIAL_RE = re.compile(
    r"(~|\$HOME|\$\{HOME\}|/Users/[^/\s]+|/home/[^/\s]+|/root)/\.(claude|codex|ssh|config|aws|gnupg|netrc|local|codex-bridge)\b"
    r"|\.env\b|id_rsa|id_ed25519|\.pem\b|\.key\b|credentials|token|api[_-]?key",
    re.IGNORECASE)
BROKER_OK, BROKER_FATAL, BROKER_USAGE = 0, 1, 2
REQ_GREEN, REQ_RED, REQ_USAGE, REQ_REFUSED = 0, 1, 2, 3
REQ_STATUS = {REQ_GREEN: "green", REQ_RED: "red", REQ_USAGE: "usage-error", REQ_REFUSED: "refused"}


class BrokerFatal(Exception):
    """Broker I/O failure that stops the serve loop (exit 1)."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write_new(path: Path, text: str) -> None:
    """Write text to path atomically; never overwrite and never follow a planted link.
    Raises FileExistsError when path already exists."""
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.broker-tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.link(str(tmp), str(path))  # fails if path exists (file or symlink)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(str(tmp))


def _atomic_write_json(path: Path, data: dict, overwrite: bool = False) -> None:
    """Atomic JSON write. overwrite=False never replaces an existing path."""
    text = json.dumps(data, indent=1) + "\n"
    if not overwrite:
        _write_new(path, text)
        return
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.broker-tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(str(tmp), str(path))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(str(tmp))
        raise


def _load_run_manifest(run_dir: Path) -> dict:
    """Read and validate broker-owned run.json; raise ValueError on any defect."""
    path = run_dir / "run.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("run.json missing or not a regular file")
    spec = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise ValueError("run.json schema_version must be 1")
    models = spec.get("worker_models")
    if (not isinstance(models, list) or not models
            or not all(isinstance(m, str) and _kind(m) for m in models)):
        raise ValueError("run.json worker_models must list supported models")
    fan = spec.get("fan_out")
    if (not isinstance(fan, dict) or set(fan) != {"width", "total", "depth"}
            or not all(type(fan[k]) is int and fan[k] >= 0 for k in fan)):
        raise ValueError("run.json fan_out must be {width, total, depth} non-negative integers")
    cwd = spec.get("cwd")
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or not Path(cwd).is_dir():
        raise ValueError("run.json cwd must be an existing absolute directory")
    # A Worker with a writable cwd could rewrite the broker's own scripts (`_load` re-executes them per call).
    # An installed release under ~/.local is never inside a Worker cwd, so it is unaffected.
    if REPO_ROOT.resolve().is_relative_to(Path(cwd).resolve()):
        raise ValueError("broker-code-in-workspace: the broker source checkout is inside the Worker cwd")
    mode = spec.get("permission_mode", DEFAULT_PERMISSION_MODE)
    if not isinstance(mode, str) or not mode:
        raise ValueError("run.json permission_mode must be a string")
    return spec


def _validate_request(inbox: Path, name: str, spec: dict) -> tuple[dict | None, str | None]:
    """Return (request, None) or (None, reason) for <inbox>/<name>. Never trusts paths inside the request."""
    m = REQUEST_FILE_RE.match(name)
    if not m:
        return None, "bad-filename"
    path = inbox / name
    try:
        st = os.lstat(str(path))
    except OSError:
        return None, "unreadable"
    import stat as _stat
    if not _stat.S_ISREG(st.st_mode):
        return None, "not-regular-file"
    if st.st_size > REQUEST_MAX_BYTES:
        return None, "too-large"
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as fh:
            raw = fh.read(REQUEST_MAX_BYTES + 1)
    except OSError:
        return None, "unreadable"
    if len(raw) > REQUEST_MAX_BYTES:
        return None, "too-large"
    try:
        req = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, "bad-json"
    return _validate_fields(req, spec, m.group(1))


def _validate_fields(req, spec: dict, expected_id: str) -> tuple[dict | None, str | None]:
    """Shared by the file inbox and the MCP transport: check a parsed request against run.json."""
    if not isinstance(req, dict) or set(req) != REQUEST_KEYS:
        return None, "bad-keys"
    if req["schema_version"] != REQUEST_SCHEMA_VERSION or type(req["schema_version"]) is not int:
        return None, "bad-schema-version"
    rid = req["request_id"]
    if not isinstance(rid, str) or not REQUEST_ID_RE.match(rid) or rid != expected_id:
        return None, "bad-request-id"
    model = req["model"]
    if not isinstance(model, str) or model not in spec["worker_models"] or not _kind(model):
        return None, "model-not-allowed"
    if req["effort"] not in _efforts_for(model):
        return None, "bad-effort"
    rung = _load("dispatch_rungs").MODEL_RUNG.get(model)
    if req["tier"] != rung:
        return None, "tier-model-mismatch"
    slots = req["slots"]
    if not isinstance(slots, dict) or not slots:
        return None, "bad-slots"
    for key, value in slots.items():
        if not SLOT_KEY_RE.match(key) or not isinstance(value, str):
            return None, "bad-slots"
        if key in BROKER_OWNED_SLOTS:
            return None, "broker-owned-slot"
    if _reject_credential_seeking(slots):
        return None, "credential-seeking"
    if _kind(model) == "claude" and not sandbox_available():
        return None, "no-sandbox-backend"
    return req, None


def _reject_credential_seeking(slots: dict) -> bool:
    """True when any slot value names a credential location or secret (D51 screen; not a sandbox)."""
    return any(CREDENTIAL_RE.search(v) for v in slots.values() if isinstance(v, str))


# Broker effort allowlist; ultra auto-delegates outside the control loop (SKILL.md:313) and xhigh stays refused.
BROKER_EFFORTS = ("low", "medium", "high", "max")


def _efforts_for(model: str) -> tuple:
    """Efforts from the model's agents_inc/models.json entry; Codex aliases map through runtime.MODEL_ALIASES."""
    from .runtime import MODEL_ALIASES
    try:
        models = json.loads((REPO_ROOT / "agents_inc" / "models.json").read_text(encoding="utf-8"))["models"]
    except (OSError, ValueError, KeyError):
        return ()
    entry = models.get(MODEL_ALIASES.get(model, model))
    if not isinstance(entry, dict):
        return ()
    efforts = entry.get("supported_efforts")
    allowed = tuple(efforts) if isinstance(efforts, list) else DEFAULT_EFFORTS
    return tuple(e for e in allowed if e in BROKER_EFFORTS)


def _write_request_result(run_dir: Path, rid: str, result: dict, report_text: str) -> None:
    """Write <id>.report.md then <id>.result.json; neither is ever overwritten."""
    report = run_dir / f"{rid}.report.md"
    _write_new(report, report_text)
    result = dict(result, schema_version=1, request_id=rid, report_path=str(report))
    _atomic_write_json(run_dir / f"{rid}.result.json", result)


def _process_request(run_dir: Path, rid: str, req: dict, spec: dict, home_repo: str | None = None) -> dict:
    """Reserve one fan-out slot, run one D47 dispatch, return the result fields."""
    started = _now()
    base = {"child_run_id": None, "outcome": None, "reason": None, "started_at": started}
    fan = spec["fan_out"]
    if fan["total"] == 0 or fan["width"] == 0:
        return dict(base, status="refused", dispatch_exit_code=REQ_REFUSED, reason="fan-out-zero", finished_at=_now())
    if spec["workers_spawned"] >= fan["total"]:
        return dict(base, status="refused", dispatch_exit_code=REQ_REFUSED, reason="fan-out-total-exhausted",
                    finished_at=_now())
    workers = run_dir / "workers"
    if workers.is_symlink() or (workers.exists() and not workers.is_dir()):
        raise BrokerFatal("workers directory is not a real directory")
    workers.mkdir(exist_ok=True)
    wdir = workers / rid
    wdir.mkdir()  # FileExistsError for a planted path: caller refuses
    slots = dict(req["slots"])
    slots["PERMISSION_MODE"] = spec.get("permission_mode", DEFAULT_PERMISSION_MODE)
    slots_path = wdir / "slots.json"
    _atomic_write_json(slots_path, slots)
    child_parent = wdir / "runs"
    spec["workers_spawned"] += 1  # reserved before launch
    _atomic_write_json(run_dir / "run.json", spec, overwrite=True)  # persist the reservation at once
    import argparse
    args = argparse.Namespace(slots=str(slots_path), model=req["model"], effort=req["effort"], cwd=spec["cwd"],
                              tier="grunt" if req["tier"] == "grunt" else None, run_dir=str(child_parent),
                              dry_run=False, resume=None, message=None, home_repo=home_repo)
    out = io.StringIO()
    crash = None
    global _BROKER_SAFE_WRITES, _BROKER_DENY
    launches_before = _LAUNCHES
    with contextlib.redirect_stdout(out):
        try:
            _BROKER_SAFE_WRITES = True
            codex_home = os.environ.get("CODEX_HOME")  # read, never logged
            _BROKER_DENY = (Path(run_dir).resolve(),) + ((Path(codex_home).resolve(),) if codex_home else ())
            rc = run(args)
        except Exception as exc:  # one bad request never stops the broker
            rc, crash = REQ_RED, f"dispatch-exception:{type(exc).__name__}"
        finally:
            _BROKER_SAFE_WRITES = False
            _BROKER_DENY = ()
    child = None
    children = sorted(p for p in child_parent.iterdir() if p.is_dir() and not p.is_symlink()) if child_parent.is_dir() else []
    if children:
        child = children[-1]
    cspec = {}
    if child is not None:
        with contextlib.suppress(OSError, ValueError):
            cspec = json.loads((child / "run.json").read_text(encoding="utf-8"))
    launched = _LAUNCHES > launches_before
    if not launched:
        spec["workers_spawned"] -= 1  # never launched: release the reservation
    code = rc if rc in REQ_STATUS else REQ_RED
    return dict(base, status=REQ_STATUS[code], dispatch_exit_code=code,
                child_run_id=cspec.get("run_id") or (child.name if child else None),
                outcome=cspec.get("outcome"), reason=crash or cspec.get("reason") or (None if code == REQ_GREEN else "dispatch-rc"),
                finished_at=_now(), status_line=out.getvalue().strip(),
                _report_path=str(child / "stdout.md") if (child and launched) else None)


def _handle_one(run_dir: Path, name: str, spec: dict, seen: set, home_repo: str | None) -> None:
    counts = spec["request_counts"]
    m = REQUEST_FILE_RE.match(name)
    rid = m.group(1) if m else None
    inbox = run_dir / INBOX
    req_path = inbox / name
    if rid and (rid in seen or os.path.lexists(str(run_dir / f"{rid}.result.json"))):
        counts["duplicate"] += 1
        _set_aside(req_path, f"{name}.duplicate-{secrets.token_hex(3)}")
        return
    req, reason = _validate_request(inbox, name, spec)
    if rid:
        seen.add(rid)
    if req is None:
        counts["refused"] += 1
        if rid:
            _write_request_result(run_dir, rid, {"status": "refused", "dispatch_exit_code": REQ_REFUSED,
                                                 "child_run_id": None, "outcome": None, "reason": reason,
                                                 "started_at": _now(), "finished_at": _now()},
                                  f"refused: {reason}\n")
        _set_aside(req_path, f"{name}.rejected")
        return
    result, report_text = _run_validated(run_dir, rid, req, spec, home_repo)
    _write_request_result(run_dir, rid, result, report_text)
    _set_aside(req_path, f"{name}.processed")


def _run_validated(run_dir: Path, rid: str, req: dict, spec: dict, home_repo: str | None) -> tuple[dict, str]:
    """Process one validated request and count it; return (result fields, report text). Both transports use this."""
    try:
        result = _process_request(run_dir, rid, req, spec, home_repo)
    except FileExistsError:
        result = {"status": "refused", "dispatch_exit_code": REQ_REFUSED, "child_run_id": None, "outcome": None,
                  "reason": "worker-dir-exists", "started_at": _now(), "finished_at": _now()}
    report_src = result.pop("_report_path", None)
    report_text = f"{result['status']}: {result.get('reason') or 'no worker report'}\n"
    if report_src:
        with contextlib.suppress(OSError):
            report_text = Path(report_src).read_text(encoding="utf-8")
    spec["request_counts"][result["status"]] = spec["request_counts"].get(result["status"], 0) + 1
    return result, report_text


def _set_aside(path: Path, new_name: str) -> None:
    with contextlib.suppress(OSError):
        os.rename(str(path), str(path.with_name(new_name)))


def init_broker_state(spec: dict, poll_interval: float | None = None, idle_timeout: float | None = None,
                      transport: str = "file") -> None:
    """Broker owns run.json from here on: in-memory state wins over any later on-disk edit."""
    spec.setdefault("workers_spawned", 0)
    if type(spec["workers_spawned"]) is not int or spec["workers_spawned"] < 0:
        spec["workers_spawned"] = 0
    counts = spec.get("request_counts")
    spec["request_counts"] = {k: (counts or {}).get(k, 0) if isinstance(counts, dict) else 0
                              for k in ("green", "red", "usage-error", "refused", "duplicate")}
    spec["broker"] = {"pid": os.getpid(), "started_at": _now(), "status": "serving", "transport": transport,
                      "poll_interval": poll_interval, "idle_timeout": idle_timeout}


def serve(run_dir: str | Path, poll_interval: float = 1.0, idle_timeout: float = 600.0,
          home_repo: str | None = None, sleep=time.sleep, clock=time.monotonic) -> int:
    """Broker loop. Exit 0 on lead.done or idle timeout, 1 on fatal I/O, 2 on bad arguments or run.json."""
    if poll_interval <= 0 or idle_timeout <= 0:
        print("dispatch --serve: --poll-interval and --idle-timeout must be positive", file=sys.stderr)
        return BROKER_USAGE
    root = Path(run_dir)
    if root.is_symlink() or not root.is_dir():
        print(f"dispatch --serve: run directory missing: {run_dir}", file=sys.stderr)
        return BROKER_USAGE
    root = root.resolve()
    inbox = root / INBOX
    if inbox.is_symlink() or not inbox.is_dir():
        print(f"dispatch --serve: {inbox} must be a real directory (the Lead's only write grant)", file=sys.stderr)
        return BROKER_USAGE
    try:
        spec = _load_run_manifest(root)
    except (OSError, ValueError) as exc:
        print(f"dispatch --serve: invalid run.json: {exc}", file=sys.stderr)
        return BROKER_USAGE
    init_broker_state(spec, poll_interval, idle_timeout)
    seen: set = set()
    try:
        _atomic_write_json(root / "run.json", spec, overwrite=True)
        last = clock()
        while True:
            names = sorted(n for n in os.listdir(str(inbox)) if REQUEST_FILE_RE.match(n))
            for name in names:
                _handle_one(root, name, spec, seen, home_repo)
                _atomic_write_json(root / "run.json", spec, overwrite=True)
                last = clock()
            if names:
                continue
            if os.path.lexists(str(inbox / LEAD_DONE)):
                stop = "lead-done"
                break
            if clock() - last >= idle_timeout:
                stop = "idle-timeout"
                break
            sleep(poll_interval)
        spec["broker"].update(status="stopped", stop=stop, stopped_at=_now())
        _atomic_write_json(root / "run.json", spec, overwrite=True)
    except (OSError, BrokerFatal) as exc:
        print(f"dispatch --serve: fatal: {exc}", file=sys.stderr)
        return BROKER_FATAL
    return BROKER_OK


def wait(run_dir: str | Path, request_id: str, timeout: float = 600.0, sleep=time.sleep,
         clock=time.monotonic) -> int:
    """Lead waiter: poll once per second for <run-dir>/<id>.result.json.
    Exit 0 and print the path when found, 124 on timeout, 2 on a bad request id or timeout."""
    if not isinstance(request_id, str) or not REQUEST_ID_RE.match(request_id) or timeout <= 0:
        print("dispatch --wait: bad request id or timeout", file=sys.stderr)
        return BROKER_USAGE
    path = Path(run_dir) / f"{request_id}.result.json"
    start = clock()
    while True:
        if path.is_file():
            print(path)
            return 0
        if clock() - start >= timeout:
            print(f"dispatch --wait: no result for {request_id} after {timeout:g} s", file=sys.stderr)
            return 124
        sleep(1)
