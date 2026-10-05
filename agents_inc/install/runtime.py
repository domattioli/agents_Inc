"""Direct Codex execution with an install-recorded executable only."""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import json
import sys

def _aliases_from_routing() -> dict[str, str]:
    """D52: alias -> slug from routing.json (the single source); alias is the text after the slug's last hyphen."""
    path = Path(__file__).resolve().parents[1] / "routing.json"
    tiers = json.loads(path.read_text(encoding="utf-8"))["tiers"]
    slugs = [tier["codex"] for tier in tiers.values() if tier.get("codex")]
    return {slug.rsplit("-", 1)[-1]: slug for slug in slugs}


# Built-in DEFAULTS only; resolution goes through load_model_map().
MODEL_ALIASES = _aliases_from_routing()


def _read_map(raw: str) -> dict[str, str]:
    """Parse a JSON object string, or a path to a JSON file. Accepts {"alias": "slug"} or {"models": {...}}."""
    raw = raw.strip()
    text = raw if raw.startswith("{") else Path(raw).expanduser().read_text()
    data = json.loads(text)
    if isinstance(data, dict) and isinstance(data.get("models"), dict):
        data = data["models"]
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) and v for k, v in data.items()):
        raise ValueError("model map must be a JSON object of alias -> slug strings")
    return data


def load_model_map(roster: Path | None = None, env: dict | None = None) -> dict[str, str]:
    """Merge model aliases, lowest to highest precedence: built-in defaults < roster file < AGENTS_INC_MODEL_MAP.

    Roster: JSON file (default ~/.config/agents-inc/roster.json), either {"alias": "slug"} or {"models": {...}}.
    AGENTS_INC_MODEL_MAP: a JSON object string (starts with "{"), otherwise a path to a JSON file.
    A malformed or unreadable override is skipped with a message on stderr; it never raises.
    """
    env = os.environ if env is None else env
    merged = dict(MODEL_ALIASES)
    if roster is None:
        from .paths import InstallPaths
        roster = InstallPaths.for_home(Path(env.get("HOME") or Path.home())).roster
    sources = []
    if Path(roster).is_file(): sources.append((f"roster {roster}", lambda: _read_map(str(roster))))
    if env.get("AGENTS_INC_MODEL_MAP"): sources.append(("AGENTS_INC_MODEL_MAP", lambda: _read_map(env["AGENTS_INC_MODEL_MAP"])))
    for label, read in sources:
        try:
            merged.update(read())
        except (OSError, ValueError) as exc:
            print(f"WARN: ignoring malformed model map from {label}: {exc}; using defaults", file=sys.stderr)
    return merged


def resolve_executable(name: str, search_path: str | None = None) -> Path:
    candidate = shutil.which(name, path=search_path)
    if not candidate:
        raise FileNotFoundError(f"WB_CLI_NOT_FOUND: {name}; run agents-inc repair")
    path = Path(candidate).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise FileNotFoundError(f"WB_CLI_NOT_FOUND: {name}; run agents-inc repair")
    return path


# D49: Codex tool access by rung. Grunt (luna) and unknown aliases stay tool-free (fail closed).
TOOL_RUNGS = {"astra": "Executive", "sol": "Orchestrator", "terra": "Workhorse"}
HARD_DENY = (".ssh", ".config", ".claude", ".codex-bridge", ".local", ".aws", ".gnupg", ".netrc")
PROFILE = "agents_inc_d49"
TOOL_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
# Nested seatbelts fail on macOS (sandbox_apply: Operation not permitted), so an outer sandbox-exec would disable
# Codex's own seatbelt. The read deny therefore rides Codex's permission profile, which its seatbelt enforces.


def tools_for(model: str, no_tools: bool = False, tools: bool = False) -> bool:
    """D49: on by default for astra, sol, terra; --no-tools wins; --tools on luna or a raw slug raises."""
    if no_tools:
        return False
    if model in TOOL_RUNGS:
        return True
    if tools:
        raise ValueError(f"--tools is allowed only for astra, sol, terra; not {model!r}")
    return False


def _toml_key(path) -> str:
    text = os.path.realpath(str(path))
    if any(ch in text for ch in ('"', "\\", "\n")):
        raise ValueError(f"path not expressible in permission profile: {text!r}")
    return f'"{text}"'


def permission_profile(cwd: Path, write: bool, home: Path | None = None,
                       write_dir: Path | None = None, extra_deny: tuple = ()) -> dict[str, str]:
    """Filesystem grants for tool commands. Anything absent (all of HOME except cwd) is unreadable.
    D51: with write_dir (the Lead's run directory), write goes to write_dir/inbox only; write_dir and cwd stay
    read, so run.json, workers/ and results are broker-owned. Without it, --write grants cwd (legacy)."""
    home = Path(home or Path.home())
    if write_dir is not None and not write:
        raise ValueError("--run-dir needs --write")
    grants = {'":minimal"': "read", _toml_key("/opt/homebrew"): "read", _toml_key("/tmp"): "read",
              _toml_key("/private/tmp"): "read",
              _toml_key(cwd): "write" if (write and write_dir is None) else "read"}
    if write_dir is not None:
        if (Path(write_dir) / "inbox").is_symlink():
            raise ValueError(f"run-dir inbox must not be a symlink: {Path(write_dir) / 'inbox'}")
        grants[_toml_key(write_dir)] = "read"
        grants[_toml_key(Path(write_dir) / "inbox")] = "write"
    for name in HARD_DENY:
        grants[f'"{os.path.realpath(home)}/{name}"'] = "none"
    for path in extra_deny:  # e.g. the isolated Lead CODEX_HOME
        grants[_toml_key(path)] = "none"
    return grants


def permission_args(cwd: Path, write: bool, home: Path | None = None, write_dir: Path | None = None,
                    extra_deny: tuple = ()) -> list[str]:
    body = ", ".join(f"{k}={chr(34)}{v}{chr(34)}"
                     for k, v in permission_profile(cwd, write, home, write_dir, extra_deny).items())
    return ["-c", f'default_permissions="{PROFILE}"', "-c", f"permissions.{PROFILE}.filesystem={{{body}}}"]


MCP_BROKER = Path(__file__).resolve().parent / "mcp_broker.py"
MCP_STARTUP_TIMEOUT_SEC = 30  # Codex waits for the tool catalog before the turn starts
MCP_TOOL_TIMEOUT_SEC = 3600  # Codex's 60 s default would cut a Worker run short


def _toml_str(text: str) -> str:
    if any(ch in text for ch in ('"', "\\", "\n")):
        raise ValueError(f"value not expressible in a TOML string: {text!r}")
    return f'"{text}"'


def lead_args(model: str, lead_dir: Path, broker: Path | None = None, codex_home: Path | None = None,
              home_repo: str | None = None) -> list[str]:
    """D51 MCP transport: -c overrides that start mcp_broker.py as the Lead's `agents_inc` MCP server.
    Only astra, sol, terra; a raw slug or luna raises. JSON strings and arrays are valid TOML here."""
    if model not in TOOL_RUNGS:
        raise ValueError(f"--lead is allowed only for astra, sol, terra; not {model!r}")
    if not Path(lead_dir).is_dir():
        raise ValueError(f"--lead run directory missing: {lead_dir}")
    script = str(broker or MCP_BROKER)
    prefix = "mcp_servers.agents_inc"
    server_args = [script, "--run-dir", str(Path(lead_dir).resolve())] + (["--home-repo", str(home_repo)] if home_repo else [])
    # Codex starts stdio MCP servers with a cleared env, so CODEX_HOME (the Worker deny) goes through the env table.
    env_table = ["-c", f"{prefix}.env={{CODEX_HOME={_toml_str(os.path.realpath(codex_home))}}}"] if codex_home else []
    return ["-c", f"{prefix}.command={json.dumps(sys.executable)}",
            "-c", f"{prefix}.args={json.dumps(server_args)}",
            "-c", f"{prefix}.tool_timeout_sec={MCP_TOOL_TIMEOUT_SEC}",
            "-c", f'{prefix}.default_tools_approval_mode="approve"',
            "-c", f"{prefix}.required=true",
            "-c", f'{prefix}.startup_readiness="catalog"',
            "-c", f"{prefix}.startup_timeout_sec={MCP_STARTUP_TIMEOUT_SEC}"] + env_table


def lead_codex_home(slug: str) -> Path:
    """Isolated CODEX_HOME for a broker Lead: only auth.json and sessions (symlinks) and a one-line config.toml,
    so the operator's MCP servers and config never load. Never copies or reads auth.json. Caller removes it
    with shutil.rmtree (does not follow symlinks)."""
    real = Path.home() / ".codex"
    auth = real / "auth.json"
    if not auth.is_file():
        raise FileNotFoundError(f"WB_CODEX_AUTH_MISSING: {auth} not found; log in to Codex first")
    if any(ch in slug for ch in ('"', "\\", "\n")):
        raise ValueError(f"model slug not expressible in config.toml: {slug!r}")
    (real / "sessions").mkdir(exist_ok=True)
    home = Path(tempfile.mkdtemp(prefix="agents-inc-lead-home-"))
    try:
        os.chmod(home, 0o700)
        (home / "auth.json").symlink_to(auth)
        (home / "sessions").symlink_to(real / "sessions")
        (home / "config.toml").write_text(f'model = "{slug}"\n', encoding="utf-8")
    except BaseException:
        try:
            shutil.rmtree(home)
        except OSError:
            pass  # the original error below is the one that matters
        raise
    return home


def lead_env(executable: Path, codex_home: Path, base: dict | None = None) -> dict:
    """Explicit minimal env for a broker Lead (and so its MCP server child): the Worker shape (fixed PATH plus
    the codex directory; HOME, USER, TERM, LANG, TMPDIR), no *KEY*/*TOKEN*/*SECRET* variable, plus CODEX_HOME."""
    from .dispatch import worker_env
    env = worker_env(str(executable), os.environ if base is None else base)
    env["CODEX_HOME"] = str(codex_home)
    return env


def build_codex_argv(executable: Path, model: str, effort: str, cwd: Path, supported_efforts: dict[str, list[str]],
                     model_map: dict[str, str] | None = None, tools: bool = False, write: bool = False,
                     write_dir: Path | None = None, lead_dir: Path | None = None,
                     extra_deny: tuple = (), lead_home: Path | None = None, home_repo: str | None = None) -> list[str]:
    slug = (model_map if model_map is not None else load_model_map()).get(model, model if model in supported_efforts else None)
    if not slug:
        raise ValueError(f"unknown Codex model alias: {model}")
    if effort not in supported_efforts.get(slug, []):
        raise ValueError(f"unsupported effort {effort!r} for {slug}")
    if not executable.is_absolute():
        raise ValueError("Codex executable must be absolute")
    if write and not tools:
        raise ValueError("--write needs --tools (rung astra, sol, or terra, without --no-tools)")
    common = ["--skip-git-repo-check", "-C", str(cwd), "-c", f"model_reasoning_effort={effort}",
              "-c", 'shell_environment_policy.inherit="none"', "-c", 'web_search="disabled"']
    if lead_dir is not None and (not tools or write or write_dir is not None):
        raise ValueError("--lead needs tools on and no --write or --run-dir")
    if not tools and extra_deny:
        # Broker Worker without a shell tool (luna): emit the deny profile too, so the D51 promise holds on every rung.
        # `-s` is dropped here only: a sandbox_mode override silently replaces default_permissions (proved 2026-10-04);
        # the profile grants cwd read only and shell_tool stays off.
        return ([str(executable), "exec", "-m", slug] + common + permission_args(cwd, False, extra_deny=extra_deny)
                + ["-c", "features.shell_tool=false", "-"])
    if not tools:
        return [str(executable), "exec", "-m", slug, "-s", "read-only"] + common + ["-c", "features.shell_tool=false", "-"]
    # No -s with tools on: a sandbox_mode override silently replaces default_permissions (proved 2026-10-04).
    # The profile alone sets access: cwd "read", or "write" with --write; network stays off.
    # inherit="none" leaves PATH empty; give tool commands system paths only (no /opt/homebrew, no user paths).
    return ([str(executable), "exec", "-m", slug] + common + ["-c", f'shell_environment_policy.set.PATH="{TOOL_PATH}"']
            + permission_args(cwd, write, write_dir=write_dir, extra_deny=extra_deny)
            + (lead_args(model, lead_dir, None, lead_home, home_repo) if lead_dir is not None else []) + ["-"])


def run_codex(model: str, effort: str, cwd: Path, prompt_stream, receipt, supported_efforts: dict[str, list[str]],
              no_tools: bool = False, write: bool = False, tools: bool = False, write_dir: Path | None = None,
              env: dict | None = None, lead_dir: Path | None = None, home_repo: str | None = None,
              extra_deny: tuple = (), isolate_home: bool = False) -> int:
    if receipt.codex_path is None:
        raise FileNotFoundError("WB_CLI_NOT_FOUND: Codex not installed (receipt has no codex_path); install codex, then run agents-inc repair")
    executable = Path(receipt.codex_path)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise FileNotFoundError("WB_CLI_NOT_FOUND: recorded Codex executable missing; run agents-inc repair")

    # Resolve model slug using same logic as build_codex_argv
    model_map = load_model_map()
    slug = model_map.get(model, model if model in supported_efforts else None)
    if not slug:
        raise ValueError(f"unknown Codex model alias: {model}")

    if lead_dir is not None:
        if no_tools:
            raise ValueError("--lead excludes --no-tools")
        tools = True  # --lead implies tools on; lead_args refuses luna and raw slugs
        if write or write_dir is not None:
            raise ValueError("--lead excludes --write and --run-dir (the run directory is broker-owned)")
        lead_args(model, lead_dir)  # fail before any launch
    tools = tools_for(model, no_tools, tools)
    if write and not tools:
        raise ValueError("--write needs --tools (rung astra, sol, or terra, without --no-tools)")
    if write_dir is not None and not write:
        raise ValueError("--run-dir needs --write")
    lead_home = lead_codex_home(slug) if (lead_dir is not None or isolate_home) else None
    cleanup_failed = False
    try:
        sys.stderr.write("agents-inc run: record " + json.dumps({"model": model, "slug": slug, "tools": "on" if tools else "off",
                         "sandbox": "workspace-write" if write else "read-only",
                         **({"transport": "mcp"} if lead_dir is not None else {}),
                         **({"codex_home": "isolated"} if lead_home is not None else {})}) + "\n")
        deny = tuple(extra_deny)
        if lead_home is not None:
            if lead_dir is not None:
                env = lead_env(executable, lead_home, env)
                deny += (Path(lead_dir).resolve(),)  # the run directory is broker-owned: unreadable to the Lead
            else:  # a broker-launched Worker keeps its scrubbed env; only CODEX_HOME is added
                env = {**(os.environ if env is None else env), "CODEX_HOME": str(lead_home)}
            deny += (lead_home,)
        result = subprocess.run(
            build_codex_argv(executable, model, effort, cwd, supported_efforts, model_map, tools, write, write_dir, lead_dir,
                             deny, lead_home, home_repo),
            input=prompt_stream.read(),  # text, never the stream: StringIO has no fileno
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=env,  # None inherits (CLI default); the D51 broker passes a scrubbed env
        )
    finally:
        if lead_home is not None:
            auth = lead_home / "auth.json"
            if auth.exists() and not auth.is_symlink():  # Codex replaced the link with a real credential file
                sys.stderr.write("agents-inc run: isolated CODEX_HOME kept: auth.json is no longer a symlink\n")
                cleanup_failed = True
            else:
                try:
                    shutil.rmtree(lead_home)  # removes the symlinks, never their targets
                except OSError:
                    pass
                if lead_home.exists():
                    sys.stderr.write(f"agents-inc run: isolated CODEX_HOME not removed: {lead_home}\n")
                    cleanup_failed = True

    # Write captured output unchanged
    sys.stdout.write(result.stdout)
    sys.stdout.flush()
    sys.stderr.write(result.stderr)
    sys.stderr.flush()

    # Check for usage/rate limit errors only in ERROR lines
    for line in result.stderr.split('\n'):
        stripped = line.lstrip()
        if stripped.startswith('ERROR:'):
            # Case-insensitive regex match for rate limit patterns
            if re.search(r'usage limit|rate limit|too many requests|\b429\b', stripped, re.IGNORECASE):
                # Extract retry time from this ERROR line
                match = re.search(r'try again at ([^\.\n]+)', line)
                retry_time = match.group(1) if match else "unknown"

                # Print error message
                error_msg = f"agents-inc run: codex {slug} hit a usage or rate limit; retry at {retry_time}"
                sys.stderr.write(error_msg + "\n")
                sys.stderr.flush()

                # Report to free_health
                try:
                    from agents_inc import free_health
                    free_health.report("codex", slug, "rate_limited", message=error_msg)
                except Exception:
                    pass

                return 75

    # Check for empty output with success exit code
    if result.returncode == 0 and not result.stdout.strip():
        sys.stderr.write(f"agents-inc run: codex {slug} returned an empty reply\n")
        sys.stderr.flush()
        return 1

    # Return original exit code; a leaked isolated CODEX_HOME turns success into failure
    return 1 if cleanup_failed and result.returncode == 0 else result.returncode
