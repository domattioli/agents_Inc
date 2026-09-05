#!/usr/bin/env bash
set -euo pipefail

readonly ROUTE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/route.sh"
readonly ANTHROPIC_BACKENDS="$(sed -n 's/^readonly ANTHROPIC_BACKENDS="\([^"]*\)"/\1/p' "$ROUTE")"
TEST_HOME=$(mktemp -d)
readonly TEST_HOME
trap 'rm -rf "$TEST_HOME"' EXIT

failures=0

pass() {
    printf 'PASS: %s\n' "$1"
}

fail() {
    printf 'FAIL: %s\n' "$1"
    failures=$((failures + 1))
}

is_anthropic() {
    local backend
    for backend in $ANTHROPIC_BACKENDS; do
        [[ "$1" == "$backend" ]] && return 0
    done
    return 1
}

assert_pick() {
    local mode="$1" task_class="$2" expected="$3" output status
    set +e
    output=$(HOME="$TEST_HOME" CODEX_BRIDGE_MODE="$mode" "$ROUTE" pick "$task_class" 2>/dev/null)
    status=$?
    set -e
    if [[ "$status" -eq 0 && "$output" == "$expected" ]]; then
        pass "$mode pick $task_class -> $expected"
    else
        fail "$mode pick $task_class expected '$expected' (status $status, output '$output')"
    fi
}

for task_class in digest triage logs survey debug review code transform plan; do
    set +e
    output=$(HOME="$TEST_HOME" CODEX_BRIDGE_MODE=ultra "$ROUTE" pick "$task_class" 2>/dev/null)
    status=$?
    set -e
    if [[ "$status" -eq 0 && "$output" =~ ^(gemini-flash|gemini-flash-lite|codex|mistral|ask)$ ]] && ! is_anthropic "$output"; then
        pass "ultra pick $task_class avoids Anthropic backends"
    else
        fail "ultra pick $task_class returned '$output' with status $status"
    fi
done

set +e
orchestrate_stdout=$(HOME="$TEST_HOME" CODEX_BRIDGE_MODE=ultra "$ROUTE" pick orchestrate 2>"$TEST_HOME/orchestrate.err")
orchestrate_status=$?
set -e
if [[ "$orchestrate_status" -eq 4 && -z "$orchestrate_stdout" ]] && grep -q 'orchestration cannot be delegated in ultra mode' "$TEST_HOME/orchestrate.err"; then
    pass "ultra orchestrate exits 4 with stderr only"
else
    fail "ultra orchestrate expected status 4 and empty stdout"
fi

classes=(digest triage logs survey debug review code transform plan orchestrate)
standard=(gemini-flash gemini-flash-lite gemini-flash-lite codex codex codex haiku gemini-flash-lite sonnet fable)
budget=(gemini-flash gemini-flash-lite gemini-flash-lite codex codex codex haiku gemini-flash-lite sonnet sonnet)
for i in "${!classes[@]}"; do
    assert_pick standard "${classes[$i]}" "${standard[$i]}"
    assert_pick budget "${classes[$i]}" "${budget[$i]}"
done

set +e
invalid_stdout=$(HOME="$TEST_HOME" CODEX_BRIDGE_MODE=invalid "$ROUTE" pick digest 2>"$TEST_HOME/invalid.err")
invalid_status=$?
set -e
if [[ "$invalid_status" -eq 2 && -z "$invalid_stdout" ]] && grep -q 'standard, budget, ultra' "$TEST_HOME/invalid.err"; then
    pass "invalid mode exits 2"
else
    fail "invalid mode expected status 2 and accepted-value error"
fi

mkdir -p "$TEST_HOME/.codex-bridge"
printf '%s\n' '{
  "gemini-flash": {"status": "exhausted", "cooldown_until": "2999-01-01T00:00:00+00:00"},
  "gemini-flash-lite": {"status": "exhausted", "cooldown_until": "2999-01-01T00:00:00+00:00"},
  "codex": {"status": "exhausted", "cooldown_until": "2999-01-01T00:00:00+00:00"},
  "mistral": {"status": "exhausted", "cooldown_until": "2999-01-01T00:00:00+00:00"},
  "haiku": {"status": "ok", "cooldown_until": null},
  "sonnet": {"status": "ok", "cooldown_until": null},
  "opus": {"status": "ok", "cooldown_until": null},
  "fable": {"status": "ok", "cooldown_until": null}
}' > "$TEST_HOME/.codex-bridge/backend-health.json"

set +e
exhausted_stdout=$(HOME="$TEST_HOME" CODEX_BRIDGE_MODE=ultra "$ROUTE" pick digest 2>"$TEST_HOME/exhausted.err")
exhausted_status=$?
set -e
if [[ "$exhausted_status" -eq 3 && "$exhausted_stdout" == "NONE" ]] && ! is_anthropic "$exhausted_stdout"; then
    pass "ultra exhaustion prints NONE and exits 3 without Anthropic fallback"
else
    fail "ultra exhaustion expected NONE/status 3 (status $exhausted_status, output '$exhausted_stdout')"
fi

exit "$failures"
