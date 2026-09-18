"""Command line for user-scoped direct Codex installation."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from .bundle import activate, stage_bundle
from .discovery import install_skill_links, restore_skill_links
from .doctor import check_install
from .paths import InstallPaths
from .receipt import InstallReceipt, OwnedPath
from .runtime import resolve_executable, run_codex
from .transaction import LifecycleLock, TransactionJournal

def _paths(): return InstallPaths.for_home(Path.home())
def _efforts(release):
    models = json.loads((release / "agents_inc/models.json").read_text()).get("models", {})
    return {name: value["supported_efforts"] for name, value in models.items() if "supported_efforts" in value}
def install_convenience_launcher(paths: InstallPaths, journal=None) -> OwnedPath:
    """Create only our stable user-bin link; preserve every foreign path."""
    desired = paths.current / "bin/agents-inc"
    paths.launcher.parent.mkdir(parents=True, exist_ok=True)
    if paths.launcher.exists() or paths.launcher.is_symlink():
        if paths.launcher.is_symlink() and paths.launcher.resolve() == desired.resolve():
            return OwnedPath(paths.launcher, "symlink")
        raise RuntimeError(f"WB_CONFIG_CONFLICT: foreign launcher path {paths.launcher}")
    if journal: journal.apply("symlink", paths.launcher, None, str(desired), lambda: paths.launcher.symlink_to(desired))
    else: paths.launcher.symlink_to(desired)
    return OwnedPath(paths.launcher, "symlink", None, str(desired))

def install(args):
    paths = _paths()
    with LifecycleLock(paths.lock):
        TransactionJournal.recover(paths.journal)
        journal = TransactionJournal(paths.journal).begin("install")
        try:
            staged = stage_bundle(Path(args.source), paths)
            receipt = InstallReceipt(staged.digest, Path(sys.executable).resolve(), resolve_executable("codex", os.environ.get("PATH")))
            receipt = activate(staged, paths, receipt, journal)
            receipt = install_skill_links(paths, staged.path, receipt, args.adopt_existing_workerbee, journal)
            launcher = install_convenience_launcher(paths, journal)
            receipt = InstallReceipt(receipt.release_hash, receipt.python_path, receipt.codex_path, receipt.owned_paths + (launcher,), receipt.prior_release)
            journal.apply("receipt", paths.receipt, None, None, lambda: receipt.save_atomic(paths.receipt))
            journal.commit(); return 0
        except Exception:
            TransactionJournal.recover(paths.journal)
            raise

def uninstall(paths: InstallPaths, receipt: InstallReceipt) -> set[Path]:
    """Remove only receipt-owned, byte-for-byte unchanged artifacts."""
    with LifecycleLock(paths.lock):
        TransactionJournal.recover(paths.journal)
        journal = TransactionJournal(paths.journal).begin("uninstall")
        retained = restore_skill_links(paths, receipt, journal)
        for item in receipt.owned_paths:
            if item.kind != "symlink" or item.path in retained or not item.path.is_symlink(): continue
            if item.target is None or os.readlink(item.path) != item.target:
                retained.add(item.path)
        if retained:
            # Receipt is evidence needed for a future conservative retry.
            journal.commit(); return retained
        journal.apply("receipt", paths.receipt, None, None, lambda: paths.receipt.unlink(missing_ok=True))
        journal.commit(); return retained
def main(argv=None):
    parser = argparse.ArgumentParser(prog="agents-inc")
    subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("install"); p.add_argument("--source", required=True); p.add_argument("--adopt-existing-workerbee", action="store_true")
    p = subs.add_parser("run"); p.add_argument("--model", required=True); p.add_argument("--effort", default="medium"); p.add_argument("--cwd", required=True)
    p = subs.add_parser("doctor"); p.add_argument("--json", action="store_true"); p.add_argument("--live-model")
    p = subs.add_parser("repair"); p.add_argument("--source", required=True); p.add_argument("--adopt-existing-workerbee", action="store_true")
    subs.add_parser("rollback"); subs.add_parser("uninstall")
    args = parser.parse_args(argv); paths = _paths()
    try:
        if args.command == "install": return install(args)
        if args.command == "doctor":
            report = check_install(paths, args.live_model); print(json.dumps(report.as_dict()) if args.json else " ".join(report.codes or ("READY",))); return 0 if report.ready else 1
        receipt = InstallReceipt.load(paths.receipt)
        if args.command == "run": return run_codex(args.model, args.effort, Path(args.cwd), sys.stdin, receipt, _efforts(paths.current.resolve()))
        if args.command == "uninstall":
            retained = uninstall(paths, receipt)
            if retained: print("WB_CONFIG_CONFLICT: retained modified artifacts", file=sys.stderr); return 1
            return 0
        if args.command == "repair": return install(args)
        if args.command == "rollback":
            if not receipt.prior_release: raise RuntimeError("no predecessor release")
            with LifecycleLock(paths.lock):
                TransactionJournal.recover(paths.journal); journal = TransactionJournal(paths.journal).begin("rollback")
                prior = os.readlink(paths.current) if paths.current.is_symlink() else None
                journal.apply("symlink", paths.current, prior, receipt.prior_release, lambda: (paths.current.unlink(missing_ok=True), paths.current.symlink_to(receipt.prior_release)))
                journal.commit()
            return 0
    except (OSError, ValueError, RuntimeError) as exc: print(str(exc), file=sys.stderr); return 1
if __name__ == "__main__": raise SystemExit(main())
