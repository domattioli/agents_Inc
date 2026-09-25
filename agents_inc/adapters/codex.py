# agents_inc/adapters/codex.py
"""Codex Worker: exec, read-only sandbox, empty cwd, no inherited env, no web. Prompt on stdin."""
import tempfile
from pathlib import Path

def empty_cwd() -> str:
    return tempfile.mkdtemp(prefix="wb-worker-")

def build_cmd(model: str, executable: str | None, cwd: str | None = None, effort: str = "medium") -> list[str]:
    if not executable or not Path(executable).is_absolute():
        raise ValueError("WB_CLI_NOT_FOUND: absolute Codex executable required")
    cwd = cwd or empty_cwd()
    return [executable, "exec", "-m", model, "-s", "read-only", "--skip-git-repo-check", "-C", cwd,
            "-c", f"model_reasoning_effort={effort}",
            "-c", 'shell_environment_policy.inherit="none"', "-c", 'web_search="disabled"', "-c", "features.shell_tool=false", "-"]
