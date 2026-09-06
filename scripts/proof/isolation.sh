#!/usr/bin/env bash
set -u
repo="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$repo" || exit 1
failed=0
for provider in claude codex; do
  output="$(scripts/isolation_probe.sh "$provider" 2>&1)"
  status=$?
  while IFS= read -r line; do
    [ -n "$line" ] && printf '%s %s\n' "$provider" "$line"
  done <<<"$output"
  if grep -q ' LEAK' <<<"$output"; then
    printf '%s RESULT LEAK\n' "$provider"
    failed=1
  elif grep -q ' INCONCLUSIVE' <<<"$output" || [ "$status" -ne 0 ]; then
    printf '%s RESULT INCONCLUSIVE\n' "$provider"
    failed=1
  else
    printf '%s RESULT CLEAN\n' "$provider"
  fi
done
exit "$failed"
