"""Private, atomic installation receipts; never store authentication data."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class OwnedPath:
    path: Path
    kind: str
    predecessor: str | None = None
    target: str | None = None

    def __post_init__(self) -> None:
        if not self.path.is_absolute():
            raise ValueError("owned path must be absolute")

    def as_dict(self) -> dict[str, object]:
        return {"path": str(self.path), "kind": self.kind, "predecessor": self.predecessor, "target": self.target}

    @classmethod
    def from_dict(cls, value: object) -> "OwnedPath":
        if not isinstance(value, dict):
            raise ValueError("owned path must be an object")
        return cls(Path(str(value["path"])), str(value["kind"]), value.get("predecessor"), value.get("target"))


@dataclass(frozen=True)
class InstallReceipt:
    release_hash: str
    python_path: Path
    codex_path: Path
    owned_paths: tuple[OwnedPath, ...] = field(default_factory=tuple)
    prior_release: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported receipt schema")
        if len(self.release_hash) != 64 or any(c not in "0123456789abcdef" for c in self.release_hash):
            raise ValueError("release hash must be a sha256 hex digest")
        if not self.python_path.is_absolute() or not self.codex_path.is_absolute():
            raise ValueError("runtime paths must be absolute")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "release_hash": self.release_hash,
            "python_path": str(self.python_path),
            "codex_path": str(self.codex_path),
            "owned_paths": [item.as_dict() for item in self.owned_paths],
            "prior_release": self.prior_release,
        }

    @classmethod
    def load(cls, path: Path) -> "InstallReceipt":
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError("receipt is not valid JSON") from exc
        if not isinstance(data, dict):
            raise ValueError("receipt must be a JSON object")
        if data.get("schema_version") != 1:
            raise ValueError("unsupported receipt schema")
        owned = data.get("owned_paths", [])
        if not isinstance(owned, list):
            raise ValueError("owned paths must be a list")
        try:
            return cls(
                release_hash=str(data["release_hash"]),
                python_path=Path(str(data["python_path"])),
                codex_path=Path(str(data["codex_path"])),
                owned_paths=tuple(OwnedPath.from_dict(item) for item in owned),
                prior_release=data.get("prior_release"),
            )
        except (KeyError, TypeError) as exc:
            raise ValueError("receipt missing required fields") from exc

    def save_atomic(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.as_dict(), handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
