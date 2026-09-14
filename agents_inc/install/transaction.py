"""Durable write-ahead journal for every installer lifecycle mutation."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class LifecycleLock:
    def __init__(self, path: Path): self.path, self.fd = path, None
    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try: self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc: raise RuntimeError("WB_CONFIG_CONFLICT: lifecycle operation already active") from exc
        os.write(self.fd, str(os.getpid()).encode()); os.fsync(self.fd); return self
    def __exit__(self, *_):
        if self.fd is not None: os.close(self.fd)
        self.path.unlink(missing_ok=True)


class TransactionJournal:
    def __init__(self, path: Path): self.path = path; self.data = {"operations": [], "committed": False}
    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw = tempfile.mkstemp(prefix=".journal-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump(self.data, out, sort_keys=True); out.flush(); os.fsync(out.fileno())
            os.replace(raw, self.path)
        finally:
            if os.path.exists(raw): os.unlink(raw)
    def begin(self, action: str): self.data = {"action": action, "operations": [], "committed": False}; self._save(); return self
    def record_intent(self, operation: str, target: Path, predecessor: str | None = None, result: str | None = None):
        self.data["operations"].append({"operation": operation, "target": str(target), "predecessor": predecessor, "result": result, "applied": False}); self._save()
    def record_applied(self): self.data["operations"][-1]["applied"] = True; self._save()
    def apply(self, operation: str, target: Path, predecessor: str | None, result: str | None, mutate):
        self.record_intent(operation, target, predecessor, result)
        mutate()
        if os.environ.get("AGENTS_INC_FAIL_AFTER") == operation:
            raise RuntimeError(f"injected failure after {operation}")
        self.record_applied()
    def commit(self): self.data["committed"] = True; self._save(); self.path.unlink(missing_ok=True)
    @classmethod
    def recover(cls, path: Path):
        if not path.exists(): return
        try: data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc: raise RuntimeError("WB_RELEASE_UNTRUSTED: invalid lifecycle journal") from exc
        if data.get("committed"): path.unlink(missing_ok=True); return
        for op in reversed(data.get("operations", [])):
            target, predecessor = Path(op["target"]), op.get("predecessor")
            # A crash between mutation and applied-marker leaves intent=false.
            # Revert only when the on-disk result proves our mutation happened.
            proven = op.get("applied") or (op.get("operation") == "symlink" and target.is_symlink() and os.readlink(target) == op.get("result"))
            if not proven: continue
            if op.get("operation") in {"symlink", "unlink"}:
                if target.is_symlink(): target.unlink()
                if predecessor is not None:
                    target.parent.mkdir(parents=True, exist_ok=True); target.symlink_to(predecessor)
            elif op.get("operation") == "mkdir" and target.is_dir():
                try: target.rmdir()
                except OSError: pass
            elif op.get("operation") == "receipt" and target.exists(): target.unlink()
        path.unlink(missing_ok=True)
