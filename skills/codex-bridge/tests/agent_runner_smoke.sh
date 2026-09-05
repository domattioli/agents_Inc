#!/usr/bin/env bash
set -euo pipefail

readonly SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly AGENT="${SKILL_DIR}/scripts/agent.sh"
TEST_ROOT=$(mktemp -d)
readonly TEST_ROOT
trap 'rm -rf "$TEST_ROOT"' EXIT

failures=0
pass() { printf 'PASS: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1"; failures=$((failures + 1)); }

mkdir -p "$TEST_ROOT/scripts" "$TEST_ROOT/state"

make_wrapper() {
  local name="$1" body="$2"
  printf '#!/usr/bin/env bash\nset -euo pipefail\n%s\n' "$body" > "$TEST_ROOT/scripts/$name"
  chmod +x "$TEST_ROOT/scripts/$name"
}

make_wrapper ask.sh 'printf "codex:%s\\n" "${*: -1}"'
make_wrapper gask.sh 'printf "gemini:%s\\n" "${*: -1}"'
make_wrapper mask.sh 'printf "mistral:%s\\n" "${*: -1}"'
make_wrapper route.sh 'case "$1" in
  pick) printf "gemini-flash\\n" ;;
  classify) printf "transient\\n" ;;
  report) exit 0 ;;
  *) exit 2 ;;
esac'

agent() {
  CODEX_BRIDGE_SCRIPTS_DIR="$TEST_ROOT/scripts" CODEX_BRIDGE_AGENT_STATE_DIR="$TEST_ROOT/state" "$AGENT" "$@"
}

id=$(agent submit --backend gemini --wait "one" | sed -n 's/^id: //p')
if [[ -n "$id" ]] && [[ "$(agent result "$id")" == "gemini:one" ]] && [[ "$(agent status "$id" --json)" == *'"status": "returned"'* ]]; then
  pass "submits, stores, and reports a Gemini job"
else
  fail "Gemini job lifecycle or result is wrong"
fi

if [[ "$(agent result "$id" --json)" == *'"schema": "codex-bridge-agent-result-v1"'* ]] && [[ "$(agent result "$id" --json)" == *'"backend": "gemini-flash"'* ]]; then
  pass "writes a provider-neutral terminal result artifact"
else
  fail "result artifact is missing or malformed"
fi

auto_id=$(agent submit --class review --wait "route-me" | sed -n 's/^id: //p')
if [[ -n "$auto_id" ]] && [[ "$(agent status "$auto_id" --json)" == *'"backend": "gemini-flash"'* ]]; then
  pass "auto dispatch selects route backend"
else
  fail "auto dispatch did not select route backend"
fi

retry_counter="$TEST_ROOT/retry-count"
printf '0\n' > "$retry_counter"
make_wrapper gask.sh 'if [[ "${*: -1}" == "retry" ]]; then
  count=$(<"$RETRY_COUNTER")
  count=$((count + 1))
  printf "%s\\n" "$count" > "$RETRY_COUNTER"
  if [[ "$count" -eq 1 ]]; then
    printf "temporary timeout\\n" >&2
    exit 1
  fi
fi
printf "gemini:%s\\n" "${*: -1}"'
retry_id=$(RETRY_COUNTER="$retry_counter" agent submit --backend gemini --retries 1 --wait "retry" | sed -n 's/^id: //p')
if [[ "$(<"$retry_counter")" == "2" ]] && [[ "$(agent status "$retry_id" --json)" == *'"attempt": 2'* ]] && [[ "$(agent result "$retry_id")" == "gemini:retry" ]]; then
  pass "retries transient provider failures"
else
  fail "transient retry did not complete correctly"
fi

mistral_id=$(agent submit --backend mistral --agent --wait "first" | sed -n 's/^id: //p')
follow_id=$(agent follow-up "$mistral_id" --wait "second" | sed -n 's/^id: //p')
if [[ "$(agent result "$follow_id")" == "mistral:second" ]] && [[ "$(agent status "$follow_id" --json)" == *"\"parent_id\": \"$mistral_id\""* ]]; then
  pass "continues persistent Mistral jobs"
else
  fail "Mistral follow-up is wrong"
fi

set +e
CODEX_BRIDGE_MODE=ultra CODEX_BRIDGE_SCRIPTS_DIR="$TEST_ROOT/scripts" CODEX_BRIDGE_AGENT_STATE_DIR="$TEST_ROOT/state" "$AGENT" submit --backend haiku "never" >"$TEST_ROOT/ultra.out" 2>"$TEST_ROOT/ultra.err"
ultra_status=$?
set -e
if [[ "$ultra_status" -eq 5 ]] && grep -q 'refuses Anthropic backend' "$TEST_ROOT/ultra.err"; then
  pass "ultra rejects Anthropic backend names"
else
  fail "ultra accepted Anthropic backend"
fi

set +e
agent follow-up "$id" "cannot" >"$TEST_ROOT/follow.out" 2>"$TEST_ROOT/follow.err"
follow_status=$?
set -e
if [[ "$follow_status" -eq 2 ]] && grep -q 'follow-up is supported only' "$TEST_ROOT/follow.err"; then
  pass "rejects stateless Gemini follow-ups"
else
  fail "accepted a Gemini follow-up"
fi

exit "$failures"
