#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

REQUESTED_DIR=""
INVALIDATE_CACHE=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      [[ $# -ge 2 ]] || { echo "error: --dir requires a path" >&2; exit 2; }
      REQUESTED_DIR="$2"
      shift 2
      ;;
    --invalidate-cache)
      INVALIDATE_CACHE=true
      shift
      ;;
    *)
      echo "usage: status.sh [--dir PATH] [--invalidate-cache]" >&2
      exit 2
      ;;
  esac
done

PREFLIGHT_OUTPUT=""
if ! PREFLIGHT_OUTPUT=$("$SCRIPT_DIR/preflight.sh" 2>&1); then
  echo "codespace: $CODESPACE_NAME"
  echo "scope preflight: failed"
  printf '%s\n' "$PREFLIGHT_OUTPUT" >&2
  exit 1
fi
printf '%s\n' "$PREFLIGHT_OUTPUT"

if [[ "$INVALIDATE_CACHE" == true ]]; then
  rm -f "$STATE_FILE"
fi

REMOTE_DIR=$(resolve_repository_path "$REQUESTED_DIR")
echo "repository: $REMOTE_DIR"

STATUS_COMMAND="cd $(shell_quote "$REMOTE_DIR") && "
STATUS_COMMAND+="printf 'hostname: %s\\n' \"\$(hostname)\" && "
STATUS_COMMAND+="printf 'branch: %s\\n' \"\$(git branch --show-current 2>/dev/null || true)\" && "
STATUS_COMMAND+="if test -z \"\$(git status --porcelain 2>/dev/null)\"; then "
STATUS_COMMAND+="echo 'working tree: clean'; else echo 'working tree: dirty'; fi"

codespace_ssh "$STATUS_COMMAND"
