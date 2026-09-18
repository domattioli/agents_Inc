"""Direct Codex execution with an install-recorded executable only."""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path

MODEL_ALIASES = {"astra": "gpt-6-astra", "sol": "gpt-5.6-sol", "terra": "gpt-5.6-terra", "luna": "gpt-5.6-luna"}


def resolve_executable(name: str, search_path: str | None = None) -> Path:
    candidate = shutil.which(name, path=search_path)
    if not candidate:
        raise FileNotFoundError(f"WB_CLI_NOT_FOUND: {name}; run agents-inc repair")
    path = Path(candidate).resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise FileNotFoundError(f"WB_CLI_NOT_FOUND: {name}; run agents-inc repair")
    return path


def build_codex_argv(executable: Path, model: str, effort: str, cwd: Path, supported_efforts: dict[str, list[str]]) -> list[str]:
    slug = MODEL_ALIASES.get(model, model if model in supported_efforts else None)
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
    executable = Path(receipt.codex_path)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise FileNotFoundError("WB_CLI_NOT_FOUND: recorded Codex executable missing; run agents-inc repair")
    return subprocess.run(build_codex_argv(executable, model, effort, cwd, supported_efforts), stdin=prompt_stream, check=False).returncode
