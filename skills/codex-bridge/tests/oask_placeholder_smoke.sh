#!/bin/bash
# Smoke test for redaction placeholder detection in oask.sh.
# Tests that oask.sh detects placeholders in reply not in request and exits with code 4.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OASK_SCRIPT="$HERE/../scripts/oask.sh"

TMP="$(mktemp -d -t oask_placeholder_smoke.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

pass=0
total=6

ok()   { echo "PASS $1"; pass=$((pass + 1)); }
fail() { echo "FAIL $1: $2"; }

# Create a curl stub that writes a canned OpenRouter JSON response.
# It extracts the -o flag argument and writes the response there.
mkdir -p "$TMP/stubs"
cat > "$TMP/stubs/curl" <<'CURL_STUB'
#!/bin/bash
# Parse -o argument to find output file
OUTPUT_FILE=""
for arg in "$@"; do
  if [[ "$prev_arg" == "-o" ]]; then
    OUTPUT_FILE="$arg"
  fi
  prev_arg="$arg"
done

if [[ -n "$OUTPUT_FILE" ]]; then
  # Write canned OpenRouter response with CURL_REPLY_TEXT from environment
  mkdir -p "$(dirname "$OUTPUT_FILE")"
  printf '{"choices":[{"message":{"content":"%s"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1}}\n' "$CURL_REPLY_TEXT" > "$OUTPUT_FILE"
fi

# Print HTTP status code
echo "200"
CURL_STUB
chmod +x "$TMP/stubs/curl"

# Set up temporary HOME with dummy key
export HOME="$TMP/home"
mkdir -p "$HOME/.codex-bridge"
echo "dummy-openrouter-key-123456789-dummy" > "$HOME/.codex-bridge/openrouter-key"

# Set API key as env var (override file checks)
export OPENROUTER_API_KEY="dummy-openrouter-key-123456789-dummy"

# Set dummy MODEL for oask.sh to skip the python3 pick-default call
export MODEL="mistral-7b:free"

# Unset governance mode
unset WORKERBEES_GOVERNANCE

# Set PATH to use our curl stub
export PATH="$TMP/stubs:$PATH"

# Test a: reply with [PERSON_NAME] not in prompt, should exit 4
export CURL_REPLY_TEXT="rename [PERSON_NAME] to x"
out=$("$OASK_SCRIPT" "review self.inside_link" 2>&1); rc=$?
if [[ $rc -eq 4 && "$out" == *"rename [PERSON_NAME] to x"* && "$out" == *"unfit for code review"* && "$out" == *"[PERSON_NAME]"* ]]; then
  ok "placeholder [PERSON_NAME] not in prompt"
else
  fail "placeholder [PERSON_NAME]" "rc=$rc, stdout/stderr check failed"
fi

# Test b: reply with [EMAIL_ADDRESS] not in prompt, should exit 4
export CURL_REPLY_TEXT="contact [EMAIL_ADDRESS]"
out=$("$OASK_SCRIPT" "hi" 2>&1); rc=$?
if [[ $rc -eq 4 ]]; then
  ok "placeholder [EMAIL_ADDRESS] not in prompt"
else
  fail "placeholder [EMAIL_ADDRESS]" "rc=$rc"
fi

# Test c: reply with [PERSON_NAME] but it IS in prompt, should exit 0
export CURL_REPLY_TEXT="keep [PERSON_NAME] as is"
out=$("$OASK_SCRIPT" "what does [PERSON_NAME] mean" 2>&1); rc=$?
if [[ $rc -eq 0 && "$out" != *"unfit for code review"* ]]; then
  ok "placeholder [PERSON_NAME] in prompt, no unfit"
else
  fail "placeholder [PERSON_NAME] in prompt" "rc=$rc, unfit should be absent"
fi

# Test d: reply with [HIGH] [OK] which are not placeholders, should exit 0
export CURL_REPLY_TEXT="looks fine [HIGH] [OK]"
out=$("$OASK_SCRIPT" "review" 2>&1); rc=$?
if [[ $rc -eq 0 && "$out" != *"unfit for code review"* ]]; then
  ok "non-placeholder [HIGH] [OK] no exit 4"
else
  fail "non-placeholder brackets" "rc=$rc, should be 0"
fi

# Test e: clean reply with no placeholders, should exit 0
export CURL_REPLY_TEXT="all good"
out=$("$OASK_SCRIPT" "review" 2>&1); rc=$?
if [[ $rc -eq 0 && "$out" == *"all good"* ]]; then
  ok "clean reply no placeholders"
else
  fail "clean reply" "rc=$rc, stdout check failed"
fi

# Test f: RAW mode with placeholder should exit 4 and warn on stderr
export CURL_REPLY_TEXT="rename [PERSON_NAME]"
out=$("$OASK_SCRIPT" --raw "review" 2>&1); rc=$?
if [[ $rc -eq 4 && "$out" == *"unfit for code review"* ]]; then
  ok "RAW mode with placeholder exits 4"
else
  fail "RAW mode placeholder" "rc=$rc, unfit check failed"
fi

echo "$pass/$total PASS"
[[ $pass -eq $total ]]
