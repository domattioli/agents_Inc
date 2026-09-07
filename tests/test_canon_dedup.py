"""T002: fail if two canon files share a normalized ##-section body. Block set fixed."""
from __future__ import annotations
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BLOCK_SET = [
    ROOT / "CLAUDE.md",
    ROOT / "CONTEXT.md",
    ROOT / "AGENTS.md",
    ROOT / ".specify" / "memory" / "constitution.md",
    ROOT / "docs" / "governance" / "ROUTING-RANKING.md",
    ROOT / "skills" / "workerbee" / "SKILL.md",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _sections(path: Path) -> dict[str, str]:
    """Split on '## ' headers (H2). Returns {header: normalized_body}."""
    text = path.read_text()
    parts = re.split(r"(?m)^## ", text)
    out: dict[str, str] = {}
    for part in parts[1:]:
        lines = part.split("\n", 1)
        header = lines[0].strip()
        body = lines[1] if len(lines) > 1 else ""
        out[f"{path.name}::{header}"] = _normalize(body)
    return out


def _all_sections() -> dict[str, str]:
    merged: dict[str, str] = {}
    for p in BLOCK_SET:
        if p.exists():
            merged.update(_sections(p))
    return merged


class TestCanonDedup(unittest.TestCase):
    def test_no_duplicate_section_bodies_across_canon_files(self):
        sections = _all_sections()
        seen: dict[str, str] = {}
        dupes = []
        for name, body in sections.items():
            if not body:
                continue
            if body in seen:
                dupes.append((seen[body], name))
            else:
                seen[body] = name
        self.assertEqual(dupes, [], f"Duplicate section bodies found: {dupes}")

    def test_detects_deliberate_reduplication(self):
        sections = {
            "a.md::Foo": _normalize("same content here for test"),
            "b.md::Bar": _normalize("same content here for test"),
        }
        seen: dict[str, str] = {}
        dupes = []
        for name, body in sections.items():
            if body in seen:
                dupes.append((seen[body], name))
            else:
                seen[body] = name
        self.assertNotEqual(dupes, [])


if __name__ == "__main__":
    unittest.main()
