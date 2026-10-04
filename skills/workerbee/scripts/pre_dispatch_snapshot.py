"""Pre-dispatch baseline: capture and verify the working tree a delegate inherits.

Usage: python3 pre_dispatch_snapshot.py capture <out.json>
       python3 pre_dispatch_snapshot.py verify <out.json> [--allow <path>]...

Run from inside the repository. capture writes JSON with keys time, head,
porcelain (`git status --porcelain`), and sha256 (repo-relative path -> hex
digest of every pre-existing dirty file plus every untracked file, enumerated
recursively with `git ls-files --others --exclude-standard`).

verify exits 0 when every hashed file is unchanged and the tree differs from
the snapshot only at --allow paths (a path or a directory prefix). Else it
exits 1 and prints one `CHANGED <path>` line per offending path. Exit 2 on
usage or git error. Capture and verify on the same host and git config.
"""
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
import time


def _git(*args: str) -> str:
    # core.quotepath=off keeps non-ASCII paths literal instead of octal-escaped.
    return subprocess.run(["git", "-c", "core.quotepath=off", *args],
                          capture_output=True, text=True, check=True).stdout


def _unquote(p: str) -> str:
    """Undo git C-style quoting ("a\\"b", octal escapes) on one porcelain path."""
    p = p.strip()
    if len(p) >= 2 and p.startswith('"') and p.endswith('"'):
        raw = p[1:-1].encode("utf-8").decode("unicode_escape")
        try:
            return raw.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return raw
    return p


def _sha(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except (FileNotFoundError, IsADirectoryError):
        return None


def _porcelain_paths(line: str) -> list[str]:
    body = line[3:]
    return [_unquote(p) for p in body.split(" -> ")] if body else []


def _dirty_files(porcelain: str) -> set[str]:
    files: set[str] = set()
    for line in porcelain.splitlines():
        if line.startswith("??"):
            continue
        for p in _porcelain_paths(line):
            if os.path.isfile(p):
                files.add(p)
    return files


def _untracked() -> set[str]:
    return {p for p in _git("ls-files", "--others", "--exclude-standard").splitlines() if p}


def capture(out: str) -> int:
    porcelain = _git("status", "--porcelain")
    files = _dirty_files(porcelain) | _untracked()
    snap = {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "head": _git("rev-parse", "HEAD").strip(),
        "porcelain": porcelain,
        "sha256": {p: _sha(p) for p in sorted(files)},
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=1)
        fh.write("\n")
    print(f"captured {len(files)} file(s) -> {out}")
    return 0


def _allowed(path: str, allow: list[str]) -> bool:
    path = path.rstrip("/")
    for a in allow:
        a = a.rstrip("/")
        if path == a or path.startswith(a + "/"):
            return True
    return False


def verify(snap_path: str, allow: list[str]) -> int:
    with open(snap_path, encoding="utf-8") as fh:
        snap = json.load(fh)
    changed: set[str] = set()
    hashes = snap.get("sha256", {})
    for path, digest in hashes.items():
        if not _allowed(path, allow) and _sha(path) != digest:
            changed.add(path)
    old = set(snap.get("porcelain", "").splitlines())
    new = set(_git("status", "--porcelain").splitlines())
    for line in old ^ new:
        for p in _porcelain_paths(line):
            if not _allowed(p, allow):
                changed.add(p)
    # untracked files hidden inside a pre-existing untracked directory line
    for p in _untracked() - set(hashes):
        if not _allowed(p, allow):
            changed.add(p)
    if snap.get("head") and _git("rev-parse", "HEAD").strip() != snap["head"]:
        changed.add("HEAD")
    for p in sorted(changed):
        print(f"CHANGED {p}")
    if changed:
        return 1
    print("UNCHANGED outside allowed paths")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "capture":
        cmd, path, allow = "capture", argv[1], []
    elif len(argv) >= 2 and argv[0] == "verify":
        cmd, path, rest, allow = "verify", argv[1], argv[2:], []
        while rest:
            if rest[0] != "--allow" or len(rest) < 2:
                print(__doc__, file=sys.stderr)
                return 2
            allow.append(rest[1])
            rest = rest[2:]
    else:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        # porcelain and ls-files paths are repo-root relative; resolve them there.
        top = _git("rev-parse", "--show-toplevel").strip()
        path = os.path.abspath(path)
        os.chdir(top)
        return capture(path) if cmd == "capture" else verify(path, allow)
    except subprocess.CalledProcessError as exc:
        print(f"git error: {exc.stderr.strip()}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
