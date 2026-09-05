#!/usr/bin/env bash
set -euo pipefail

# codex-bridge ask: Send a prompt to the persistent Codex session
# Usage: ask.sh [--model M] [--reset] [--raw] "prompt" or read from stdin

# Check jq dependency
command -v jq >/dev/null || { echo "error: jq required (brew install jq)" >&2; exit 1; }

STATE_DIR="$HOME/.codex-bridge"
STATE_FILE="$STATE_DIR/state.json"
TOKEN_FILE="$STATE_DIR/token"

# Defaults
PORT=8787
TOKEN=""
MODEL=""
RESET=false
RAW=false
PROMPT=""
TIMEOUT=300

# Check if state.json exists to get port/timeout
if [[ -f "$STATE_FILE" ]]; then
  PORT=$(jq -r '.port // 8787' "$STATE_FILE" 2>/dev/null || echo "8787")
  TIMEOUT=$(jq -r '.timeout // 300' "$STATE_FILE" 2>/dev/null || echo "300")
fi

# Read token
if [[ -f "$TOKEN_FILE" ]]; then
  TOKEN=$(cat "$TOKEN_FILE")
fi

if [[ -z "$TOKEN" ]]; then
  echo "error: token file not found at $TOKEN_FILE" >&2
  exit 1
fi

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)
      MODEL="$2"
      shift 2
      ;;
    --reset)
      RESET=true
      shift
      ;;
    --raw)
      RAW=true
      shift
      ;;
    *)
      # Positional: prompt text
      PROMPT="$1"
      shift
      ;;
  esac
done

# Read from stdin if no prompt provided
if [[ -z "$PROMPT" ]]; then
  PROMPT=$(cat)
fi

if [[ -z "$PROMPT" ]]; then
  echo "error: no prompt provided" >&2
  exit 1
fi

# Build JSON body with python3 (safe escaping)
# Export PROMPT so it's available to python3
export PROMPT
export RESET
export MODEL
JSON_BODY=$(python3 << 'PYTHON'
import json
import os

body = {
  "prompt": os.environ.get('PROMPT', ''),
  "reset": os.environ.get('RESET') == 'true'
}
if os.environ.get('MODEL'):
  body['model'] = os.environ.get('MODEL')

print(json.dumps(body))
PYTHON
)

# POST to /prompt
CURL_MAX_TIME=$((TIMEOUT + 30))
RESPONSE=$(curl -s -w '\n%{http_code}' \
  -H "X-Auth-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  --max-time "$CURL_MAX_TIME" \
  -X POST \
  -d "$JSON_BODY" \
  "http://127.0.0.1:$PORT/prompt" 2>&1 || echo "")

# Split response and status code (last line)
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

# Handle curl transport failure
if [[ -z "$HTTP_CODE" || ! "$HTTP_CODE" =~ ^[0-9]+$ ]]; then
  echo "error: cannot reach bridge at 127.0.0.1:$PORT" >&2
  exit 1
fi

# Handle HTTP errors
if [[ "$HTTP_CODE" != "200" ]]; then
  ERROR_MSG=$(echo "$BODY" | jq -r '.error // .' 2>/dev/null || echo "$BODY")
  echo "bridge error $HTTP_CODE: $ERROR_MSG" >&2
  exit 1
fi

RESPONSE="$BODY"

# Check if response is valid JSON
if ! echo "$RESPONSE" | jq . >/dev/null 2>&1; then
  echo "error: invalid JSON response" >&2
  echo "$RESPONSE" >&2
  exit 1
fi

# Check for error in response
ERROR=$(echo "$RESPONSE" | jq -r '.error // empty' 2>/dev/null)
if [[ -n "$ERROR" ]]; then
  echo "error: $ERROR" >&2
  exit 1
fi

# Output
if [[ "$RAW" == true ]]; then
  echo "$RESPONSE"
else
  # Extract response text
  RESP_TEXT=$(echo "$RESPONSE" | jq -r '.response // ""' 2>/dev/null)
  THREAD_ID=$(echo "$RESPONSE" | jq -r '.thread_id // ""' 2>/dev/null)
  USAGE=$(echo "$RESPONSE" | jq -r '.usage // {}' 2>/dev/null)
  IN_TOKENS=$(echo "$USAGE" | jq -r '.input_tokens // 0' 2>/dev/null)
  OUT_TOKENS=$(echo "$USAGE" | jq -r '.output_tokens // 0' 2>/dev/null)

  echo "$RESP_TEXT"
  echo "[thread $THREAD_ID | in $IN_TOKENS out $OUT_TOKENS]" >&2
fi
