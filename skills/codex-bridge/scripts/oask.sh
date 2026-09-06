#!/usr/bin/env bash
set -euo pipefail

# codex-bridge oask: Send a prompt to OpenRouter API (free tier only)
# Usage: oask.sh [--file PATH]... [--glob PATTERN] [--raw] ["prompt"]

if [[ "${WORKERBEES_GOVERNANCE:-off}" != "off" ]]; then
  echo "oask: REFUSED — legacy wrappers are disabled in governed lanes" >&2
  exit 3
fi

# Check required tools
command -v jq >/dev/null || { echo "error: jq required" >&2; exit 1; }

KEY_DIR="$HOME/.codex-bridge"
KEY_FILE="$KEY_DIR/openrouter-key"
USAGE_LOG="$KEY_DIR/usage.jsonl"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Defaults
MODEL="nvidia/nemotron-3-ultra-550b-a55b:free"
RAW=false
OASK_TIMEOUT="${OASK_TIMEOUT:-180}"
OASK_CONNECT_TIMEOUT="${OASK_CONNECT_TIMEOUT:-10}"
PROMPT=""
DECLARE_FILES=()
DECLARE_GLOBS=()
RESOLVED_FILES=()

# SPEND GUARD: operator rule is spend nothing on OpenRouter.
# Only ":free" models are permitted. Paid model IDs are refused outright.
check_spend_guard() {
  case "$MODEL" in
    *:free) ;;
    *)
      echo "oask: REFUSED — '$MODEL' is not a ':free' model." >&2
      echo "oask: operator rule is spend nothing on OpenRouter." >&2
      exit 3
      ;;
  esac
}

# Load key from env or file
if [[ -z "${OPEN_ROUTER_API_KEY:-}" ]]; then
  if [[ -f "$KEY_FILE" ]]; then
    OPEN_ROUTER_API_KEY=$(cat "$KEY_FILE")
  fi
fi

# Fallback: read from ~/Projects/.env if key is missing/empty/placeholder
if [[ -z "${OPEN_ROUTER_API_KEY:-}" ]] || [[ ${#OPEN_ROUTER_API_KEY} -lt 20 ]]; then
  if [[ -f "$HOME/Projects/.env" ]]; then
    ENV_KEY=$(grep -m1 -E '^OPENROUTER_API_KEY=' "$HOME/Projects/.env" 2>/dev/null | cut -d= -f2- || true)
    if [[ -n "$ENV_KEY" ]]; then
      ENV_KEY="${ENV_KEY%\"}"
      ENV_KEY="${ENV_KEY#\"}"
      if [[ ${#ENV_KEY} -ge 20 ]]; then
        OPEN_ROUTER_API_KEY="$ENV_KEY"
      fi
    fi
  fi
fi

if [[ -z "${OPEN_ROUTER_API_KEY:-}" ]] || [[ ${#OPEN_ROUTER_API_KEY} -lt 20 ]]; then
  echo "oask error: no API key (checked $KEY_FILE and ~/Projects/.env OPENROUTER_API_KEY)" >&2
  exit 2
fi

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --file)
      DECLARE_FILES+=("$2")
      shift 2
      ;;
    --glob)
      DECLARE_GLOBS+=("$2")
      shift 2
      ;;
    --list)
      # List free models
      curl -sS -m 30 https://openrouter.ai/api/v1/models | python3 -c '
import sys, json
d = json.load(sys.stdin)
free = [m for m in d["data"]
        if float(m.get("pricing", {}).get("prompt", 1) or 0) == 0
        and float(m.get("pricing", {}).get("completion", 1) or 0) == 0]
for m in sorted(free, key=lambda x: -(x.get("context_length") or 0)):
    print("%-55s ctx=%s" % (m["id"], m.get("context_length")))
'
      exit 0
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

# Check spend guard BEFORE any API call
check_spend_guard

# Expand --glob patterns
RESOLVED_FILES=("${DECLARE_FILES[@]:-}")
for pattern in "${DECLARE_GLOBS[@]:-}"; do
  while IFS= read -r match; do
    RESOLVED_FILES+=("$match")
  done < <(compgen -G "$pattern" || true)
done

# Build request body with python3
export PROMPT
export MODEL
export RESOLVED_FILES_JSON

RESOLVED_FILES_JSON=$(python3 -c "
import json
import sys

files = []
for fpath in sys.argv[1:]:
    if not fpath:  # Skip empty paths
        continue
    try:
        with open(fpath, 'r') as f:
            content = f.read()
            files.append({'type': 'file', 'path': fpath, 'content': content})
    except Exception as e:
        sys.stderr.write(f'warning: could not read {fpath}: {e}\n')

print(json.dumps(files))
" "${RESOLVED_FILES[@]:-}")

# Build API request body
BODY=$(python3 << 'PYTHON'
import json
import os
import sys

prompt_text = os.environ["PROMPT"]
files_json = os.environ["RESOLVED_FILES_JSON"]

try:
    files = json.loads(files_json)
except:
    files = []

# Combine file contents with prompt text
if files:
    file_lines = []
    for f in files:
        file_lines.append(f"[{f.get('path', 'unknown')}]\n{f.get('content', '')}")
    file_context = "\n\n---\nAttached files:\n" + "\n".join(file_lines)
    content = prompt_text + file_context
else:
    content = prompt_text

body = {
    "model": os.environ["MODEL"],
    "messages": [
        {"role": "user", "content": content}
    ]
}

print(json.dumps(body))
PYTHON
)

# Make request
HTTP_CODE=$(curl -sS -w "%{http_code}" -o /tmp/oask_response.json \
  -m "$OASK_TIMEOUT" \
  --connect-timeout "$OASK_CONNECT_TIMEOUT" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPEN_ROUTER_API_KEY" \
  -H "X-Title: codex-bridge" \
  -X POST https://openrouter.ai/api/v1/chat/completions \
  -d "$BODY")

RESPONSE=$(cat /tmp/oask_response.json)
rm -f /tmp/oask_response.json

# Check HTTP status
if [[ "$HTTP_CODE" != "200" ]]; then
  ERROR_TEXT=$(echo "$RESPONSE" | head -c 300)
  if echo "$RESPONSE" | jq -e '.error.message' >/dev/null 2>&1; then
    MESSAGE=$(echo "$RESPONSE" | jq -r '.error.message')
    echo "oask error $HTTP_CODE: $MESSAGE" >&2
  else
    echo "oask error $HTTP_CODE: $ERROR_TEXT" >&2
  fi
  exit 1
fi

# Check for API error in 200 response
if echo "$RESPONSE" | jq -e '.error' >/dev/null 2>&1; then
  MESSAGE=$(echo "$RESPONSE" | jq -r '.error.message // .error // "unknown error"')
  echo "oask error: $MESSAGE" >&2
  exit 1
fi

# Check for empty/blocked completion
if ! echo "$RESPONSE" | jq -e '.choices[0]' >/dev/null 2>&1; then
  FINISH_REASON=$(echo "$RESPONSE" | jq -r '.choices[0].finish_reason // "UNKNOWN"' 2>/dev/null || echo "UNKNOWN")
  echo "oask returned no content (finish_reason: $FINISH_REASON)" >&2
  exit 1
fi

# Extract response text
RESP_TEXT=$(echo "$RESPONSE" | jq -r '.choices[0].message.content // ""' 2>/dev/null)

if [[ -z "$RESP_TEXT" ]]; then
  echo "oask returned no content" >&2
  exit 1
fi

# Extract usage (OpenAI-compatible format)
PROMPT_TOKENS=$(echo "$RESPONSE" | jq -r '.usage.prompt_tokens // 0' 2>/dev/null)
OUTPUT_TOKENS=$(echo "$RESPONSE" | jq -r '.usage.completion_tokens // 0' 2>/dev/null)

# Output response
if [[ "$RAW" == true ]]; then
  echo "$RESPONSE"
else
  echo "$RESP_TEXT"
  echo "[openrouter $MODEL | in $PROMPT_TOKENS out $OUTPUT_TOKENS]" >&2
fi

# Log to both JSONL and SQLite
python3 << PYTHON_LOG
import json
import os
import uuid
import sqlite3
from datetime import datetime, timezone

log_file = "$USAGE_LOG"
db_path = os.path.expanduser("~/.codex-bridge/usage.db")

# JSONL log (append-only)
try:
    os.makedirs(os.path.dirname(log_file) if os.path.dirname(log_file) else '.', exist_ok=True)
    if not os.path.exists(log_file):
        open(log_file, 'a').close()
        os.chmod(log_file, 0o600)

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "backend": "openrouter",
        "model": "$MODEL",
        "input_tokens": $PROMPT_TOKENS,
        "output_tokens": $OUTPUT_TOKENS
    }

    with open(log_file, 'a') as f:
        f.write(json.dumps(record) + '\n')
except Exception:
    pass

# SQLite log (fail silently)
try:
    uid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    day = now[:10]
    model = "$MODEL"

    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute(
        "INSERT INTO usage (uid, ts, day, backend, model, input_tokens, output_tokens, cache_read, cache_write, reasoning) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (uid, now, day, "openrouter", model, int($PROMPT_TOKENS), int($OUTPUT_TOKENS), 0, 0, 0)
    )
    conn.commit()
    conn.close()
except Exception:
    pass
PYTHON_LOG
