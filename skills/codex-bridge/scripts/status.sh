#!/usr/bin/env bash
set -euo pipefail

# codex-bridge status: Check bridge health and print state

# Check jq dependency
command -v jq >/dev/null || { echo "error: jq required (brew install jq)" >&2; exit 1; }

STATE_DIR="$HOME/.codex-bridge"
STATE_FILE="$STATE_DIR/state.json"
TOKEN_FILE="$STATE_DIR/token"
GEMINI_KEY_FILE="$STATE_DIR/gemini-key"

if [[ ! -f "$STATE_FILE" ]]; then
  echo "not running"
  exit 1
fi

# Read state
PORT=$(jq -r '.port // 8787' "$STATE_FILE" 2>/dev/null || echo "8787")
URL=$(jq -r '.url // ""' "$STATE_FILE" 2>/dev/null || echo "http://127.0.0.1:$PORT")
TUNNEL_URL=$(jq -r '.tunnel_url // empty' "$STATE_FILE" 2>/dev/null || echo "")
WORKDIR=$(jq -r '.workdir // ""' "$STATE_FILE" 2>/dev/null || echo "")
SANDBOX=$(jq -r '.sandbox // ""' "$STATE_FILE" 2>/dev/null || echo "")
STARTED=$(jq -r '.started // ""' "$STATE_FILE" 2>/dev/null || echo "")

# Check health
HEALTH_OK=false
THREAD_ID=""
TOKEN=""
LIVE_SANDBOX=""

if [[ -f "$TOKEN_FILE" ]]; then
  TOKEN=$(cat "$TOKEN_FILE")
fi

if curl -sf --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  HEALTH_OK=true

  # Get current session/thread and sandbox
  if [[ -n "$TOKEN" ]]; then
    SESSION=$(curl -sf \
      -H "X-Auth-Token: $TOKEN" \
      --max-time 2 \
      "http://127.0.0.1:$PORT/session" 2>/dev/null || echo "")

    if [[ -n "$SESSION" ]]; then
      THREAD_ID=$(echo "$SESSION" | jq -r '.thread_id // ""' 2>/dev/null || echo "")
      LIVE_SANDBOX=$(echo "$SESSION" | jq -r '.sandbox // ""' 2>/dev/null || echo "")
    fi
  fi
fi

# Calculate uptime (parse STARTED as UTC, compare against UTC now)
UPTIME=""
if [[ -n "$STARTED" ]]; then
  # Strip microseconds from ISO format (e.g., "2026-09-02T19:58:30.123456Z" -> "2026-09-02T19:58:30Z")
  STARTED_CLEAN=$(echo "$STARTED" | sed 's/\.[0-9]*Z$/Z/')
  # Parse as UTC epoch
  START_EPOCH=$(date -j -u -f "%Y-%m-%dT%H:%M:%SZ" "$STARTED_CLEAN" +%s 2>/dev/null || echo "0")
  # Get current UTC epoch
  NOW_EPOCH=$(date -u +%s)
  if [[ "$START_EPOCH" != "0" && "$NOW_EPOCH" -ge "$START_EPOCH" ]]; then
    UPTIME_SECS=$((NOW_EPOCH - START_EPOCH))
    UPTIME_MINS=$((UPTIME_SECS / 60))
    UPTIME_HRS=$((UPTIME_SECS / 3600))
    UPTIME_DAYS=$((UPTIME_SECS / 86400))
    if [[ $UPTIME_SECS -lt 60 ]]; then
      UPTIME="${UPTIME_SECS}s"
    elif [[ $UPTIME_MINS -lt 60 ]]; then
      UPTIME="${UPTIME_MINS}m"
    elif [[ $UPTIME_HRS -lt 24 ]]; then
      UPTIME="${UPTIME_HRS}h $(($UPTIME_MINS % 60))m"
    else
      UPTIME="${UPTIME_DAYS}d $((($UPTIME_SECS % 86400) / 3600))h"
    fi
  else
    UPTIME="unknown"
  fi
fi

# Check gemini availability
GEMINI_STATUS="not configured"
if [[ -f "$GEMINI_KEY_FILE" ]]; then
  GEMINI_STATUS="available"
fi

# Print status
if [[ "$HEALTH_OK" == true ]]; then
  echo "running"
else
  echo "not responding"
fi

echo "  url:     $URL"
if [[ -n "$TUNNEL_URL" ]]; then
  echo "  tunnel:  $TUNNEL_URL"
fi
if [[ -n "$THREAD_ID" ]]; then
  echo "  thread:  $THREAD_ID"
fi
if [[ -n "$WORKDIR" ]]; then
  echo "  workdir: $WORKDIR"
fi
# Report sandbox: prefer live value from /session, show discrepancy if any
if [[ -n "$LIVE_SANDBOX" ]]; then
  if [[ "$LIVE_SANDBOX" != "$SANDBOX" ]]; then
    echo "  sandbox: $LIVE_SANDBOX  (state.json says $SANDBOX — restart to reconcile)"
  else
    echo "  sandbox: $LIVE_SANDBOX"
  fi
elif [[ -n "$SANDBOX" ]]; then
  echo "  sandbox: $SANDBOX"
fi
echo "  gemini:  $GEMINI_STATUS"
if [[ -n "$UPTIME" ]]; then
  echo "  uptime:  $UPTIME"
fi

if [[ "$HEALTH_OK" != true ]]; then
  exit 1
fi

exit 0
