#!/usr/bin/env bash
# Test: install_skills.sh with empty HOME
# Asserts: exit 0, no /Users/ paths in manifest/installer, prints OPTIONAL-MISSING for absent optional skills

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Create temp HOME
TEMP_HOME="$(mktemp -d)"
trap "rm -rf '$TEMP_HOME'" EXIT

# Run installer with clean HOME
rc=0
output="$(HOME="$TEMP_HOME" bash "$REPO_ROOT/scripts/install_skills.sh" 2>&1)" || rc=$?

if [[ $rc -ne 0 ]]; then
  echo "FAIL: installer exited $rc"
  echo "$output"
  exit 1
fi

# Check for OPTIONAL-MISSING lines (expected for absent optional-user-scope skills)
if ! echo "$output" | grep -q "OPTIONAL-MISSING"; then
  echo "FAIL: no OPTIONAL-MISSING lines found in output"
  echo "$output"
  exit 1
fi

# Check for /Users/ paths in the scripts themselves
if grep -n '/Users/' "$REPO_ROOT/skills.requirements.txt" "$REPO_ROOT/scripts/install_skills.sh" > /dev/null 2>&1; then
  echo "FAIL: /Users/ paths found in manifest or installer"
  grep -n '/Users/' "$REPO_ROOT/skills.requirements.txt" "$REPO_ROOT/scripts/install_skills.sh" || true
  exit 1
fi

echo "SMOKE PASS"
exit 0
