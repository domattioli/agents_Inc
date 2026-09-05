#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

parse_exec_args "$@"

"$SCRIPT_DIR/preflight.sh" >&2

if [[ "$INVALIDATE_CACHE" == true ]]; then
  rm -f "$STATE_FILE"
fi

REMOTE_DIR=$(resolve_repository_path "$REQUESTED_DIR")
REMOTE_COMMAND=$(build_remote_command "$REMOTE_DIR" "${EXEC_COMMAND[@]}")
STATUS_FILE=$(mktemp "${TMPDIR:-/tmp}/codespace-exec-status.XXXXXX")
trap 'rm -f "$STATUS_FILE"' EXIT

set +e
codespace_ssh "$REMOTE_COMMAND" | capture_remote_stdout "$STATUS_FILE"
PIPELINE_STATUS=("${PIPESTATUS[@]}")
set -e

GH_STATUS=${PIPELINE_STATUS[0]}
if FINAL_STATUS=$(resolve_remote_status "$STATUS_FILE" "$GH_STATUS"); then
  exit "$FINAL_STATUS"
fi
exit 1
