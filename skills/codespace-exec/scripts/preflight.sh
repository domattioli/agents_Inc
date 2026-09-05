#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

command -v gh >/dev/null 2>&1 || {
  echo "error: GitHub CLI (gh) is required; install it and ensure it is on PATH" >&2
  exit 10
}

if ! AUTH_OUTPUT=$(gh auth status 2>&1); then
  echo "error: GitHub CLI is not authenticated; run: gh auth login -h github.com" >&2
  [[ -n "$AUTH_OUTPUT" ]] && printf '%s\n' "$AUTH_OUTPUT" >&2
  exit 11
fi

if ! LIST_OUTPUT=$(gh codespace list --json name,state --jq '.[] | [.name, .state] | @tsv' 2>&1); then
  if grep -qiE 'HTTP 403|codespace.*scope|scope.*codespace' <<< "$LIST_OUTPUT"; then
    echo "error: GitHub CLI authentication is missing the codespace scope" >&2
    echo "remedy: gh auth refresh -h github.com -s codespace" >&2
    exit 12
  fi
  echo "error: could not list Codespaces: $LIST_OUTPUT" >&2
  exit 14
fi

CODESPACE_STATE=""
while IFS=$'\t' read -r listed_name listed_state; do
  if [[ "$listed_name" == "$CODESPACE_NAME" ]]; then
    CODESPACE_STATE="$listed_state"
    break
  fi
done <<< "$LIST_OUTPUT"

if [[ -z "$CODESPACE_STATE" ]]; then
  echo "error: required Codespace '$CODESPACE_NAME' was not found; no replacement will be created" >&2
  exit 13
fi

case "$CODESPACE_STATE" in
  Unavailable|Failed)
    echo "error: required Codespace '$CODESPACE_NAME' is $CODESPACE_STATE; no replacement will be created" >&2
    exit 15
    ;;
esac

echo "codespace: $CODESPACE_NAME"
echo "state: $CODESPACE_STATE"
echo "scope preflight: passed"
