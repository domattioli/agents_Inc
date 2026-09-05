#!/bin/bash
set -euo pipefail

# quota_probe.sh - Check if Codex 5-hour usage limit is hit
# Usage: quota_probe.sh [--model MODEL]
# Exit codes: 0=QUOTA_OK, 1=QUOTA_UNKNOWN, 2=QUOTA_EXHAUSTED

MODEL="gpt-5.4-mini"

# Parse --model flag
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model) MODEL="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# Step (a): Check help output for usage/limits/status subcommands
if command -v codex &>/dev/null; then
  {
    codex --help 2>&1 || true
    codex exec --help 2>&1 || true
  } | grep -qiE 'usage|limits?|status' 2>/dev/null || true
fi

# Step (b): Send minimal probe to check quota status
output=$(echo "reply PONG" | codex exec -m "$MODEL" -s read-only --skip-git-repo-check - 2>&1 || true)

# Parse output for quota exhaustion
if echo "$output" | grep -qiE 'usage limit|rate limit|try again at'; then
  # Extract reset time if present
  reset_time=$(echo "$output" | grep -oiE 'try again at [0-9:]+\s*[AP]M' | head -1 || echo "unknown")
  echo "QUOTA_EXHAUSTED reset=$reset_time"
  exit 2
fi

# Check for successful PONG response
if echo "$output" | grep -q "PONG"; then
  echo "QUOTA_OK"
  exit 0
fi

# Unknown response
last_line=$(echo "$output" | tail -1)
echo "QUOTA_UNKNOWN $last_line"
exit 1
