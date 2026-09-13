#!/bin/bash
# Preflight checks for speckit-pipeline phase execution.
# Verifies that required skills exist for each phase and .specify/ scaffold is present.
#
# Usage: preflight.sh [--legacy] <phase1> [phase2] ...
# Exit: 0 if all checks pass, 1 if any check fails
#
# New mode (default, no --legacy): a missing .specify/scripts/bash/check-prerequisites.sh
# is a warning, not a preflight failure (v1.5) — several phase skills call it themselves
# at their own Setup step, but a consumer repo not scaffolded by upstream spec-kit may
# not carry it. Legacy mode (--legacy) keeps v1.4 behavior: this script does not check
# for it at all; the affected phase fails later, at its own Setup step.

set -euo pipefail

LEGACY=0
if [[ "${1:-}" == "--legacy" ]]; then
    LEGACY=1
    shift
fi

# Map phase id to skill directory
declare -A SKILL_DIR_MAP=(
    [constitution]="speckit-constitution"
    [specify]="speckit-specify"
    [clarify]="speckit-clarify"
    [plan]="speckit-plan"
    [tasks]="speckit-tasks"
    [tasks-to-issues]="speckit-taskstoissues"
    [split]="speckit-split"
    [checklist]="speckit-checklist"
    [analyze]="speckit-analyze"
    [implement]="speckit-implement"
    [commit]="speckit-git-commit"
)

PASSED=0
FAILED=0

# Check each phase's skill exists
for phase_id in "$@"; do
    skill_dir="${SKILL_DIR_MAP[$phase_id]:-}"

    if [[ -z "$skill_dir" ]]; then
        echo "[MISS] Phase '$phase_id' not in map"
        FAILED=$((FAILED+1))
        continue
    fi

    skill_path="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/$skill_dir/SKILL.md"

    if [[ -f "$skill_path" ]]; then
        echo "[OK] $phase_id → $skill_dir/SKILL.md"
        PASSED=$((PASSED+1))
    else
        echo "[MISS] $phase_id → $skill_dir/SKILL.md (not found)"
        FAILED=$((FAILED+1))
    fi
done

# Check .specify/ directory exists
if [[ -d ".specify" ]]; then
    echo "[OK] .specify/ directory present"
    PASSED=$((PASSED+1))
else
    echo "[MISS] .specify/ directory not found"
    FAILED=$((FAILED+1))
fi

# New mode only: check-prerequisites.sh presence is a warning, never a preflight failure.
if [[ "$LEGACY" -eq 0 ]]; then
    if [[ -f ".specify/scripts/bash/check-prerequisites.sh" ]]; then
        echo "[OK] .specify/scripts/bash/check-prerequisites.sh present"
        PASSED=$((PASSED+1))
    else
        echo "WARN: .specify/scripts/bash/check-prerequisites.sh not found — phases that depend on it may fail at their own Setup step"
    fi
fi

# spec-010 (contracts C5): surface open-mandate WARN lines after the .specify/ check.
# Never affects this script's exit code -- agent.sh may not exist on this machine/path.
AGENT_SH="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../codex-bridge/scripts" 2>/dev/null && pwd)/agent.sh"
if [[ -n "${AGENT_SH:-}" && -x "$AGENT_SH" ]]; then
    "$AGENT_SH" mandate list 2>&1 >/dev/null | grep '^WARN:' || true
fi

# Summary
if (( FAILED > 0 )); then
    exit 1
fi

exit 0
