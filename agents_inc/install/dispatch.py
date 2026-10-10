"""`agents-inc dispatch`: render, lint, snapshot, launch, and verify one delegation (D45, D46, D47).

Only the status line goes to stdout. Everything else lands in the run directory.
"""
from __future__ import annotations
import base64
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
import threading
import time
import urllib.parse
from pathlib import Path

from agents_inc.datafiles import repo_file, repo_root

REPO_ROOT = repo_root()
SCRIPTS = repo_file("skills/workerbee/scripts")

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


def default_parent(cwd: Path | None = None) -> Path:
    """<cwd>/.scratch/agents-inc-runs when git ignores <cwd>/.scratch: a delegate under acceptEdits can write
    there, never outside cwd. Else the session scratchpad, TMPDIR, or /tmp."""
    if cwd is not None and (Path(cwd) / ".scratch").is_dir():
        with contextlib.suppress(OSError):
            res = subprocess.run(["git", "-C", str(cwd), "check-ignore", "-q", ".scratch"], capture_output=True)
            if res.returncode == 0:
                return Path(cwd) / ".scratch" / "agents-inc-runs"
    base = os.environ.get("CLAUDE_SCRATCHPAD") or os.environ.get("TMPDIR") or "/tmp"
    return Path(base) / "agents-inc-runs"


HOME_REPO_RE = re.compile(r"agents-inc home repo:\s*(\S+)", re.IGNORECASE)


def resolve_home_repo(home_repo: str | None, cwd: Path | None) -> str | None:
    """D46 ruling 8: --home-repo, then AGENTS_INC_HOME_REPO, then the first `agents-inc home repo: <path>` line
    in <cwd>/AGENTS.md (the path may start with ~)."""
    if home_repo:
        return home_repo
    if os.environ.get("AGENTS_INC_HOME_REPO"):
        return os.environ["AGENTS_INC_HOME_REPO"]
    try:
        text = (Path(cwd) / "AGENTS.md").read_text(encoding="utf-8") if cwd is not None else ""
    except (OSError, UnicodeDecodeError):
        return None
    m = HOME_REPO_RE.search(text)
    return str(Path(m.group(1).strip("`'\"")).expanduser()) if m else None


def new_run_id(model: str) -> str:
    return f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{model}-{secrets.token_hex(3)}"


def render(slots_path: Path, model: str | None = None) -> tuple[int, str, str]:
    """Render via render_dispatch.main() in-process; return (rc, prompt, stderr)."""
    module = _load("render_dispatch")
    out, err = io.StringIO(), io.StringIO()
    saved = sys.argv
    sys.argv = ["render_dispatch.py", "--slots", str(slots_path)] + (["--model", model] if model else [])
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


def claude_argv(model: str, permission_mode: str, resume: str | None = None,
                effort: str | None = None) -> list[str]:
    exe = shutil.which("claude") or "claude"
    argv = [exe, "-p", "--model", CLAUDE_MODELS[model], "--permission-mode", permission_mode,
            "--output-format", "json"]
    if effort:
        argv += ["--effort", effort]
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


def claude_sandbox_profile(cwd: Path, home: Path, tmpdir: str, deny_paths: tuple = (), write_ok: tuple = (),
                           read_ok: tuple = ()) -> str:
    """sandbox-exec profile: writes only to cwd, the child tmpdir, claude_scratch_dir(), /dev, the login keychain, and the
    CLAUDE_HOME_ALLOW subpaths; reads and writes denied under the D49 home deny list, ~/.claude.json*,
    and ~/.claude outside CLAUDE_HOME_ALLOW. deny_paths (the broker run directory, the Lead's isolated CODEX_HOME) are
    unreadable and unwritable except the child's own tmpdir, even when they sit under a granted cwd.
    D54: write_ok (the ask_lead channel) is also readable and writable; read_ok files (the ask_lead server and its
    config) are readable only."""
    h = _sb(home)
    claude_ok = [f"{h}/.claude/{name}" for name in CLAUDE_HOME_ALLOW]
    writable = [_sb(cwd), _sb(tmpdir), claude_scratch_dir(), f"{h}/Library/Keychains", "/dev"] + claude_ok
    writable += [_sb(w) for w in write_ok]
    keep = " ".join(f'(require-not (subpath "{w}"))' for w in writable)
    deny = " ".join(f'(subpath "{h}/{name}")' for name in CLAUDE_WORKER_DENY)
    claude_read = claude_ok + [f"{h}/.claude/{name}" for name in CLAUDE_HOME_READ]
    claude_keep = " ".join(f'(require-not (subpath "{w}"))' for w in claude_read)
    holes = "".join(f' (require-not (subpath "{_sb(p)}"))' for p in (tmpdir,) + tuple(write_ok))
    holes += "".join(f' (require-not (literal "{_sb(p)}"))' for p in read_ok)
    broker_deny = "".join(
        f'(deny file-read* file-write* (require-all (subpath "{_sb(d)}"){holes}))\n'
        for d in deny_paths)
    claude_write_denies = " ".join(f'(subpath "{h}/.claude/{n}")' for n in CLAUDE_HOME_READ)
    return ("(version 1)\n(allow default)\n"
            f"(deny file-write* (require-all {keep}))\n"
            + broker_deny +
            f"(deny file-read* file-write* {deny})\n"
            f'(deny file-read* file-write* (regex #"^{re.escape(h)}/\\.claude\\.json"))\n'
            f'(deny file-read* file-write* (require-all (subpath "{h}/.claude") {claude_keep}))\n'
            f'(deny file-write* {claude_write_denies})\n')


def _child_tmp(run_dir: Path, resume_turn: bool = False) -> Path:
    """Broker-owned per-child temp dir; the Worker's only TMPDIR (never inherited /tmp)."""
    tmp = Path(run_dir) / "tmp"
    if resume_turn and tmp.is_dir() and not tmp.is_symlink():
        return tmp.resolve()  # a resumed turn reuses the child's TMPDIR
    tmp.mkdir(mode=0o700)
    return tmp.resolve()


# D54 ask_lead channel: <child>/ask is the only broker-side path a Worker may write; the server script and its
# Claude config sit beside it, read-only to the Worker.
ASK_DIR = "ask"
WORKER_MCP = Path(__file__).resolve().parent / "worker_mcp.py"
ASK_TOOL = "mcp__agents_inc__ask_lead"
ASK_LEAD_NOTE = ("\nLEAD CHANNEL: to ask your Lead a question while you work, call the `ask_lead` tool of the `agents_inc` "
                 "MCP server (Claude: `mcp__agents_inc__ask_lead`; Codex: first call `tool_search` with query "
                 "\"agents_inc\", then `mcp__agents_inc__ask_lead`). It waits up to 30 minutes for the answer. "
                 "The Lead cannot message you otherwise.\n")


def _ask_channel(run_dir: Path, rid: str) -> dict:
    """Create <child>/ask and refresh the server copy and its Claude config (rewritten on every turn, so a
    Worker edit never survives into the next one). Return the paths the launch needs."""
    from .runtime import MCP_TOOL_TIMEOUT_SEC
    child = Path(run_dir)
    ask = child / ASK_DIR
    if ask.is_symlink():
        raise RuntimeError("ask-channel-is-symlink")
    ask.mkdir(mode=0o700, exist_ok=True)
    script = child / "worker_mcp.py"
    _replace_text(script, WORKER_MCP.read_text(encoding="utf-8"))
    args = [str(script.resolve()), "--run-dir", str(ask.resolve()), "--request-id", rid]
    config = child / "worker_mcp.json"
    _replace_text(config, json.dumps({"mcpServers": {"agents_inc": {
        "type": "stdio", "command": sys.executable, "args": args, "timeout": MCP_TOOL_TIMEOUT_SEC * 1000}}}, indent=1) + "\n")
    return {"ask": ask.resolve(), "script": script.resolve(), "config": config.resolve(), "rid": rid}


CODEX_WRITE_MODES = ("acceptEdits", "bypassPermissions")


def codex_write(slots: dict) -> bool:
    """A Codex delegate gets what a Claude subagent gets: tools and write access to cwd whenever PERMISSION_MODE
    (default acceptEdits) lets a Claude delegate edit. Slot CODEX_WRITE: no (or false) opts out; yes forces it on."""
    explicit = str(slots.get("CODEX_WRITE", "")).strip().lower()
    if explicit in ("yes", "true"):
        return True
    if explicit in ("no", "false"):
        return False
    return (slots.get("PERMISSION_MODE") or DEFAULT_PERMISSION_MODE) in CODEX_WRITE_MODES


def codex_network(slots: dict) -> bool:
    """#66: slot CODEX_NETWORK: yes (or true) gives a Codex delegate's tool commands outbound network access.
    Off by default. It needs tools, so it takes effect only with codex_write."""
    return str(slots.get("CODEX_NETWORK", "")).strip().lower() in ("yes", "true")


def launch(kind: str, model: str, effort: str | None, cwd: Path, prompt: str, run_dir: Path,
           permission_mode: str = DEFAULT_PERMISSION_MODE, resume: str | None = None,
           codex_write: bool = False, codex_network: bool = False) -> dict:
    """Run the delegate. Return {"rc", "stdout", "stderr", "argv", "session_id"}. resume: the Claude session id
    or the Codex thread id to continue. Under the broker, every Worker also gets the ask_lead server (D54)."""
    channel = _ask_channel(run_dir, _WORKER_ASK) if (_BROKER_SAFE_WRITES and _WORKER_ASK) else None
    if kind == "claude":
        argv = claude_argv(model, permission_mode, resume, effort)
        extra = {}
        if channel is not None:
            argv += ["--mcp-config", str(channel["config"]), "--strict-mcp-config", "--allowedTools", ASK_TOOL]
        if _BROKER_SAFE_WRITES:
            if not sandbox_available():
                raise RuntimeError("no-sandbox-backend")  # never run a broker Claude Worker unconfined
            env = worker_env(argv[0])
            env["TMPDIR"] = str(_child_tmp(run_dir, resume_turn=bool(resume)))
            extra["env"] = env
            profile = Path(run_dir) / ("sandbox.sb" if not resume else f"sandbox.{secrets.token_hex(3)}.sb")
            _wtext(profile, claude_sandbox_profile(
                Path(cwd), Path(env.get("HOME") or Path.home()), env["TMPDIR"], _BROKER_DENY,
                (channel["ask"],) if channel else (), (channel["script"], channel["config"]) if channel else ()))
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
        env["TMPDIR"] = str(_child_tmp(run_dir, resume_turn=bool(resume)))
    out, err = io.StringIO(), io.StringIO()
    thread: dict = {}
    worker = (channel["ask"], channel["rid"], channel["script"]) if channel else None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = run_codex(model, effort, cwd, io.StringIO(prompt), receipt, _efforts(paths.current.resolve()), env=env,
                       extra_deny=_BROKER_DENY if _BROKER_SAFE_WRITES else (), isolate_home=_BROKER_SAFE_WRITES,
                       thread_out=thread, resume_thread=resume, worker=worker,
                       tools=codex_write, write=codex_write, network=codex_write and codex_network,
                       # the prompt names snapshot.json; a run dir outside cwd (TMPDIR) is otherwise unreadable
                       extra_read=() if _BROKER_SAFE_WRITES else (Path(run_dir) / "snapshot.json",))
    return {"rc": rc, "stdout": out.getvalue(), "stderr": err.getvalue(),
            "argv": ["run_codex", model, effort, str(cwd)] + (["resume", resume] if resume else []),
            "session_id": thread.get("thread_id") or resume}


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
_WORKER_ASK: str | None = None  # D54: request id of the broker turn being launched; the Worker's ask_lead files use it


def _wtext(path: Path, text: str) -> None:
    if _BROKER_SAFE_WRITES:
        _write_new(path, text)
    else:
        path.write_text(text, encoding="utf-8")


def _replace_text(path: Path, text: str) -> None:
    """Atomic overwrite that never writes through a planted link (the link itself is replaced)."""
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


def _write_json(path: Path, data: dict) -> None:
    if _BROKER_SAFE_WRITES:
        _atomic_write_json(path, data, overwrite=True)
    else:
        path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def _verify(spec: dict, run_dir: Path, out_path: Path, name: str = "verify.txt") -> tuple[str, str, int]:
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
    _wtext(run_dir / name, f"report: {report}\n{log}\nsnapshot rc={src}\n{slog}")
    return report, snap, src


WORKERS_SPAWNED_RE = re.compile(r"^\W*(?:\[(?:verified|inferred|assumed)\]\s*)?workers spawned:\s*(\d+)\W*$", re.IGNORECASE | re.MULTILINE)


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
    home = resolve_home_repo(home_repo, Path(spec["cwd"]) if spec.get("cwd") else None)
    if not home:
        print("run spec not mirrored: no home repo", file=sys.stderr)
        return
    dest = Path(home) / "specs" / "consumers" / Path(spec["cwd"]).name / "runs" / spec["run_id"]
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("run.json", "prompt.md"):
        if (run_dir / name).is_file():
            shutil.copyfile(run_dir / name, dest / name)


def _finish(spec: dict, run_dir: Path, out_path: Path, result: dict, home_repo: str | None,
            verify_name: str = "verify.txt") -> int:
    report, snap, vrc = _verify(spec, run_dir, out_path, verify_name)
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


def _record_ledger_node(spec: dict, slots: dict) -> None:
    """Add a `dispatched` ledger node for this run (id = run id). A failure goes to run.json, never the outcome."""
    try:
        from .. import host_ledger  # lazy, like cli.py
        from .cli import _paths
        task = slots.get("TASK") if isinstance(slots, dict) else None
        if not host_ledger.record_dispatch_run(_paths().state, spec, task if isinstance(task, str) else None):
            spec["ledger_error"] = "ledger write failed"
    except Exception as exc:
        spec["ledger_error"] = f"{type(exc).__name__}: {exc}"


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
    # Claude without --effort keeps the claude CLI default (operator settings); record null, not a guess.
    effort = args.effort or (None if kind == "claude" else "medium")
    if kind == "claude" and effort is not None and effort not in _efforts_for(model):
        print(f"dispatch: effort {effort} not allowed for {model}, use one of: {' '.join(_efforts_for(model))}",
              file=sys.stderr)
        return EXIT_USAGE
    slots_path = Path(args.slots).resolve()
    try:
        slots = json.loads(slots_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"dispatch: cannot read slots: {exc}", file=sys.stderr)
        return EXIT_USAGE
    cwd = Path(args.cwd or os.getcwd()).resolve()
    run_id = new_run_id(model)
    run_dir = Path(args.run_dir or default_parent(cwd)).resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    if _BROKER_SAFE_WRITES:
        _wtext(run_dir / "slots.json", slots_path.read_text(encoding="utf-8"))
    else:
        shutil.copyfile(slots_path, run_dir / "slots.json")
    spec = {"run_id": run_id, "kind": kind, "slots": str(slots_path), "model": model, "effort": effort,
            "cwd": str(cwd), "chain": ["CoS", model], "snapshot": str(run_dir / "snapshot.json"),
            "gates": {"tier": args.tier, "allow": allow_paths(str(slots.get("FILES_IN_SCOPE", "")))},
            "permission_mode": slots.get("PERMISSION_MODE") or DEFAULT_PERMISSION_MODE,
            "codex_write": codex_write(slots),
            "codex_network": codex_network(slots),
            "rc": None, "outcome": None, "session_id": None}
    rc, prompt, err = render(slots_path, model)
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
    if _BROKER_SAFE_WRITES and _WORKER_ASK:
        prompt += ASK_LEAD_NOTE
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
    _record_ledger_node(spec, slots)
    global _LAUNCHES
    _LAUNCHES += 1
    result = launch(kind, model, effort, cwd, prompt, run_dir, spec["permission_mode"],
                    **({"codex_write": True} if spec["codex_write"] else {}),
                    **({"codex_network": True} if spec["codex_network"] else {}))
    out_path = run_dir / "stdout.md"
    _wtext(out_path, result["stdout"])
    _wtext(run_dir / "stderr.txt", result["stderr"])
    spec.update(rc=result["rc"], session_id=result.get("session_id"), argv=result.get("argv"))
    return _finish(spec, run_dir, out_path, result, getattr(args, "home_repo", None))


def resume(args) -> int:
    """Send one more turn to a finished delegate: Claude via its session id, Codex via its thread id (D54)."""
    cwd = Path(getattr(args, "cwd", None) or os.getcwd()).resolve()
    run_dir = Path(args.run_dir or default_parent(cwd)).resolve() / args.resume
    try:
        spec = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(f"dispatch: no run.json for {args.resume}", file=sys.stderr)
        return EXIT_USAGE
    kind = spec.get("kind")
    if kind not in ("claude", "codex") or not spec.get("session_id"):
        print(f"dispatch: no session id recorded for {args.resume}; cannot resume", file=sys.stderr)
        return EXIT_USAGE
    if not args.message:
        print("dispatch: --resume needs --message", file=sys.stderr)
        return EXIT_USAGE
    result = launch(kind, spec["model"], spec["effort"], Path(spec["cwd"]), args.message, run_dir,
                    spec.get("permission_mode", DEFAULT_PERMISSION_MODE), resume=spec["session_id"],
                    **({"codex_write": True} if spec.get("codex_write") is True else {}),
                    **({"codex_network": True} if spec.get("codex_network") is True else {}))
    n = len(spec.get("resumes", [])) + 1
    out_path = run_dir / f"stdout.{n}.md"
    _wtext(out_path, result["stdout"])
    _wtext(run_dir / f"stderr.{n}.txt", result["stderr"])
    spec.setdefault("resumes", []).append({"rc": result["rc"], "out": str(out_path)})
    spec["rc"] = result["rc"]
    if result.get("session_id"):
        spec["session_id"] = result["session_id"]
    return _finish(spec, run_dir, out_path, result, getattr(args, "home_repo", None), f"verify.{n}.txt")


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
# Efforts for a model without `supported_efforts` in models.json (Claude: passed as `claude -p --effort`).
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
    req, reason = _read_request(inbox, name)
    if req is None:
        return None, reason
    return _validate_fields(req, spec, REQUEST_FILE_RE.match(name).group(1))


def _read_request(inbox: Path, name: str) -> tuple[object, str | None]:
    """Return (parsed JSON, None) or (None, reason) for <inbox>/<name>: regular file, size limit, valid JSON."""
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
        return json.loads(raw.decode("utf-8")), None
    except (UnicodeDecodeError, ValueError):
        return None, "bad-json"


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
    with _SPEC_LOCK:
        spec["workers_spawned"] += 1  # reserved before launch
        _atomic_write_json(run_dir / "run.json", spec, overwrite=True)  # persist the reservation at once
    import argparse
    args = argparse.Namespace(slots=str(slots_path), model=req["model"], effort=req["effort"], cwd=spec["cwd"],
                              tier="grunt" if req["tier"] == "grunt" else None, run_dir=str(child_parent),
                              dry_run=False, resume=None, message=None, home_repo=home_repo)
    out = io.StringIO()
    launches_before = _LAUNCHES
    rc, crash = _in_worker_scope(run_dir, rid, out, lambda: run(args))
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
        with _SPEC_LOCK:
            spec["workers_spawned"] -= 1  # never launched: release the reservation
    code = rc if rc in REQ_STATUS else REQ_RED
    return dict(base, status=REQ_STATUS[code], dispatch_exit_code=code,
                child_run_id=cspec.get("run_id") or (child.name if child else None),
                outcome=cspec.get("outcome"), reason=crash or cspec.get("reason") or (None if code == REQ_GREEN else "dispatch-rc"),
                finished_at=_now(), status_line=out.getvalue().strip(),
                _report_path=str(child / "stdout.md") if (child and launched) else None)


def _kind_keys(req, keys: frozenset) -> bool:
    """D54 request kinds: exactly keys, plus an optional schema_version 1."""
    if not isinstance(req, dict) or set(req) - {"schema_version"} != keys:
        return False
    return "schema_version" not in req or (type(req["schema_version"]) is int and req["schema_version"] == 1)


def _handle_one(run_dir: Path, name: str, spec: dict, seen: set, home_repo: str | None, issued: set | None = None,
                busy: bool = False):
    """Handle one inbox file. Return None when handled, "busy" when a dispatch or resume must wait for the
    running turn (answers never wait), or a Turn to start."""
    issued = set() if issued is None else issued
    counts = spec["request_counts"]
    m = REQUEST_FILE_RE.match(name)
    rid = m.group(1) if m else None
    inbox = run_dir / INBOX
    req_path = inbox / name
    if rid and (rid in seen or os.path.lexists(str(run_dir / f"{rid}.result.json"))):
        counts["duplicate"] += 1
        _set_aside(req_path, f"{name}.duplicate-{secrets.token_hex(3)}")
        return None
    raw, reason = _read_request(inbox, name)
    kind = raw.get("kind") if isinstance(raw, dict) else None
    extra = {}
    if kind == "answer":
        if not _kind_keys(raw, ANSWER_KEYS):
            reason = "bad-keys"
        elif raw["request_id"] not in issued:
            reason = "unknown-request"
        else:
            fields, reason = answer_question(run_dir, spec, raw["request_id"], raw["question_n"], raw["text"])
            if reason is None:
                seen.add(rid)
                now = _now()
                _write_request_result(run_dir, rid, dict(fields, answered_request_id=fields["request_id"],
                                                         started_at=now, finished_at=now), "answered\n")
                _set_aside(req_path, f"{name}.processed")
                return None
        req = None
    elif busy and raw is not None:
        return "busy"
    elif kind == "resume":
        req, plan = None, None
        if not _kind_keys(raw, RESUME_KEYS):
            reason = "bad-keys"
        else:
            plan, reason = plan_resume(run_dir, spec, raw["request_id"], raw["message"], issued.__contains__)
        if plan is not None and plan["new_rid"] != rid:
            plan, reason, extra = None, "bad-request-id", {"expected_request_id": plan["new_rid"]}
        if plan is not None:
            seen.add(rid)
            issued.add(rid)
            with _SPEC_LOCK:
                spec.setdefault("resume_of", {})[rid] = plan["root"]
            _set_aside(req_path, f"{name}.processed")
            message = raw["message"]
            return Turn(run_dir, rid, lambda: run_resume(run_dir, plan, message, spec, home_repo), spec,
                        lambda: _atomic_write_json(run_dir / "run.json", spec, overwrite=True), (OSError, BrokerFatal))
    else:
        req, reason = (None, reason) if raw is None else _validate_fields(raw, spec, rid)
    if rid:
        seen.add(rid)
    if req is None:
        counts["refused"] += 1
        if rid:
            _write_request_result(run_dir, rid, dict({"status": "refused", "dispatch_exit_code": REQ_REFUSED,
                                                      "child_run_id": None, "outcome": None, "reason": reason,
                                                      "started_at": _now(), "finished_at": _now()}, **extra),
                                  f"refused: {reason}\n")
        _set_aside(req_path, f"{name}.rejected")
        return None
    issued.add(rid)
    _set_aside(req_path, f"{name}.processed")
    return Turn(run_dir, rid, lambda: _run_validated(run_dir, rid, req, spec, home_repo), spec,
                lambda: _atomic_write_json(run_dir / "run.json", spec, overwrite=True), (OSError, BrokerFatal))


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
    with _SPEC_LOCK:
        spec["request_counts"][result["status"]] = spec["request_counts"].get(result["status"], 0) + 1
    return result, report_text


def _in_worker_scope(run_dir: Path, rid: str, out, fn) -> tuple[int, str | None]:
    """Run fn (a D47 run or resume) with the broker's Worker confinement on; return (rc, crash reason)."""
    global _BROKER_SAFE_WRITES, _BROKER_DENY, _WORKER_ASK
    with contextlib.redirect_stdout(out):
        try:
            _BROKER_SAFE_WRITES, _WORKER_ASK = True, rid
            codex_home = os.environ.get("CODEX_HOME")  # read, never logged
            _BROKER_DENY = (Path(run_dir).resolve(),) + ((Path(codex_home).resolve(),) if codex_home else ())
            return fn(), None
        except Exception as exc:  # one bad request never stops the broker
            return REQ_RED, f"dispatch-exception:{type(exc).__name__}"
        finally:
            _BROKER_SAFE_WRITES, _WORKER_ASK = False, None
            _BROKER_DENY = ()


# ---------------------------------------------------------------------------
# D54 delegate turns. A Worker turn (dispatch or resume) runs in a thread so the broker keeps serving while the
# Worker waits on ask_lead: wait returns needs-lead with the screened question, answer writes the reply into the
# Worker's channel. One turn at a time (the confinement state above is process-wide). A resume continues a
# finished Worker in its own child run directory under a new id <root>-r<n>; it never charges fan-out.
# ---------------------------------------------------------------------------
_SPEC_LOCK = threading.RLock()  # run.json state is shared by the serve loop and the turn thread
RESUME_KEYS = frozenset({"kind", "request_id", "message"})
ANSWER_KEYS = frozenset({"kind", "request_id", "question_n", "text"})
QUESTION_MAX_BYTES = 16 * 1024
NEEDS_LEAD_EXIT = 10  # `dispatch --wait`: a Worker asked a question; answer it, then wait again


def resume_cap(model: str) -> int:
    """Operator ruling 2026-10-04: 1 resume for a Grunt Worker, 2 for Workhorse and above."""
    return 1 if _load("dispatch_rungs").MODEL_RUNG.get(model) == "grunt" else 2


class Turn:
    """One Worker turn in a thread. fn returns (result fields, report text); the result is written when it ends.
    fatal: exception types re-raised to the owner (the file broker stops on them); others become a red result."""

    def __init__(self, run_dir: Path, rid: str, fn, spec: dict, save, fatal: tuple = ()):
        self.run_dir, self.rid, self.fn, self.spec, self.save, self.fatal = run_dir, rid, fn, spec, save, fatal
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "Turn":
        self.thread.start()
        return self

    def alive(self) -> bool:
        return self.thread.is_alive()

    def _run(self) -> None:
        try:
            result, report = self.fn()
        except self.fatal as exc:
            self.error = exc
            return
        except Exception as exc:
            reason = f"exception:{type(exc).__name__}"
            result, report = {"status": "red", "dispatch_exit_code": REQ_RED, "child_run_id": None, "outcome": None,
                              "reason": reason, "started_at": _now(), "finished_at": _now()}, f"red: {reason}\n"
        try:
            with _SPEC_LOCK:
                _write_request_result(self.run_dir, self.rid, result, report)
                self.save()
        except Exception as exc:
            self.error = exc


def _root_of(spec: dict, rid: str) -> str:
    return spec.get("resume_of", {}).get(rid, rid)


def _child_dir(run_dir: Path, root: str) -> Path | None:
    """The Worker's child run directory under workers/<root>/runs (broker-owned), or None."""
    runs = Path(run_dir) / "workers" / root / "runs"
    if not runs.is_dir() or runs.is_symlink():
        return None
    children = sorted(p for p in runs.iterdir() if p.is_dir() and not p.is_symlink())
    return children[-1] if children else None


def _read_small(path: Path, limit: int) -> bytes | None:
    """Read at most limit+1 bytes from a regular file without following a link; None when absent or unreadable."""
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    with os.fdopen(fd, "rb") as fh:
        import stat as _stat
        if not _stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
            return None
        return fh.read(limit + 1)


def screen_text(text: str, limit: int = QUESTION_MAX_BYTES) -> str:
    """What the Lead may see of Worker text: at most limit bytes, and no environment value of 8 or more
    characters, plain or encoded as base64 (standard or URL-safe, with or without padding), percent-encoding or
    hex (each form is replaced by [redacted]; spec 018 FR-011)."""
    text = text.encode("utf-8")[:limit].decode("utf-8", "ignore")
    forms = set()
    for value in {v for v in os.environ.values() if len(v) >= 8}:
        raw = value.encode()
        b64, url = base64.b64encode(raw).decode(), base64.urlsafe_b64encode(raw).decode()
        forms.update((value, b64, b64.rstrip("="), url, url.rstrip("="), urllib.parse.quote(value, safe=""),
                      raw.hex(), raw.hex().upper()))
    for form in sorted(forms, key=len, reverse=True):
        text = text.replace(form, "[redacted]")
    return text


def relay_question(run_dir: Path, spec: dict, rid: str) -> dict | None:
    """Find the lowest unanswered question of turn rid in the Worker's channel, copy it screened to
    <run-dir>/<rid>.question.<n>.json (once; counted in run.json `questions`), and return the needs-lead fields."""
    child = _child_dir(run_dir, _root_of(spec, rid))
    if child is None:
        return None
    ask, n = child / ASK_DIR, 1
    while os.path.lexists(str(ask / f"{rid}.question.{n}.json")):
        if not os.path.lexists(str(Path(run_dir) / f"{rid}.answer.{n}.json")):
            break
        n += 1
    else:
        return None
    lead_copy = Path(run_dir) / f"{rid}.question.{n}.json"
    if not lead_copy.is_file():
        raw = _read_small(ask / f"{rid}.question.{n}.json", QUESTION_MAX_BYTES * 2)
        try:
            question = json.loads(raw.decode("utf-8"))["question"] if raw else None
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            question = None
        text = screen_text(question) if isinstance(question, str) else "(question unreadable; answer or tell the Worker to stop)"
        with _SPEC_LOCK:
            try:
                _atomic_write_json(lead_copy, {"request_id": rid, "question_n": n, "question": text, "relayed_at": _now()})
            except FileExistsError:
                pass
            else:
                spec["questions"] = spec.get("questions", 0) + 1
    data = json.loads(lead_copy.read_text(encoding="utf-8"))
    return {"status": "needs-lead", "request_id": rid, "question_n": n, "question": data.get("question", "")}


def pending_question(run_dir: Path, rid: str) -> dict | None:
    """The lowest relayed question of rid with no answer yet, as needs-lead fields; None when there is none."""
    n = 1
    while (Path(run_dir) / f"{rid}.question.{n}.json").is_file():
        if not os.path.lexists(str(Path(run_dir) / f"{rid}.answer.{n}.json")):
            raw = _read_small(Path(run_dir) / f"{rid}.question.{n}.json", QUESTION_MAX_BYTES * 2)
            try:
                question = json.loads(raw.decode("utf-8")).get("question", "") if raw else ""
            except (ValueError, AttributeError, UnicodeDecodeError):
                question = ""
            return {"status": "needs-lead", "request_id": rid, "question_n": n, "question": question}
        n += 1
    return None


def answer_question(run_dir: Path, spec: dict, rid, n, text) -> tuple[dict, str | None]:
    """Write the Lead's answer into the Worker's channel. Return (fields, refusal reason or None)."""
    if not isinstance(rid, str) or not REQUEST_ID_RE.match(rid):
        return {}, "bad-request-id"
    if isinstance(n, bool) or not isinstance(n, int) or n < 1 or not isinstance(text, str):
        return {}, "bad-arguments"
    if len(text.encode("utf-8")) > REQUEST_MAX_BYTES:
        return {}, "oversize"
    if _reject_credential_seeking({"TEXT": text}):
        return {}, "credential-seeking"
    if not (Path(run_dir) / f"{rid}.question.{n}.json").is_file():
        return {}, "unknown-question"
    child = _child_dir(run_dir, _root_of(spec, rid))
    if child is None:
        return {}, "unknown-question"
    now = _now()
    try:
        _write_new(Path(run_dir) / f"{rid}.answer.{n}.json", json.dumps({"request_id": rid, "question_n": n,
                                                                          "answered_at": now}) + "\n")
    except FileExistsError:
        return {}, "already-answered"
    try:
        _write_new(child / ASK_DIR / f"{rid}.answer.{n}.json", json.dumps({"answer": text, "answered_at": now}) + "\n")
    except OSError:
        return {}, "already-answered"  # a planted file or link in the channel: the Worker reads nothing new
    return {"status": "answered", "request_id": rid, "question_n": n}, None


def plan_resume(run_dir: Path, spec: dict, rid, message, known) -> tuple[dict | None, str | None]:
    """Check a resume request. known(rid) says whether this broker issued rid. Return (plan, None) with the
    root id, new id, turn number, and child directory, or (None, reason)."""
    if not isinstance(rid, str) or not REQUEST_ID_RE.match(rid):
        return None, "bad-request-id"
    if not isinstance(message, str) or not message.strip():
        return None, "bad-message"
    if len(json.dumps({"request_id": rid, "message": message}).encode("utf-8")) > REQUEST_MAX_BYTES:
        return None, "oversize"
    if _reject_credential_seeking({"MESSAGE": message}):
        return None, "credential-seeking"
    if not known(rid):
        return None, "unknown-request"
    result_path = Path(run_dir) / f"{rid}.result.json"
    if not result_path.is_file() or result_path.is_symlink():
        return None, "request-running"
    try:
        status = json.loads(result_path.read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError):
        return None, "unknown-request"
    if status not in ("green", "red"):
        return None, "not-resumable"
    root = _root_of(spec, rid)
    child = _child_dir(run_dir, root)
    try:
        cspec = json.loads((child / "run.json").read_text(encoding="utf-8")) if child else None
    except (OSError, ValueError):
        cspec = None
    if not cspec or not cspec.get("session_id"):
        return None, "no-session"
    turn = len(cspec.get("resumes", [])) + 1
    if turn > resume_cap(cspec.get("model", "")):
        return None, "resume-cap"
    new_rid = f"{root}-r{turn}"
    if not REQUEST_ID_RE.match(new_rid):
        return None, "bad-request-id"
    return {"root": root, "new_rid": new_rid, "turn": turn, "child": child, "parent": rid}, None


def run_resume(run_dir: Path, plan: dict, message: str, spec: dict, home_repo: str | None) -> tuple[dict, str]:
    """Run one resume turn on the Worker's child run directory; return (result fields, report text)."""
    import argparse
    child = plan["child"]
    args = argparse.Namespace(resume=child.name, message=message, run_dir=str(child.parent), cwd=spec["cwd"],
                              home_repo=home_repo)
    started, out = _now(), io.StringIO()
    rc, crash = _in_worker_scope(run_dir, plan["new_rid"], out, lambda: resume(args))
    cspec = {}
    with contextlib.suppress(OSError, ValueError):
        cspec = json.loads((child / "run.json").read_text(encoding="utf-8"))
    turns = cspec.get("resumes") or []
    ran = len(turns) >= plan["turn"]
    code = rc if rc in REQ_STATUS else REQ_RED
    result = {"status": REQ_STATUS[code], "dispatch_exit_code": code, "child_run_id": child.name,
              "outcome": cspec.get("outcome") if ran else None,
              "reason": crash or (cspec.get("reason") if ran else None) or (None if code == REQ_GREEN else "dispatch-rc"),
              "started_at": started, "finished_at": _now(), "status_line": out.getvalue().strip(),
              "resumed_from": plan["root"], "turn": plan["turn"]}
    report = f"{result['status']}: {result.get('reason') or 'no worker report'}\n"
    if ran:
        with contextlib.suppress(OSError):
            report = (child / f"stdout.{plan['turn']}.md").read_text(encoding="utf-8")
    with _SPEC_LOCK:
        spec["request_counts"][result["status"]] = spec["request_counts"].get(result["status"], 0) + 1
        spec["resumes"] = spec.get("resumes", 0) + 1
    return result, report


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
    for key in ("resumes", "questions"):  # D54 counters
        if type(spec.get(key)) is not int or spec[key] < 0:
            spec[key] = 0
    if not isinstance(spec.get("resume_of"), dict):
        spec["resume_of"] = {}
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
    issued: set = set()
    turn = None

    def save():
        with _SPEC_LOCK:
            _atomic_write_json(root / "run.json", spec, overwrite=True)
    try:
        save()
        last = clock()
        while True:
            if turn is not None and not turn.alive():
                turn.thread.join()
                if turn.error is not None:
                    raise turn.error if isinstance(turn.error, (OSError, BrokerFatal)) else BrokerFatal(str(turn.error))
                turn = None
                save()
                last = clock()
            if turn is not None:  # a Worker is running: relay its question, never stop the broker under it
                with contextlib.suppress(ValueError):
                    if relay_question(root, spec, turn.rid) is not None:
                        save()
                last = clock()
            names = sorted(n for n in os.listdir(str(inbox)) if REQUEST_FILE_RE.match(n))
            progressed = False
            for name in names:
                got = _handle_one(root, name, spec, seen, home_repo, issued, busy=turn is not None)
                if got == "busy":
                    continue
                progressed = True
                if isinstance(got, Turn):
                    turn = got.start()
                save()
                last = clock()
            if progressed:
                continue
            if turn is not None:
                turn.thread.join(poll_interval)  # wakes early when the turn ends
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
    Exit 0 and print the path when found, 10 and print the needs-lead JSON when the Worker asked a question the
    Lead has not answered (D54), 124 on timeout, 2 on a bad request id or timeout."""
    if not isinstance(request_id, str) or not REQUEST_ID_RE.match(request_id) or timeout <= 0:
        print("dispatch --wait: bad request id or timeout", file=sys.stderr)
        return BROKER_USAGE
    path = Path(run_dir) / f"{request_id}.result.json"
    start = clock()
    while True:
        if path.is_file():
            print(path)
            return 0
        asked = pending_question(Path(run_dir), request_id)
        if asked is not None:
            print(json.dumps(asked))
            return NEEDS_LEAD_EXIT
        if clock() - start >= timeout:
            print(f"dispatch --wait: no result for {request_id} after {timeout:g} s", file=sys.stderr)
            return 124
        sleep(1)
