# workerbees/adapters/base.py
"""Run one tool-free Worker. Exit 0 means Returned, never Verified."""
from __future__ import annotations
import re, subprocess
from dataclasses import dataclass

_QUOTA = re.compile(r"rate.?limit|quota|usage limit|429|too many requests", re.I)

@dataclass
class WorkerResult:
    status: str   # returned | failed | paused
    output: str
    stderr: str
    exit_code: int

def run_worker(cmd: list[str], stdin_text: str, timeout: int = 300, cwd: str | None = None) -> WorkerResult:
    try:
        p = subprocess.run(cmd, input=stdin_text, text=True, capture_output=True, timeout=timeout, cwd=cwd, check=False)
    except FileNotFoundError as e:
        return WorkerResult("failed", "", f"WB_CLI_NOT_FOUND: {e}", 127)
    except subprocess.TimeoutExpired:
        return WorkerResult("failed", "", "timeout", 124)
    if p.returncode == 0:
        return WorkerResult("returned", p.stdout, p.stderr, 0)
    if _QUOTA.search(p.stderr or p.stdout or ""):
        return WorkerResult("paused", p.stdout, p.stderr, p.returncode)
    return WorkerResult("failed", p.stdout, p.stderr, p.returncode)
