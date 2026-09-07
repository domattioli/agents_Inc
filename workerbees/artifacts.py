"""Bindle sibling — Backend A. Content-addressed local blob store.

Spec: specs/006-bindle-sibling-integration/spec.md S5.2, FR-004/005/009/013.
Ledger owns "what happened"; this owns "what was produced" (bytes only, no
run_id/node_id/role sidecar -- that would duplicate ledger authority, S5.2).

Layout: .workerbees/cas/<sha256[:2]>/<sha256> (bytes, 0600) +
        .workerbees/cas/<sha256[:2]>/<sha256>.meta.json (content facts only, 0600)

Never raises past capture()/get() (FR-007) -- I/O and validation errors are
swallowed into Capture(stored=False) or a None return.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Capture:
    sha256: str
    size: int
    stored: bool
    backend: str  # "local" | "off"


def _cas_root(workspace: Path) -> Path:
    return workspace / ".workerbees" / "cas"


def _shard_dir(root: Path, sha256: str) -> Path:
    return root / sha256[:2]


def capture(workspace: Path, data: bytes, *, media_type: str = "text/markdown") -> Capture:
    """Write data to the CAS, keyed by its sha256. Dedup: existing verified blob of the
    same size is a no-op. Never raises -- any failure returns stored=False."""
    sha256 = hashlib.sha256(data).hexdigest()
    size = len(data)
    try:
        root = _cas_root(workspace)
        shard = _shard_dir(root, sha256)
        shard.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(shard, 0o700)
        blob_path = shard / sha256
        meta_path = shard / f"{sha256}.meta.json"

        if blob_path.exists() and blob_path.stat().st_size == size:
            return Capture(sha256=sha256, size=size, stored=True, backend="local")

        fd, tmp_name = tempfile.mkstemp(dir=str(shard), prefix=f".{sha256}.")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, blob_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

        meta = {"sha256": sha256, "size": size, "mediaType": media_type}
        meta_tmp_fd, meta_tmp_name = tempfile.mkstemp(dir=str(shard), prefix=f".{sha256}.meta.")
        try:
            with os.fdopen(meta_tmp_fd, "w") as f:
                json.dump(meta, f)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(meta_tmp_name, 0o600)
            os.replace(meta_tmp_name, meta_path)
        except Exception:
            try:
                os.unlink(meta_tmp_name)
            except OSError:
                pass
            raise

        return Capture(sha256=sha256, size=size, stored=True, backend="local")
    except Exception:
        return Capture(sha256=sha256, size=size, stored=False, backend="local")


def get(workspace: Path, sha256: str, *, verify: bool = True) -> bytes | None:
    """Read a blob back by its sha256. Rejects non-hex/non-64-char keys (path-traversal
    defense) and path-containment escapes. Verifies digest by default; a mismatch
    quarantines the blob (renamed .tampered) and returns None."""
    key = sha256.strip()
    if not _HEX64.match(key):
        return None
    try:
        root = _cas_root(workspace).resolve()
        blob_path = (root / key[:2] / key).resolve()
        if root not in blob_path.parents:
            return None
        if not blob_path.is_file():
            return None
        data = blob_path.read_bytes()
        if verify:
            actual = hashlib.sha256(data).hexdigest()
            if actual != key:
                try:
                    blob_path.rename(blob_path.with_suffix(blob_path.suffix + ".tampered"))
                except OSError:
                    pass
                return None
        return data
    except Exception:
        return None
