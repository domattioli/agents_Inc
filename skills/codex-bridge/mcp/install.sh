#!/bin/bash
# Register the DelegateAgent MCP server at user scope. Default: PRINT the command only.
set -euo pipefail
PY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/codex_agent_mcp.py"
if [[ "${1:-}" == "--apply" ]]; then
    command -v claude >/dev/null 2>&1 || { echo "NOTE: claude CLI not found -> MCP not registered; run the printed command after installing Claude." >&2; exit 0; }
    claude mcp add --scope user delegate-agent -- python3 "$PY"
else
    echo "claude mcp add --scope user delegate-agent -- python3 \"$PY\""
    echo "(print-only; pass --apply to run it)"
fi
