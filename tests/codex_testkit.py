"""Shared executable fixture for tests that route work through Codex."""
from __future__ import annotations

import atexit
import stat
import tempfile
from pathlib import Path


_directory = tempfile.TemporaryDirectory(prefix="workerbees-codex-test-")
atexit.register(_directory.cleanup)
CODEX_EXECUTABLE = Path(_directory.name) / "codex"
CODEX_EXECUTABLE.write_text("#!/bin/sh\nexit 0\n")
CODEX_EXECUTABLE.chmod(CODEX_EXECUTABLE.stat().st_mode | stat.S_IXUSR)
