#!/usr/bin/env bash
# Smoke test for argument validation in gask.sh, oask.sh, mask.sh.
# Tests that unknown flags and multiple prompts are rejected before any network call.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GASK_SCRIPT="$HERE/../scripts/gask.sh"
OASK_SCRIPT="$HERE/../scripts/oask.sh"
MASK_SCRIPT="$HERE/../scripts/mask.sh"

TMP="$(mktemp -d -t ask_args_smoke.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

pass=0
total=9

ok()   { echo "PASS $1"; pass=$((pass + 1)); }
fail() { echo "FAIL $1: $2"; }

# Create a fake curl stub that exits 99 and touches a marker file.
# If any script reaches curl, the marker will exist.
mkdir -p "$TMP/stubs"
cat > "$TMP/stubs/curl" <<'CURL_STUB'
#!/bin/sh
touch "$CURL_MARKER_FILE"
exit 99
CURL_STUB
chmod +x "$TMP/stubs/curl"

# Set up temporary HOME with dummy keys.
export HOME="$TMP/home"
mkdir -p "$HOME/.codex-bridge"
echo "dummy-gemini-key-123456789-dummy" > "$HOME/.codex-bridge/gemini-key"
echo "dummy-openrouter-key-123456789-dummy" > "$HOME/.codex-bridge/openrouter-key"
mkdir -p "$HOME/.config/devstral"
echo "dummy-mistral-key-123456789-dummy" > "$HOME/.config/devstral/api_key"

# Set API keys as env vars (override file checks)
export GEMINI_API_KEY="dummy-gemini-key-123456789-dummy"
export OPENROUTER_API_KEY="dummy-openrouter-key-123456789-dummy"
export MISTRAL_API_KEY="dummy-mistral-key-123456789-dummy"

# Set dummy MODEL for oask.sh to skip the python3 pick-default call
export MODEL="mistral-7b:free"

# Unset governance mode
unset WORKERBEES_GOVERNANCE

# Set PATH to use our curl stub
export PATH="$TMP/stubs:$PATH"

# Test gask.sh: two positional arguments should be rejected
export CURL_MARKER_FILE="$TMP/gask_curl_marker"
err_output=$("$GASK_SCRIPT" "one" "two" 2>&1 >/dev/null); rc=$?
if [[ $rc -eq 2 && "$err_output" == *"more than one prompt argument"* && ! -f "$CURL_MARKER_FILE" ]]; then
  ok "gask two positionals rejected"
else
  fail "gask two positionals" "rc=$rc, curl_called=$([[ -f "$CURL_MARKER_FILE" ]] && echo 'yes' || echo 'no')"
fi

# Test gask.sh: unknown flag should be rejected
export CURL_MARKER_FILE="$TMP/gask_flag_marker"
err_output=$("$GASK_SCRIPT" --bogus "prompt" 2>&1 >/dev/null); rc=$?
if [[ $rc -eq 2 && "$err_output" == *"unknown flag: --bogus"* && ! -f "$CURL_MARKER_FILE" ]]; then
  ok "gask unknown flag rejected"
else
  fail "gask unknown flag" "rc=$rc, curl_called=$([[ -f "$CURL_MARKER_FILE" ]] && echo 'yes' || echo 'no')"
fi

# Test gask.sh: zsh unquoted expansion case
export CURL_MARKER_FILE="$TMP/gask_zsh_marker"
err_output=$("$GASK_SCRIPT" "--file a --file b" "prompt" 2>&1 >/dev/null); rc=$?
if [[ $rc -eq 2 && "$err_output" == *"unknown flag"* && ! -f "$CURL_MARKER_FILE" ]]; then
  ok "gask zsh expansion case"
else
  fail "gask zsh expansion" "rc=$rc, curl_called=$([[ -f "$CURL_MARKER_FILE" ]] && echo 'yes' || echo 'no')"
fi

# Test oask.sh: two positional arguments should be rejected
export CURL_MARKER_FILE="$TMP/oask_curl_marker"
err_output=$("$OASK_SCRIPT" "one" "two" 2>&1 >/dev/null); rc=$?
if [[ $rc -eq 2 && "$err_output" == *"more than one prompt argument"* && ! -f "$CURL_MARKER_FILE" ]]; then
  ok "oask two positionals rejected"
else
  fail "oask two positionals" "rc=$rc, curl_called=$([[ -f "$CURL_MARKER_FILE" ]] && echo 'yes' || echo 'no')"
fi

# Test oask.sh: unknown flag should be rejected
export CURL_MARKER_FILE="$TMP/oask_flag_marker"
err_output=$("$OASK_SCRIPT" --bogus "prompt" 2>&1 >/dev/null); rc=$?
if [[ $rc -eq 2 && "$err_output" == *"unknown flag: --bogus"* && ! -f "$CURL_MARKER_FILE" ]]; then
  ok "oask unknown flag rejected"
else
  fail "oask unknown flag" "rc=$rc, curl_called=$([[ -f "$CURL_MARKER_FILE" ]] && echo 'yes' || echo 'no')"
fi

# Test oask.sh: zsh unquoted expansion case
export CURL_MARKER_FILE="$TMP/oask_zsh_marker"
err_output=$("$OASK_SCRIPT" "--file a --file b" "prompt" 2>&1 >/dev/null); rc=$?
if [[ $rc -eq 2 && "$err_output" == *"unknown flag"* && ! -f "$CURL_MARKER_FILE" ]]; then
  ok "oask zsh expansion case"
else
  fail "oask zsh expansion" "rc=$rc, curl_called=$([[ -f "$CURL_MARKER_FILE" ]] && echo 'yes' || echo 'no')"
fi

# Test mask.sh: two positional arguments should be rejected
export CURL_MARKER_FILE="$TMP/mask_curl_marker"
err_output=$("$MASK_SCRIPT" "one" "two" 2>&1 >/dev/null); rc=$?
if [[ $rc -eq 2 && "$err_output" == *"more than one prompt argument"* && ! -f "$CURL_MARKER_FILE" ]]; then
  ok "mask two positionals rejected"
else
  fail "mask two positionals" "rc=$rc, curl_called=$([[ -f "$CURL_MARKER_FILE" ]] && echo 'yes' || echo 'no')"
fi

# Test mask.sh: unknown flag should be rejected
export CURL_MARKER_FILE="$TMP/mask_flag_marker"
err_output=$("$MASK_SCRIPT" --bogus "prompt" 2>&1 >/dev/null); rc=$?
if [[ $rc -eq 2 && "$err_output" == *"unknown flag: --bogus"* && ! -f "$CURL_MARKER_FILE" ]]; then
  ok "mask unknown flag rejected"
else
  fail "mask unknown flag" "rc=$rc, curl_called=$([[ -f "$CURL_MARKER_FILE" ]] && echo 'yes' || echo 'no')"
fi

# Test mask.sh: zsh unquoted expansion case
export CURL_MARKER_FILE="$TMP/mask_zsh_marker"
err_output=$("$MASK_SCRIPT" "--file a --file b" "prompt" 2>&1 >/dev/null); rc=$?
if [[ $rc -eq 2 && "$err_output" == *"unknown flag"* && ! -f "$CURL_MARKER_FILE" ]]; then
  ok "mask zsh expansion case"
else
  fail "mask zsh expansion" "rc=$rc, curl_called=$([[ -f "$CURL_MARKER_FILE" ]] && echo 'yes' || echo 'no')"
fi

echo "$pass/$total PASS"
[[ $pass -eq $total ]]
