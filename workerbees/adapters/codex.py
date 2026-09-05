# workerbees/adapters/codex.py
"""Codex Worker: exec, read-only sandbox, prompt on stdin."""
def build_cmd(model: str) -> list[str]:
    return ["codex", "exec", "-m", model, "-s", "read-only", "--skip-git-repo-check", "-"]
