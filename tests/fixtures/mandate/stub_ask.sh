#!/usr/bin/env bash
# Test fixture for tests/test_mandate_session.py (spec-010, task T001).
#
# Stands in for skills/codex-bridge/scripts/ask.sh so mandate-path tests can drive
# a real `agent.sh submit --mandate` without a live bridge or provider call.
# Point CODEX_BRIDGE_SCRIPTS_DIR at this file's directory to use it.
#
# Behaviour:
#   - Parses the same flags ask.sh understands: --model, --thread, --fresh, --raw, --reset.
#   - --thread and --fresh together -> exit 2 (mirrors ask.sh's own guard, C4).
#   - If CODEX_BRIDGE_STUB_CAPTURE is set, appends one JSON line per invocation recording
#     the argv this call was handed (model/thread/fresh/reset/prompt) -- this is what
#     T045's SC-001 byte-identity assertion reads.
#   - If CODEX_BRIDGE_STUB_RESUME_FAIL=true and --thread was given, simulates the bridge's
#     409 "resume failed" response (ask.sh's own stderr shape) and exits 1.
#   - Otherwise echoes canned JSON: {"response":..., "thread_id":..., "usage":..., "session_restarted": false}.
#     thread_id echoes --thread when given, else CODEX_BRIDGE_STUB_THREAD_ID, else a fresh
#     per-invocation id -- so two `--fresh` calls in the same test never collide.

set -euo pipefail

MODEL=""
THREAD=""
FRESH=false
RAW=false
RESET=false
PROMPT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)
      MODEL="$2"
      shift 2
      ;;
    --thread)
      THREAD="$2"
      shift 2
      ;;
    --fresh)
      FRESH=true
      shift
      ;;
    --raw)
      RAW=true
      shift
      ;;
    --reset)
      RESET=true
      shift
      ;;
    *)
      PROMPT="$1"
      shift
      ;;
  esac
done

if [[ -n "$THREAD" && "$FRESH" == true ]]; then
  echo "error: --thread and --fresh are mutually exclusive" >&2
  exit 2
fi

if [[ -z "$PROMPT" ]]; then
  PROMPT=$(cat)
fi

if [[ -n "${CODEX_BRIDGE_STUB_CAPTURE:-}" ]]; then
  MODEL="$MODEL" THREAD="$THREAD" FRESH="$FRESH" RESET="$RESET" PROMPT="$PROMPT" python3 - <<'PYEOF' >> "$CODEX_BRIDGE_STUB_CAPTURE"
import json
import os

print(json.dumps({
    "model": os.environ.get("MODEL", ""),
    "thread": os.environ.get("THREAD", ""),
    "fresh": os.environ.get("FRESH") == "true",
    "reset": os.environ.get("RESET") == "true",
    "prompt": os.environ.get("PROMPT", ""),
}))
PYEOF
fi

if [[ "${CODEX_BRIDGE_STUB_RESUME_FAIL:-}" == "true" && -n "$THREAD" ]]; then
  echo "bridge error 409: resume failed" >&2
  exit 1
fi

STUB_THREAD_ID="${CODEX_BRIDGE_STUB_THREAD_ID:-}"
if [[ -n "$THREAD" ]]; then
  STUB_THREAD_ID="$THREAD"
elif [[ -z "$STUB_THREAD_ID" ]]; then
  STUB_THREAD_ID="stub-thread-$$-$RANDOM"
fi

RESULT_JSON=$(python3 - "$STUB_THREAD_ID" "$PROMPT" <<'PYEOF'
import json
import sys

thread_id, prompt = sys.argv[1], sys.argv[2]
print(json.dumps({
    "response": f"stub response to: {prompt}",
    "thread_id": thread_id,
    "usage": {"input_tokens": 1, "output_tokens": 1},
    "session_restarted": False,
}))
PYEOF
)

if [[ "$RAW" == true ]]; then
  echo "$RESULT_JSON"
else
  echo "$RESULT_JSON" | jq -r '.response'
  echo "[thread $STUB_THREAD_ID]" >&2
fi
