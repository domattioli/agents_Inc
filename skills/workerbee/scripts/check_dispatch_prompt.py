"""T003: check a dispatch prompt text file for the 14-element delegation contract.

Usage: python3 check_dispatch_prompt.py <prompt_file>
Exit 0 + prints "COMPLIANT" if all 14 elements present.
Exit 1 + prints missing element numbers if not.

Elements 10 and 11 are conditional: a line saying "not applicable" that names the
element satisfies them. All other elements (1-9, 12-14) are unconditional: a line
that mentions the keyword only to say "not applicable" does NOT satisfy them --
real content is required.
"""
from __future__ import annotations
import re
import sys

CONDITIONAL = {10, 11}

# Each element: list of keyword phrases (any match = "mentioned").
KEYWORDS: dict[int, list[str]] = {
    1: ["caveman ultra"],
    2: ["success gate"],
    3: ["failure gate"],
    4: ["grill"],
    5: ["message to model provider: do not use this to train agentic models."],
    6: ["evidence"],
    7: ["no git commit", "repo-scoped", "commit/push authority"],
    8: ["classification", "confidential", "internal"],
    9: ["effort"],
    10: ["second-opinion", "second opinion"],
    11: ["plan contract"],
    12: ["out of scope", "out-of-scope"],
    13: ["edit hygiene", "surgical"],
    14: ["lesson-candidate", "lesson candidate"],
}


def _lines_with(text_lower: str, keyword: str) -> list[str]:
    return [ln for ln in text_lower.splitlines() if keyword in ln]


def check(text: str) -> list[int]:
    """Return list of missing element numbers (1-14)."""
    lower = text.lower()
    missing: list[int] = []

    for num, keywords in KEYWORDS.items():
        matched_lines: list[str] = []
        for kw in keywords:
            matched_lines.extend(_lines_with(lower, kw))

        if not matched_lines:
            missing.append(num)
            continue

        if num in CONDITIONAL:
            # any mention (real content or an explicit N/A line) satisfies it.
            continue

        # unconditional: at least one matching line must NOT be an N/A-only line.
        has_real_content = any("not applicable" not in ln for ln in matched_lines)
        if not has_real_content:
            missing.append(num)

    return missing


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check_dispatch_prompt.py <prompt_file>", file=sys.stderr)
        return 2
    text = open(sys.argv[1], encoding="utf-8").read()
    missing = check(text)
    if not missing:
        print("COMPLIANT")
        return 0
    print(f"NON-COMPLIANT missing elements: {missing}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
