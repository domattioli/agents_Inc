#!/usr/bin/env python3
"""Resolve a rung name to its dispatchable model slugs, parsed live from this
repo's docs/governance/ROUTING-RANKING.md (table of record) -- never a
hardcoded copy, so it can never drift from canon (agents_for_dummies-native
addition to the DomI-forked speckit-pipeline, D35/D34).

Usage: resolve_rung.py <RungName> [--repo-root PATH]
  RungName: Executive | Orchestrator | Supervisor | Workhorse | Grunt
  (Supervisor is the D34 synonym for Orchestrator -- same rung.)

Prints JSON to stdout: {"rung": "...", "default": ["slug", ...], "escalate_to": ["slug", ...]}
Exit 0 on success. Exit 1 with a message on stderr if the rung or table row
is not found (fail closed, per constitution P4 -- never guess a route).
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

# Display-name -> dispatch slug. Claude slugs are Agent-tool `model` values;
# Codex slugs are workerbee vendor nicknames (constitution P7 -- never mix
# the two families up). Extend here only, never hardcode a routing table
# elsewhere -- this is the single normalization point.
_SLUG_MAP = {
    "fable 5": "fable", "fable": "fable",
    "opus 5": "opus", "opus": "opus",
    "sonnet 5": "sonnet", "sonnet": "sonnet",
    "haiku 4.5": "haiku", "haiku": "haiku",
    "astra": "astra", "gpt-6 astra": "astra",
    "sol": "sol", "gpt-5.6 sol": "sol",
    "terra": "terra", "gpt-5.6 terra": "terra",
    "luna": "luna", "gpt-5.6 luna": "luna",
}

_SYNONYMS = {"supervisor": "orchestrator"}  # D34: same rung, alt keyword


def _to_slug(display: str) -> str:
    key = display.strip().lower()
    if key in _SLUG_MAP:
        return _SLUG_MAP[key]
    raise ValueError(f"unrecognized model display name in ROUTING-RANKING.md: {display!r}")


def _split_models(cell: str) -> list[str]:
    # Cells look like "Fable 5 or Astra" or "the other frontier model" (prose,
    # not a name -- caller resolves relative to the dispatching model itself).
    if "the other" in cell.lower():
        return []
    parts = re.split(r"\s+or\s+", cell.strip())
    return [_to_slug(p) for p in parts if p.strip()]


def parse_rungs_table(md_text: str) -> dict[str, dict[str, list[str]]]:
    lines = md_text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == "## Rungs")
    except StopIteration:
        raise ValueError("'## Rungs' section not found in ROUTING-RANKING.md")

    rows: dict[str, dict[str, list[str]]] = {}
    in_table = False
    for line in lines[start:]:
        if line.startswith("## ") and line.strip() != "## Rungs":
            break
        if not line.strip().startswith("|"):
            if in_table:
                break
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0] in ("Rung", "---") or set(cells[0]) <= {"-"}:
            in_table = True
            continue
        rung_names = [n.strip() for n in cells[0].split("/")]
        entry = {
            "default": _split_models(cells[1]),
            "escalate_to": _split_models(cells[2]),
        }
        for name in rung_names:
            rows[name.strip().lower()] = entry
    if not rows:
        raise ValueError("no data rows parsed under '## Rungs' -- table shape changed?")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rung")
    ap.add_argument("--repo-root", default=None)
    args = ap.parse_args()

    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[3]
    table_path = repo_root / "docs" / "governance" / "ROUTING-RANKING.md"
    if not table_path.exists():
        print(f"ROUTING-RANKING.md not found at {table_path}", file=sys.stderr)
        return 1

    key = args.rung.strip().lower()
    key = _SYNONYMS.get(key, key)

    try:
        rows = parse_rungs_table(table_path.read_text())
    except ValueError as e:
        print(f"parse error: {e}", file=sys.stderr)
        return 1

    if key not in rows:
        print(f"unknown rung {args.rung!r}; known: {sorted(rows)}", file=sys.stderr)
        return 1

    print(json.dumps({"rung": args.rung, **rows[key]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
