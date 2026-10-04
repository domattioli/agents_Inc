"""Direct Codex execution with an install-recorded executable only."""
from __future__ import annotations
import os
import re
import shutil
import subprocess
from pathlib import Path

import json
import sys

# Built-in DEFAULTS only; resolution goes through load_model_map().
MODEL_ALIASES = {"astra": "gpt-6-astra", "sol": "gpt-5.6-sol", "terra": "gpt-5.6-terra", "luna": "gpt-5.6-luna"}


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


def permission_profile(cwd: Path, write: bool, home: Path | None = None) -> dict[str, str]:
    """Filesystem grants for tool commands. Anything absent (all of HOME except cwd) is unreadable."""
    home = Path(home or Path.home())
    grants = {'":minimal"': "read", _toml_key("/opt/homebrew"): "read", _toml_key("/tmp"): "read",
              _toml_key("/private/tmp"): "read", _toml_key(cwd): "write" if write else "read"}
    for name in HARD_DENY:
        grants[f'"{os.path.realpath(home)}/{name}"'] = "none"
    return grants


def permission_args(cwd: Path, write: bool, home: Path | None = None) -> list[str]:
    body = ", ".join(f"{k}={chr(34)}{v}{chr(34)}" for k, v in permission_profile(cwd, write, home).items())
    return ["-c", f'default_permissions="{PROFILE}"', "-c", f"permissions.{PROFILE}.filesystem={{{body}}}"]


def build_codex_argv(executable: Path, model: str, effort: str, cwd: Path, supported_efforts: dict[str, list[str]],
                     model_map: dict[str, str] | None = None, tools: bool = False, write: bool = False) -> list[str]:
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
    if not tools:
        return [str(executable), "exec", "-m", slug, "-s", "read-only"] + common + ["-c", "features.shell_tool=false", "-"]
    # No -s with tools on: a sandbox_mode override silently replaces default_permissions (proved 2026-10-04).
    # The profile alone sets access: cwd "read", or "write" with --write; network stays off.
    # inherit="none" leaves PATH empty; give tool commands system paths only (no /opt/homebrew, no user paths).
    return ([str(executable), "exec", "-m", slug] + common + ["-c", f'shell_environment_policy.set.PATH="{TOOL_PATH}"']
            + permission_args(cwd, write) + ["-"])


def run_codex(model: str, effort: str, cwd: Path, prompt_stream, receipt, supported_efforts: dict[str, list[str]],
              no_tools: bool = False, write: bool = False, tools: bool = False) -> int:
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

    tools = tools_for(model, no_tools, tools)
    if write and not tools:
        raise ValueError("--write needs --tools (rung astra, sol, or terra, without --no-tools)")
    sys.stderr.write("agents-inc run: record " + json.dumps({"model": model, "slug": slug, "tools": "on" if tools else "off",
                     "sandbox": "workspace-write" if write else "read-only"}) + "\n")
    result = subprocess.run(
        build_codex_argv(executable, model, effort, cwd, supported_efforts, model_map, tools, write),
        stdin=prompt_stream,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False
    )

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

    # Return original exit code
    return result.returncode
