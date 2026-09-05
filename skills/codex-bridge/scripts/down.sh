#!/usr/bin/env bash
set -euo pipefail

# codex-bridge down: Stop the Codex Bridge server and tunnel

# Check jq dependency
command -v jq >/dev/null || { echo "error: jq required (brew install jq)" >&2; exit 1; }

STATE_DIR="$HOME/.codex-bridge"
STATE_FILE="$STATE_DIR/state.json"

if [[ ! -f "$STATE_FILE" ]]; then
  echo "nothing to stop"
  exit 0
fi

# Read state
BRIDGE_PID=$(jq -r '.pid // empty' "$STATE_FILE" 2>/dev/null || echo "")
TUNNEL_PID=$(jq -r '.tunnel_pid // empty' "$STATE_FILE" 2>/dev/null || echo "")
PORT=$(jq -r '.port // empty' "$STATE_FILE" 2>/dev/null || echo "8787")
TUNNEL_URL=$(jq -r '.tunnel_url // empty' "$STATE_FILE" 2>/dev/null || echo "")

STOPPED=()

# Kill bridge
if [[ -n "$BRIDGE_PID" ]] && kill -0 "$BRIDGE_PID" 2>/dev/null; then
  kill -TERM "$BRIDGE_PID" 2>/dev/null || true
  sleep 1
  if kill -0 "$BRIDGE_PID" 2>/dev/null; then
    kill -KILL "$BRIDGE_PID" 2>/dev/null || true
  fi
  STOPPED+=("bridge (PID $BRIDGE_PID)")
fi

# Kill tunnel
if [[ -n "$TUNNEL_PID" ]] && kill -0 "$TUNNEL_PID" 2>/dev/null; then
  kill -TERM "$TUNNEL_PID" 2>/dev/null || true
  sleep 1
  if kill -0 "$TUNNEL_PID" 2>/dev/null; then
    kill -KILL "$TUNNEL_PID" 2>/dev/null || true
  fi
  STOPPED+=("tunnel (PID $TUNNEL_PID)")
fi

# Clean up state file
rm -f "$STATE_FILE"

if [[ ${#STOPPED[@]} -eq 0 ]]; then
  echo "nothing to stop"
else
  echo "stopped: ${STOPPED[*]}"
fi

exit 0
