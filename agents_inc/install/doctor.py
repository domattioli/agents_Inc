"""Offline installer verification; live probing is deliberately opt-in."""
from __future__ import annotations
from dataclasses import dataclass
import json
import os
import subprocess
from pathlib import Path
from .bundle import verify_bundle
from .paths import InstallPaths
from .receipt import InstallReceipt
from .runtime import build_codex_argv

@dataclass(frozen=True)
class DoctorReport:
    ready: bool
    codes: tuple[str, ...]
    live: dict | None = None
    warnings: tuple[str, ...] = ()  # non-fatal; never affects `ready` or the CLI exit code
    def as_dict(self): return {"ready": self.ready, "codes": list(self.codes), "live": self.live, "warnings": list(self.warnings)}

def check_install(paths: InstallPaths, live_model: str | None = None, runner=subprocess.run) -> DoctorReport:
    codes = []; warnings = []
    try: receipt = InstallReceipt.load(paths.receipt)
    except (OSError, ValueError):
        missing = () if paths.receipt.exists() else ("WB_NOT_INSTALLED",)  # #35: say why
        return DoctorReport(False, ("WB_RELEASE_UNTRUSTED",) + missing)
    release = paths.releases / receipt.release_hash
    if not verify_bundle(release): codes.append("WB_RELEASE_UNTRUSTED")
    if not paths.current.is_symlink() or paths.current.resolve() != release.resolve(): codes.append("WB_RELEASE_UNTRUSTED")
    if receipt.codex_path is None: warnings.append("WB_CLI_NOT_FOUND")  # installed without codex: warning only
    elif not receipt.codex_path.is_file() or not os.access(receipt.codex_path, os.X_OK): codes.append("WB_CLI_NOT_FOUND")
    for root in (paths.claude_skills, paths.codex_skills):
        for name in ("workerbee", "codex-bridge"):
            if not (root / name).is_symlink(): codes.append("WB_SKILL_MISSING")
    live = None
    if live_model and not codes and receipt.codex_path is not None:
        models = json.loads((release / "agents_inc/models.json").read_text()).get("models", {})
        efforts = {slug: row["supported_efforts"] for slug, row in models.items() if row.get("provider") == "codex" and "supported_efforts" in row}
        argv = build_codex_argv(receipt.codex_path, live_model, "medium", Path.cwd(), efforts)
        completed = runner(argv, input="Reply PONG", text=True, capture_output=True, env={}, check=False)
        output = (completed.stdout or "") + (completed.stderr or "")
        code = "READY" if completed.returncode == 0 and "PONG" in output else ("WB_AUTH_REQUIRED" if "auth" in output.lower() or "login" in output.lower() else "WB_MODEL_UNAVAILABLE")
        live = {"code": code, "executable": str(receipt.codex_path), "isolated": True}
        if code != "READY": codes.append(code)
    return DoctorReport(not codes, tuple(sorted(set(codes))), live, tuple(sorted(set(warnings))))
