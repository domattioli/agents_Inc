#!/usr/bin/env bash
set -euo pipefail

# codex-bridge up: Start the Codex Bridge server (idempotent)
# Args: [--port N] [--timeout N] [--workdir DIR] [--sandbox MODE] [--model M] [--tunnel] [--force]

# Check jq dependency
command -v jq >/dev/null || { echo "error: jq required (brew install jq)" >&2; exit 1; }

BASE="/Users/domattioli/Projects/claude-codex"
STATE_DIR="$HOME/.codex-bridge"
TOKEN_FILE="$STATE_DIR/token"
STATE_FILE="$STATE_DIR/state.json"
BRIDGE_LOG="$STATE_DIR/bridge.log"
TUNNEL_LOG="$STATE_DIR/tunnel.log"

PORT=8787
TIMEOUT=300
WORKDIR="$(pwd)"
SANDBOX="workspace-write"
MODEL=""
TUNNEL=false
FORCE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      PORT="$2"
      shift 2
      ;;
    --timeout)
      TIMEOUT="$2"
      shift 2
      ;;
    --workdir)
      WORKDIR="$2"
      shift 2
      ;;
    --sandbox)
      SANDBOX="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --tunnel)
      TUNNEL=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# Protect the one shared state file from silently retargeting ask.sh/status.sh.
if [[ -f "$STATE_FILE" && "$FORCE" != true ]]; then
  RECORDED_PORT=$(jq -r '.port // empty' "$STATE_FILE" 2>/dev/null || echo "")
  RECORDED_PID=$(jq -r '.pid // empty' "$STATE_FILE" 2>/dev/null || echo "")
  if [[ -n "$RECORDED_PORT" && "$RECORDED_PORT" != "$PORT" && "$RECORDED_PID" =~ ^[0-9]+$ ]] && \
     kill -0 "$RECORDED_PID" 2>/dev/null; then
    echo "error: bridge on port $RECORDED_PORT (PID $RECORDED_PID) is still running; refusing to replace shared state.json (use --force to override)" >&2
    exit 1
  fi
fi

# Create state dir
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"

# Create token file if missing
if [[ ! -f "$TOKEN_FILE" ]]; then
  openssl rand -hex 32 > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
fi

# Check if bridge is already running
BRIDGE_RUNNING=false
OLD_WORKDIR=""
OLD_SANDBOX=""
if curl -sf --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  BRIDGE_RUNNING=true
  # Read old config if it exists
  if [[ -f "$STATE_FILE" ]]; then
    OLD_WORKDIR=$(jq -r '.workdir // ""' "$STATE_FILE" 2>/dev/null || echo "")
    OLD_SANDBOX=$(jq -r '.sandbox // ""' "$STATE_FILE" 2>/dev/null || echo "")
  fi

  # Warn if config changed
  if [[ -n "$OLD_WORKDIR" && "$OLD_WORKDIR" != "$WORKDIR" ]] || [[ -n "$OLD_SANDBOX" && "$OLD_SANDBOX" != "$SANDBOX" ]]; then
    echo "warn: running bridge uses workdir=$OLD_WORKDIR sandbox=$OLD_SANDBOX; restart to apply new values" >&2
  fi

  echo "bridge already up on port $PORT"
else
  # Start the bridge
  TOKEN=$(cat "$TOKEN_FILE")
  export CODEX_BRIDGE_TOKEN="$TOKEN"

  BRIDGE_CMD="python3 $BASE/bridge.py --port $PORT --timeout $TIMEOUT --workdir $WORKDIR --sandbox $SANDBOX"
  if [[ -n "$MODEL" ]]; then
    BRIDGE_CMD="$BRIDGE_CMD --model $MODEL"
  fi

  nohup $BRIDGE_CMD >> "$BRIDGE_LOG" 2>&1 &
  BRIDGE_PID=$!

  # Poll for health (up to 10s)
  HEALTH_OK=false
  for i in {1..20}; do
    if curl -sf --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
      HEALTH_OK=true
      break
    fi
    sleep 0.5
  done

  if [[ "$HEALTH_OK" != true ]]; then
    echo "bridge failed to start on port $PORT" >&2
    echo "last 20 lines of $BRIDGE_LOG:" >&2
    tail -20 "$BRIDGE_LOG" >&2
    exit 1
  fi

  BRIDGE_RUNNING=true
fi

# Get current bridge PID
BRIDGE_PID=$(pgrep -f "bridge.py.*--port $PORT" | head -1 || echo "")

# Tunnel setup
TUNNEL_PID=""
TUNNEL_URL=""
if [[ "$TUNNEL" == true ]]; then
  if ! command -v cloudflared &>/dev/null; then
    echo "tunnel skipped: cloudflared not installed (brew install cloudflared)"
  else
    # Start tunnel
    nohup cloudflared tunnel --url "http://localhost:$PORT" >> "$TUNNEL_LOG" 2>&1 &
    TUNNEL_PID=$!

    # Poll for tunnel URL (up to 30s)
    for i in {1..60}; do
      if [[ -f "$TUNNEL_LOG" ]] && grep -q "https://[a-z0-9-]*\.trycloudflare\.com" "$TUNNEL_LOG" 2>/dev/null; then
        TUNNEL_URL=$(grep -o "https://[a-z0-9-]*\.trycloudflare\.com" "$TUNNEL_LOG" | head -1)
        break
      fi
      sleep 0.5
    done

    if [[ -z "$TUNNEL_URL" ]]; then
      echo "tunnel started but URL not found after 30s (PID $TUNNEL_PID, see $TUNNEL_LOG)"
    fi
  fi
fi

# Write state.json
STATE_JSON=$(python3 - "$BASE" "$PORT" "$BRIDGE_PID" "$TUNNEL_PID" "$TUNNEL_URL" "$WORKDIR" "$SANDBOX" "$TIMEOUT" "$MODEL" << 'PYTHON'
import json
import sys
from datetime import datetime

base = sys.argv[1]
port = int(sys.argv[2])
bridge_pid = sys.argv[3].strip()
tunnel_pid = sys.argv[4].strip()
tunnel_url = sys.argv[5].strip()
workdir = sys.argv[6]
sandbox = sys.argv[7]
timeout = int(sys.argv[8])
model = sys.argv[9].strip()

state = {
  "base": base,
  "port": port,
  "pid": int(bridge_pid) if bridge_pid else None,
  "url": f"http://127.0.0.1:{port}",
  "tunnel_url": tunnel_url or None,
  "tunnel_pid": int(tunnel_pid) if tunnel_pid else None,
  "workdir": workdir,
  "sandbox": sandbox,
  "timeout": timeout,
  "model": model or None,
  "started": datetime.utcnow().isoformat() + "Z"
}
print(json.dumps(state, indent=2))
PYTHON
)

echo "$STATE_JSON" > "$STATE_FILE"
chmod 600 "$STATE_FILE"

# Self-check: verify state.json is valid and non-null pid
if ! echo "$STATE_JSON" | jq . >/dev/null 2>&1; then
  echo "error: state file write failed (invalid JSON)" >&2
  exit 1
fi

STATE_PID=$(echo "$STATE_JSON" | jq -r '.pid // empty' 2>/dev/null)
if [[ "$BRIDGE_RUNNING" == true && -z "$STATE_PID" ]]; then
  echo "error: state file write failed (pid is null)" >&2
  exit 1
fi

# Print summary
echo "codex-bridge: up"
echo "  local:   http://127.0.0.1:$PORT"
if [[ -n "$TUNNEL_URL" ]]; then
  echo "  tunnel:  $TUNNEL_URL"
else
  echo "  tunnel:  none"
fi
echo "  pid:     ${BRIDGE_PID:-unknown}"
echo "  workdir: $WORKDIR"
echo "  sandbox: $SANDBOX"
echo "  token:   $TOKEN_FILE"
