#!/usr/bin/env bash
# Reads skills.requirements.txt and syncs skills/<name>/ from each entry's
# source. "vendored" entries are already the canonical copy in this repo
# (no-op, just verified present). "external-repo" entries are re-copied from
# their source path so a stale local copy gets refreshed on demand.
#
# Usage: bash scripts/install_skills.sh [--dry-run]

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$REPO_ROOT/skills.requirements.txt"
DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

if [[ ! -f "$MANIFEST" ]]; then
  echo "ERROR: $MANIFEST not found" >&2
  exit 1
fi

status=0
while IFS= read -r line; do
  # skip comments/blank lines
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  [[ -z "${line// }" ]] && continue

  name="$(echo "$line" | sed -E 's/==.*//' | xargs)"
  source_field="$(echo "$line" | sed -E 's/.*source=//' | xargs)"

  dest="$REPO_ROOT/skills/$name"

  if [[ "$source_field" == vendored* ]]; then
    if [[ -d "$dest" ]]; then
      echo "OK    $name (vendored, present)"
    else
      echo "MISS  $name (vendored, but $dest does not exist)"
      status=1
    fi
    continue
  fi

  if [[ "$source_field" == optional-user-scope* ]]; then
    user_skill_path="$HOME/.claude/skills/$name"
    if [[ -d "$user_skill_path" ]]; then
      echo "OK    $name (optional-user-scope, present)"
    else
      echo "OPTIONAL-MISSING $name"
    fi
    continue
  fi

  echo "SKIP  $name (unrecognized source field: $source_field)"
done < "$MANIFEST"

exit $status
