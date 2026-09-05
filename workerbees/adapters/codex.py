# workerbees/adapters/codex.py
"""Codex Worker: exec, read-only sandbox, empty cwd, no inherited env, no web. Prompt on stdin."""
import tempfile

def empty_cwd() -> str:
    return tempfile.mkdtemp(prefix="wb-worker-")

def build_cmd(model: str, cwd: str | None = None) -> list[str]:
    cwd = cwd or empty_cwd()
    return ["codex", "exec", "-m", model, "-s", "read-only", "--skip-git-repo-check", "-C", cwd,
            "-c", 'shell_environment_policy.inherit="none"', "-c", 'web_search="disabled"', "-c", "features.shell_tool=false", "-"]
