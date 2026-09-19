#!/bin/bash
set -euo pipefail

# Model map: built-in defaults < ~/.config/agents-inc/roster.json < AGENTS_INC_MODEL_MAP < CODEXAGENT_MODEL_MAP
# (JSON object or path to JSON file), resolved by mcp/codex_agent_mcp.py --resolve-model. --slug passes a raw slug.
MCP_PY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../mcp/codex_agent_mcp.py"

MODEL="luna"
RAW_SLUG=""
PROMPT_ARGS=()

# Parse flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)
            MODEL="$2"
            shift 2
            ;;
        --slug)
            RAW_SLUG="$2"
            shift 2
            ;;
        *)
            # Everything else is part of prompt
            PROMPT_ARGS+=("$1")
            shift
            ;;
    esac
done

if [[ -n "$RAW_SLUG" ]]; then
    SLUG="$RAW_SLUG"
elif ! SLUG="$(python3 "$MCP_PY" --resolve-model "$MODEL")"; then
    echo "Error: invalid model '$MODEL'. Allowed: $(python3 "$MCP_PY" --list-models)" >&2
    exit 1
fi

if [[ ${#PROMPT_ARGS[@]} -eq 0 ]]; then
    echo "Error: prompt required." >&2
    exit 1
fi

# Join prompt args with space
PROMPT="${PROMPT_ARGS[@]}"

TMPFILE=$(mktemp)
STDERR_FILE=$(mktemp)
trap "rm -f '$TMPFILE' '$STDERR_FILE'" EXIT

TIMEOUT_CMD=""
if command -v timeout &>/dev/null; then
    TIMEOUT_CMD="timeout"
elif command -v gtimeout &>/dev/null; then
    TIMEOUT_CMD="gtimeout"
fi

TIMEOUT_VAL="${CODEXAGENT_TIMEOUT:-300}"

CODEX_EXIT=0
if [[ -n "$TIMEOUT_CMD" ]]; then
    "$TIMEOUT_CMD" "$TIMEOUT_VAL" codex exec -m "$SLUG" -s read-only --skip-git-repo-check -o "$TMPFILE" -- "$PROMPT" 2>"$STDERR_FILE" >/dev/null || CODEX_EXIT=$?
else
    codex exec -m "$SLUG" -s read-only --skip-git-repo-check -o "$TMPFILE" -- "$PROMPT" 2>"$STDERR_FILE" >/dev/null || CODEX_EXIT=$?
fi

if [[ $CODEX_EXIT -ne 0 ]]; then
    cat "$STDERR_FILE" >&2
    exit $CODEX_EXIT
fi

if [[ ! -s "$TMPFILE" ]]; then
    if [[ -s "$STDERR_FILE" ]]; then
        cat "$STDERR_FILE" >&2
    fi
    echo "Error: empty result from codex exec." >&2
    exit 1
fi

cat "$TMPFILE"
