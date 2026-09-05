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
    truncated: bool = False

def run_worker(cmd: list[str], stdin_text: str, timeout: int = 300, cwd: str | None = None, max_output_bytes: int = 1_000_000) -> WorkerResult:
    try:
        p = subprocess.run(cmd, input=stdin_text, text=True, capture_output=True, timeout=timeout, cwd=cwd, check=False)
    except FileNotFoundError as e:
        return WorkerResult("failed", "", f"WB_CLI_NOT_FOUND: {e}", 127)
    except subprocess.TimeoutExpired:
        return WorkerResult("failed", "", "timeout", 124)

    stdout, stderr = p.stdout, p.stderr
    truncated = False
    if len(stdout.encode("utf-8", errors="ignore")) > max_output_bytes:
        stdout = stdout.encode("utf-8", errors="ignore")[:max_output_bytes].decode("utf-8", errors="ignore")
        truncated = True
    if len(stderr.encode("utf-8", errors="ignore")) > max_output_bytes:
        stderr = stderr.encode("utf-8", errors="ignore")[:max_output_bytes].decode("utf-8", errors="ignore")
        truncated = True

    if p.returncode == 0:
        return WorkerResult("returned", stdout, stderr, 0, truncated)
    if _QUOTA.search(stderr or stdout or ""):
        return WorkerResult("paused", stdout, stderr, p.returncode, truncated)
    return WorkerResult("failed", stdout, stderr, p.returncode, truncated)
