"""Offline installer verification; live probing is deliberately opt-in."""
from __future__ import annotations
from dataclasses import dataclass, replace
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from . import catalog
from .bundle import stage_bundle, verify_bundle
from .host_wiring import AT_ROUTE, wiring_problems
from .paths import InstallPaths
from .receipt import InstallReceipt
from .runtime import MODEL_ALIASES, build_codex_argv, is_temp_or_shim_path

@dataclass(frozen=True)
class DoctorReport:
    ready: bool
    codes: tuple[str, ...]
    live: dict | None = None
    warnings: tuple[str, ...] = ()  # non-fatal; never affects `ready` or the CLI exit code
    def as_dict(self): return {"ready": self.ready, "codes": list(self.codes), "live": self.live, "warnings": list(self.warnings)}

def _hook_drift(paths: InstallPaths) -> list[str]:
    """Warn when the installed at_route hook differs from the source checkout it came from."""
    installed = paths.current / AT_ROUTE
    try:
        if not installed.is_file(): return []  # release ships no hook: nothing to drift
        record = paths.state / "source-checkout"
        source = Path(record.read_text().strip()) / AT_ROUTE if record.is_file() else None
        if source is None or not source.is_file(): return ["WB_HOOK_DRIFT_UNCHECKED"]
        return ["WB_HOOK_DRIFT"] if source.read_bytes() != installed.read_bytes() else []
    except OSError: return ["WB_HOOK_DRIFT_UNCHECKED"]

def _model_drift(models: list[dict] | None) -> list[str]:
    """D52: one warning per Codex alias whose pinned slug has a newer catalog slug."""
    out = []
    for alias, slug in MODEL_ALIASES.items():
        newer = catalog.drift(slug, models)
        if newer: out.append(f"MODEL_DRIFT {alias}: pinned {slug}, newest {newer}")
    return out

def _install_stale(paths: InstallPaths, release_hash: str) -> list[str]:
    """D52: warn when the checkout recorded at install time would now stage to a different release hash.
    Staging goes to a temp dir so nothing is written under ~/.local; any failure is silent."""
    record = paths.state / "source-checkout"
    try:
        if not record.is_file(): return []
        source = Path(record.read_text().strip())
        tmp = Path(tempfile.mkdtemp(prefix="agents-inc-stale-"))
        try:
            digest = stage_bundle(source, replace(paths, releases=tmp / "releases")).digest
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except (OSError, ValueError, RuntimeError): return []
    return ["INSTALL_STALE"] if digest != release_hash else []

def check_install(paths: InstallPaths, live_model: str | None = None, runner=subprocess.run,
                  models: list[dict] | None = None, catalog_path: Path | None = None) -> DoctorReport:
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
    elif is_temp_or_shim_path(receipt.codex_path): warnings.append("WB_CLI_TEMP_PATH")
    for root in (paths.claude_skills, paths.codex_skills):
        for name in ("workerbee", "codex-bridge"):
            if not (root / name).is_symlink(): codes.append("WB_SKILL_MISSING")
    # Skills load lazily; without the always-on block and hooks no session learns to delegate.
    if wiring_problems(paths): codes.append("WB_HOST_UNWIRED")
    warnings.extend(_hook_drift(paths))
    if models is None:  # the catalog of the home being checked; CODEX_HOME still wins. [] stops a re-read of the default.
        default = catalog.cache_path({**os.environ, "HOME": str(paths.home)})
        models = catalog.load(catalog_path or default) or []
    warnings.extend(_model_drift(models))
    warnings.extend(_install_stale(paths, receipt.release_hash))
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
