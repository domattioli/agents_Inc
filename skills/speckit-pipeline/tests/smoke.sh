#!/bin/bash
# Shell smoke for speckit-pipeline resolve_phases.py + preflight.sh.
# Asserts default resolve, each error exit code, permutation invariance,
# --list count, and preflight pass/fail. Run from repo root:
#   bash skills/speckit-pipeline/tests/smoke.sh

R="skills/speckit-pipeline/scripts/resolve_phases.py"
P="skills/speckit-pipeline/scripts/preflight.sh"
FAILS=0

check() {
    # $1 = label, $2 = expected, $3 = actual
    if [[ "$2" == "$3" ]]; then
        echo "PASS: $1"
    else
        echo "FAIL: $1 (expected $2, got $3)"
        FAILS=$((FAILS+1))
    fi
}

# 1. default resolve exit 0 + 7 lines
set +e
OUT="$(python3 "$R")"; RC=$?
set -e 2>/dev/null || true
LINES="$(printf '%s\n' "$OUT" | grep -c .)"
if [[ "$RC" == "0" && "$LINES" == "7" ]]; then
    echo "PASS: default resolve exit 0, 7 lines"
else
    echo "FAIL: default resolve (rc=$RC lines=$LINES)"
    FAILS=$((FAILS+1))
fi

# 2-6. error exit codes
set +e
python3 "$R" --skip implment >/dev/null 2>&1; check "unknown phase → 10" 10 $?
python3 "$R" --skip clarify --add clarify >/dev/null 2>&1; check "skip/add conflict → 11" 11 $?
python3 "$R" --add plan >/dev/null 2>&1; check "add not insertable → 12" 12 $?
python3 "$R" --skip specify >/dev/null 2>&1; check "skip required → 13" 13 $?
python3 "$R" --skip plan >/dev/null 2>&1; check "dependency break → 14" 14 $?

# 7. permutation invariance
A="$(python3 "$R" --add commit,constitution --json 2>/dev/null)"
B="$(python3 "$R" --add constitution,commit --json 2>/dev/null)"
if [[ "$A" == "$B" ]]; then
    echo "PASS: permutation invariance"
else
    echo "FAIL: permutation invariance (A != B)"
    FAILS=$((FAILS+1))
fi

# 8. --list exit 0 + 11 phases
LOUT="$(python3 "$R" --list 2>/dev/null)"; LRC=$?
LCOUNT="$(printf '%s\n' "$LOUT" | grep -c .)"
if [[ "$LRC" == "0" && "$LCOUNT" == "11" ]]; then
    echo "PASS: --list exit 0, 11 phases"
else
    echo "FAIL: --list (rc=$LRC count=$LCOUNT)"
    FAILS=$((FAILS+1))
fi

# 9. preflight all-valid → 0
bash "$P" specify clarify plan tasks checklist analyze implement >/dev/null 2>&1
check "preflight valid phases → 0" 0 $?

# 10. preflight bogus phase → 1
bash "$P" bogusphase >/dev/null 2>&1
check "preflight bogus phase → 1" 1 $?
set -e 2>/dev/null || true

if (( FAILS > 0 )); then
    echo "SMOKE FAILED: $FAILS case(s)"
    exit 1
fi
echo "SMOKE OK"
exit 0
