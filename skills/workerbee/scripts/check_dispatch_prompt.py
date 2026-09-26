"""T003: check a dispatch prompt text file for the 14-element delegation contract.

Usage: python3 check_dispatch_prompt.py <prompt_file> [--with-handoff-lint] [--tier grunt]
       python3 check_dispatch_prompt.py <report_file> --with-handoff-lint --profile report
Exit 0 + prints "COMPLIANT" if all 14 elements present (and tier requirements met).
Exit 1 + prints missing element numbers if not.

--with-handoff-lint also runs the optional third-party handoff-lint tool from
$HOME/.claude/skills/handoff-lint/scripts/handoff_lint.py when it exists. When
absent, one line `handoff-lint NOT installed -> H1-H6 checked by hand` goes to
STDERR (STDOUT stays the machine-parseable verdict) and the exit code is the
14-element verdict alone. With --profile report the file is a delegate report,
not a prompt: the 14-element check is skipped and only handoff-lint runs.

--tier grunt adds Grunt-tier requirements: "files in scope:" and "stop rule:" with digit.

Element 1 (caveman) is conditional on the third-party skill: either the Skill-call
form (`caveman ultra`) or the emulation form
(`caveman NOT installed -> checked by hand`) satisfies it. Neither = missing.

Elements 2 and 3 (gate elements) require backtick in matching lines for real content.

Elements 10 and 11 are conditional: a line saying "not applicable" that names the
element satisfies them. All other elements (1-9, 12-14) are unconditional: a line
that mentions the keyword only to say "not applicable" does NOT satisfy them --
real content is required.
"""
from __future__ import annotations
import os
import subprocess
import sys

CONDITIONAL = {10, 11}
GATE_ELEMENTS = {2, 3}

# Each element: list of keyword phrases (any match = "mentioned").
KEYWORDS: dict[int, list[str]] = {
    1: ["caveman ultra", "caveman not installed -> checked by hand",
        "caveman not installed → checked by hand"],
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


def check(text: str, tier: str | None = None) -> list[int | str]:
    """Return list of missing element numbers (1-14) and tier-specific requirements.

    For tier="grunt", also check for "files in scope:" and "stop rule:" with digit.
    Missing tier requirements added as strings: "files-in-scope", "stop-rule".
    """
    lower = text.lower()
    missing: list[int | str] = []

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

        # For gate elements (2, 3): filter to lines with backticks only.
        if num in GATE_ELEMENTS:
            matched_lines = [ln for ln in matched_lines if "`" in ln]
            if not matched_lines:
                missing.append(num)
                continue

        # unconditional: at least one matching line must NOT be an N/A-only line.
        has_real_content = any("not applicable" not in ln for ln in matched_lines)
        if not has_real_content:
            missing.append(num)

    # Check tier-specific requirements.
    if tier == "grunt":
        # "files in scope:" line must start with this label (stripped).
        files_in_scope_found = any(ln.strip().startswith("files in scope:") for ln in lower.splitlines())
        if not files_in_scope_found:
            missing.append("files-in-scope")

        # "stop rule:" line must start with this label (stripped) and contain digit.
        has_stop_rule_with_digit = any(
            any(c.isdigit() for c in ln)
            for ln in lower.splitlines()
            if ln.strip().startswith("stop rule:")
        )
        if not has_stop_rule_with_digit:
            missing.append("stop-rule")

    return missing


HANDOFF_WARNING = "handoff-lint NOT installed -> H1-H6 checked by hand"


def run_handoff_lint(path: str, profile: str | None) -> int:
    """Run handoff-lint if installed; else warn on stderr. Returns lint exit code (0 if absent)."""
    script = os.path.join(os.environ.get("HOME", ""), ".claude", "skills",
                          "handoff-lint", "scripts", "handoff_lint.py")
    if not os.path.isfile(script):
        print(HANDOFF_WARNING, file=sys.stderr)
        return 0
    cmd = [sys.executable, script, path]
    if profile:
        cmd += ["--profile", profile]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        print(f"handoff-lint failed to start ({exc}) -> H1-H6 checked by hand", file=sys.stderr)
        return 0
    # lint output to stderr: stdout stays the 14-element verdict.
    sys.stderr.write(res.stdout + res.stderr)
    return res.returncode


def main() -> int:
    args = sys.argv[1:]
    with_lint = "--with-handoff-lint" in args
    args = [a for a in args if a != "--with-handoff-lint"]
    profile = None
    tier = None
    if "--profile" in args:
        k = args.index("--profile")
        if k + 1 >= len(args):
            print("--profile needs a value", file=sys.stderr)
            return 2
        profile = args[k + 1]
        del args[k:k + 2]
    if "--tier" in args:
        k = args.index("--tier")
        if k + 1 >= len(args):
            print("--tier needs a value", file=sys.stderr)
            return 2
        tier = args[k + 1]
        del args[k:k + 2]
    if len(args) != 1 or (profile and not with_lint):
        print("usage: check_dispatch_prompt.py <prompt_file> [--with-handoff-lint [--profile report]] [--tier grunt]",
              file=sys.stderr)
        return 2
    text = open(args[0], encoding="utf-8").read()
    if profile == "report":
        # delegate report, not a prompt: 14-element check does not apply.
        return 1 if run_handoff_lint(args[0], profile) else 0
    missing = check(text, tier=tier)
    if not missing:
        print("COMPLIANT")
    else:
        print(f"NON-COMPLIANT missing elements: {missing}")
    lint_rc = run_handoff_lint(args[0], profile) if with_lint else 0
    return 1 if (missing or lint_rc) else 0


if __name__ == "__main__":
    raise SystemExit(main())
