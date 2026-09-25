"""One canonical SKILL.md -> .claude/skills + .agents/skills. Bodies identical; frontmatter per host."""
from __future__ import annotations
from pathlib import Path

HOST_DIRS = {"claude": ".claude/skills", "codex": ".agents/skills"}

def _split(text: str) -> tuple[str, str]:
    _, fm, body = text.split("---", 2)
    return fm.strip(), body

def generate(canonical: Path, root: Path) -> list[Path]:
    fm, body = _split(canonical.read_text())
    out = []
    for host, rel in HOST_DIRS.items():
        dest = root / rel / canonical.parent.name / "SKILL.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(f"---\n{fm}\n---{body}")
        out.append(dest)
    return out

if __name__ == "__main__":
    import sys
    for p in generate(Path(sys.argv[1]), Path(sys.argv[2] if len(sys.argv) > 2 else ".")):
        print(p)
