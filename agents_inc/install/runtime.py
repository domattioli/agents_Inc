"""Direct Codex execution with an install-recorded executable only."""
from __future__ import annotations
import os
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


def build_codex_argv(executable: Path, model: str, effort: str, cwd: Path, supported_efforts: dict[str, list[str]],
                     model_map: dict[str, str] | None = None) -> list[str]:
    slug = (model_map if model_map is not None else load_model_map()).get(model, model if model in supported_efforts else None)
    if not slug:
        raise ValueError(f"unknown Codex model alias: {model}")
    if effort not in supported_efforts.get(slug, []):
        raise ValueError(f"unsupported effort {effort!r} for {slug}")
    if not executable.is_absolute():
        raise ValueError("Codex executable must be absolute")
    return [str(executable), "exec", "-m", slug, "-s", "read-only", "--skip-git-repo-check", "-C", str(cwd),
            "-c", f"model_reasoning_effort={effort}", "-c", 'shell_environment_policy.inherit="none"',
            "-c", 'web_search="disabled"', "-c", "features.shell_tool=false", "-"]


def run_codex(model: str, effort: str, cwd: Path, prompt_stream, receipt, supported_efforts: dict[str, list[str]]) -> int:
    if receipt.codex_path is None:
        raise FileNotFoundError("WB_CLI_NOT_FOUND: Codex not installed (receipt has no codex_path); install codex, then run agents-inc repair")
    executable = Path(receipt.codex_path)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise FileNotFoundError("WB_CLI_NOT_FOUND: recorded Codex executable missing; run agents-inc repair")
    return subprocess.run(build_codex_argv(executable, model, effort, cwd, supported_efforts), stdin=prompt_stream, check=False).returncode
