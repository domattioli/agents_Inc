#!/bin/bash
set -euo pipefail

OFFLINE=0
[[ "${1:-}" == "--offline" ]] && OFFLINE=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/../codex_agent_mcp.py"

# Create temp directory and named pipes for bash 3.2 compatibility
TMPDIR_FIFO=$(mktemp -d)
REQ_FIFO="$TMPDIR_FIFO/request"
RESP_FIFO="$TMPDIR_FIFO/response"

mkfifo "$REQ_FIFO" "$RESP_FIFO"

# Start MCP server in background with stdin/stdout redirected to fifos
if [[ "$OFFLINE" -eq 1 ]]; then
    # Hermetic: ignore the caller's roster and env maps so the built-in default is what is checked.
    export HOME="$TMPDIR_FIFO"
    unset AGENTS_INC_MODEL_MAP CODEXAGENT_MODEL_MAP
fi
python3 "$PYTHON_SCRIPT" < "$REQ_FIFO" > "$RESP_FIFO" &
MCPPROC_PID=$!

trap "kill $MCPPROC_PID 2>/dev/null || true; rm -rf $TMPDIR_FIFO" EXIT

# Open file descriptors for communication
exec 3>"$REQ_FIFO"
exec 4<"$RESP_FIFO"

# Send initialize
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' >&3
read -u 4 response
echo "$response"

# Send notifications/initialized (no response expected)
echo '{"jsonrpc":"2.0","method":"notifications/initialized"}' >&3

# Send tools/list
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' >&3
read -u 4 response
echo "$response"

if [[ "$OFFLINE" -eq 1 ]]; then
    # Offline: stop after tools/list; never send tools/call (would shell out to codex).
    if echo "$response" | python3 -c 'import sys,json; t=json.loads(sys.stdin.read())["result"]["tools"]; d=[x for x in t if x["name"]=="DelegateAgent"]; sys.exit(0 if d and d[0]["inputSchema"]["properties"]["model"]["enum"] == ["luna"] else 1)'; then
        echo "SMOKE PASS"
        exit 0
    fi
    echo "SMOKE FAIL"
    exit 1
fi

# Send tools/call with test prompt
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"DelegateAgent","arguments":{"prompt":"Reply with exactly: MCP_OK"}}}' >&3
read -u 4 response
echo "$response"

# Check if MCP_OK is in the response
if echo "$response" | grep -q "MCP_OK"; then
    echo "SMOKE PASS"
    exit 0
else
    echo "SMOKE FAIL"
    exit 1
fi
