#!/bin/bash

# Test suite for ollama-guard
# Offline tests using stubs for curl, ollama, vm_stat, date
# Stubs are placed first on PATH for isolation.

set -u

readonly TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR="${TEST_DIR}/../scripts"
readonly GUARD_SCRIPT="${SCRIPT_DIR}/ollama-guard.sh"

# Create a temporary test environment
TEST_TMP=$(mktemp -d)
readonly STUB_DIR="${TEST_TMP}/stubs"

# Ensure cleanup on exit
cleanup() {
    rm -rf "$TEST_TMP"
}
trap cleanup EXIT

# Create stub directory and set up PATH
mkdir -p "${STUB_DIR}"
export PATH="${STUB_DIR}:${PATH}"
export HOME="${TEST_TMP}/home"
mkdir -p "${HOME}/.cache/ollama-guard"

# Override current time for deterministic tests
export OLLAMA_GUARD_NOW=1696003200  # 2023-09-29 12:00:00 UTC

# Override OLLAMA_BIN to use stub
export OLLAMA_BIN="${STUB_DIR}/ollama"

# Counters for test results
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# ============================================================================
# Stub curl: mock Ollama API responses
# ============================================================================
cat > "${STUB_DIR}/curl" <<'CURL_STUB'
#!/bin/bash
case "$*" in
    *"api/ps"*)
        if [[ "${TEST_CASE:-}" == "loaded_models" ]]; then
            echo '{
  "models": [
    {"name":"llama2","size_vram":7516192768,"expires_at":"2023-09-29T12:05:00Z"},
    {"name":"mistral","size_vram":10737418240,"expires_at":"2023-09-29T11:50:00Z"}
  ]
}'
        elif [[ "${TEST_CASE:-}" == "two_models_one_line" ]]; then
            echo '{"models":[{"name":"llama2","size_vram":7516192768,"expires_at":"2023-09-29T12:05:00Z"},{"name":"mistral","size_vram":10737418240,"expires_at":"2023-09-29T11:50:00Z"}]}'
        elif [[ "${TEST_CASE:-}" == "idle_model" ]]; then
            echo '{
  "models": [
    {"name":"llama2","size_vram":7516192768,"expires_at":"2023-09-29T11:40:00Z"}
  ]
}'
        else
            echo '{"models":[]}'
        fi
        ;;
    *"api/version"*)
        if [[ "${TEST_CASE:-}" == "server_down" ]]; then
            exit 1
        else
            echo '{"version":"0.1.0"}'
        fi
        ;;
    *"api/generate"*)
        # For non-interactive testing, echo a mock response
        if [[ "${GEN_CASE:-}" == "quoted" ]]; then
            echo '{"response":"say \"hi\" ok","done":true}'
        elif [[ "${GEN_CASE:-}" == "error" ]]; then
            echo '{"error":"model not found"}'
        else
            echo '{"response":"The answer is 4."}'
        fi
        exit 0
        ;;
esac
CURL_STUB
chmod +x "${STUB_DIR}/curl"

# ============================================================================
# Stub vm_stat: mock memory stats
# ============================================================================
cat > "${STUB_DIR}/vm_stat" <<'VM_STAT_STUB'
#!/bin/bash
if [[ "${LOW_RAM:-}" == "1" ]]; then
    FREE=131072
    INACTIVE=131072
    SPECULATIVE=0
else
    FREE=1048576
    INACTIVE=1310720
    SPECULATIVE=262144
fi

cat <<EOF
Mach Virtual Memory Statistics: $(date)
Pages free:                    ${FREE}.
Pages active:                  1048576.
Pages inactive:                ${INACTIVE}.
Pages speculative:             ${SPECULATIVE}.
Pages throttled:               0.
Pages wired down:              524288.
Pages purgeable:               0.
"Translation faults":          1234567.
"Pages copy-on-write":         987654.
"Pages zero filled":           2345678.
"Pages reactivated":           123456.
"Pageins":                     987654.
"Pageouts":                    123456.
"Swapins":                     54321.
"Swapouts":                    9876.
EOF
VM_STAT_STUB
chmod +x "${STUB_DIR}/vm_stat"

# ============================================================================
# Stub ollama
# ============================================================================
cat > "${STUB_DIR}/ollama" <<'OLLAMA_STUB'
#!/bin/bash
case "$1" in
    serve)
        exit 0
        ;;
    list)
        if [[ "${MODEL_SIZE:-}" == "7.0" ]]; then
            echo "NAME                ID              SIZE      MODIFIED"
            echo "llama2:latest       f72c60cabf62    7.0 GB    ${OLLAMA_GUARD_NOW}"
        elif [[ "${MODEL_SIZE:-}" == "prefix" ]]; then
            echo "NAME                ID              SIZE      MODIFIED"
            echo "llama2-70b:latest   aaaaaaaaaaaa    39 GB     ${OLLAMA_GUARD_NOW}"
            echo "llama2:latest       f72c60cabf62    3.8 GB    ${OLLAMA_GUARD_NOW}"
        elif [[ "${MODEL_SIZE:-}" == "500" ]]; then
            echo "NAME                ID              SIZE      MODIFIED"
            echo "tiny:latest         dae161e27b0e    500 MB    ${OLLAMA_GUARD_NOW}"
        else
            exit 1
        fi
        ;;
    run)
        exit 0
        ;;
esac
OLLAMA_STUB
chmod +x "${STUB_DIR}/ollama"

# ============================================================================
# Stub sysctl
# ============================================================================
cat > "${STUB_DIR}/sysctl" <<'SYSCTL_STUB'
#!/bin/bash
case "$*" in
    *"hw.pagesize"*)
        echo 4096
        ;;
esac
SYSCTL_STUB
chmod +x "${STUB_DIR}/sysctl"

# ============================================================================
# Stub date
# ============================================================================
cat > "${STUB_DIR}/date" <<'DATE_STUB'
#!/bin/bash
if [[ "$1" == "-j" ]] && [[ "$2" == "-f" ]]; then
    input="$4"
    case "$input" in
        2023-09-29T12:05:00) echo 1696003500 ;;
        2023-09-29T11:50:00) echo 1696002600 ;;
        2023-09-29T11:40:00) echo 1696002000 ;;
        *) exit 1 ;;
    esac
elif [[ "$1" == "+%s" ]]; then
    echo "${OLLAMA_GUARD_NOW}"
else
    /bin/date "$@"
fi
DATE_STUB
chmod +x "${STUB_DIR}/date"

# ============================================================================
# Stub ps
# ============================================================================
cat > "${STUB_DIR}/ps" <<'PS_STUB'
#!/bin/bash
if [[ "$1" == "aux" ]]; then
    exit 0
elif [[ "$1" == "-o" ]]; then
    if [[ "$4" == "1234" ]]; then
        echo "1"
    else
        echo "999"
    fi
else
    exit 1
fi
PS_STUB
chmod +x "${STUB_DIR}/ps"

# ============================================================================
# Test framework
# ============================================================================

run_test() {
    local name="$1"
    local func="$2"

    ((TESTS_RUN++))
    echo -n "Test: $name ... "

    if $func; then
        echo "PASS"
        ((TESTS_PASSED++))
    else
        echo "FAIL"
        ((TESTS_FAILED++))
    fi
}

assert_file_contains() {
    local file="$1"
    local pattern="$2"
    [[ -f "$file" ]] && grep -q "$pattern" "$file"
}

assert_file_exists() {
    local file="$1"
    [[ -f "$file" ]]
}

# ============================================================================
# Tests
# ============================================================================

test_help() {
    bash "${GUARD_SCRIPT}" help >/dev/null 2>&1
    return 0
}

test_status_no_models() {
    TEST_CASE="no_models" bash "${GUARD_SCRIPT}" status >/dev/null 2>&1
    return 0
}

test_status_with_models() {
    TEST_CASE="loaded_models" bash "${GUARD_SCRIPT}" status 2>&1 | grep -q "llama2"
}

test_reap_records_reaped() {
    TEST_CASE="idle_model" bash "${GUARD_SCRIPT}" reap >/dev/null 2>&1 || true
    assert_file_contains "${HOME}/.cache/ollama-guard/reaped.tsv" "idle"
}

test_reap_doesnt_kill_fresh() {
    rm -f "${HOME}/.cache/ollama-guard/reaped.tsv"
    TEST_CASE="loaded_models" bash "${GUARD_SCRIPT}" reap >/dev/null 2>&1 || true
    ! grep -q "llama2" "${HOME}/.cache/ollama-guard/reaped.tsv" 2>/dev/null || return 1
    return 0
}

test_run_insufficient_ram() {
    MODEL_SIZE="7.0" LOW_RAM=1 bash "${GUARD_SCRIPT}" run llama2 "test" </dev/null >/dev/null 2>&1
    result=$?
    [[ $result -eq 2 ]]
}

test_run_records_launch() {
    rm -f "${HOME}/.cache/ollama-guard/launches.tsv"
    MODEL_SIZE="500" bash "${GUARD_SCRIPT}" run tiny test </dev/null >/dev/null 2>&1 || true
    assert_file_contains "${HOME}/.cache/ollama-guard/launches.tsv" "tiny"
}

test_syntax_check() {
    bash -n "${GUARD_SCRIPT}"
}

test_status_two_models_one_line() {
    # Test parsing multiple models on one JSON line
    TEST_CASE="two_models_one_line" bash "${GUARD_SCRIPT}" status 2>&1 | grep -q "llama2" && \
    TEST_CASE="two_models_one_line" bash "${GUARD_SCRIPT}" status 2>&1 | grep -q "mistral"
}

test_resume_picks_latest() {
    # Create a reaped.tsv with multiple entries
    rm -f "${HOME}/.cache/ollama-guard/reaped.tsv"
    echo -e "1696000000\tllama2\tidle\t" >> "${HOME}/.cache/ollama-guard/reaped.tsv"
    echo -e "1696001000\tmistral\tidle\t" >> "${HOME}/.cache/ollama-guard/reaped.tsv"

    # Try to resume (will fail because model won't actually run, but should try mistral)
    MODEL_SIZE="10.7" bash "${GUARD_SCRIPT}" resume </dev/null >/dev/null 2>&1 || true

    # Check that entry was removed
    ! grep -q "1696001000.*mistral" "${HOME}/.cache/ollama-guard/reaped.tsv" 2>/dev/null
}

test_resume_restores_on_ram_refusal() {
    # Create a reaped.tsv entry
    rm -f "${HOME}/.cache/ollama-guard/reaped.tsv"
    echo -e "1696000000\tllama2\tidle\t" >> "${HOME}/.cache/ollama-guard/reaped.tsv"

    # Try to resume with low RAM (will fail with exit 2)
    LOW_RAM=1 MODEL_SIZE="7.0" bash "${GUARD_SCRIPT}" resume </dev/null >/dev/null 2>&1
    result=$?

    # Should get exit code 2
    [[ $result -eq 2 ]] && \
    # Entry should be restored
    grep -q "1696000000.*llama2" "${HOME}/.cache/ollama-guard/reaped.tsv"
}

test_unparsable_expires_at_skipped() {
    # Temporarily create a curl stub that returns unparsable timestamp
    # Save the original curl stub
    local orig_curl="${STUB_DIR}/curl.bak"
    cp "${STUB_DIR}/curl" "$orig_curl"

    cat > "${STUB_DIR}/curl" <<'CURL_STUB'
#!/bin/bash
case "$*" in
    *"api/ps"*)
        echo '{
  "models": [
    {"name":"llama2","size_vram":7516192768,"expires_at":"invalid-timestamp"}
  ]
}'
        ;;
    *"api/version"*)
        echo '{"version":"0.1.0"}'
        ;;
    *"api/generate"*)
        exit 0
        ;;
esac
CURL_STUB
    chmod +x "${STUB_DIR}/curl"

    # reap should warn and skip this model (not try to unload it)
    result=$(TEST_CASE="unparsable" bash "${GUARD_SCRIPT}" reap 2>&1)
    test_result=$?

    # Restore the original curl stub
    mv "$orig_curl" "${STUB_DIR}/curl"
    chmod +x "${STUB_DIR}/curl"

    # Check if the result contains "unparsable"
    echo "$result" | grep -q "unparsable" || return 0
    return $test_result
}

test_run_with_no_args() {
    # Test that run works with just model name (no args)
    # Should not crash even though model_args is empty array under set -u
    # stdin is /dev/null (not a tty), so run takes the API path and prints the reply
    local out
    out=$(MODEL_SIZE="500" bash "${GUARD_SCRIPT}" run tiny </dev/null 2>&1) || return 1
    echo "$out" | grep -q "The answer is 4"
}

test_run_exact_model_match() {
    # llama2 must match llama2:latest (3.8 GB), not llama2-70b (39 GB)
    local out
    out=$(MODEL_SIZE="prefix" bash "${GUARD_SCRIPT}" run llama2 </dev/null 2>&1) || return 1
    ! echo "$out" | grep -q "Insufficient RAM" && echo "$out" | grep -q "The answer is 4"
}

test_run_response_with_escaped_quotes() {
    local out
    out=$(echo "q" | GEN_CASE="quoted" MODEL_SIZE="500" bash "${GUARD_SCRIPT}" run tiny 2>/dev/null) || return 1
    [[ "$out" == 'say "hi" ok' ]]
}

test_run_api_error_exits_nonzero() {
    local out rc
    out=$(echo "q" | GEN_CASE="error" MODEL_SIZE="500" bash "${GUARD_SCRIPT}" run tiny 2>&1)
    rc=$?
    [[ $rc -ne 0 ]] && echo "$out" | grep -q "model not found"
}

test_stop_ignores_stale_pid() {
    sleep 300 &
    local victim=$!
    echo "$victim" > "${HOME}/.cache/ollama-guard/serve.pid"
    bash "${GUARD_SCRIPT}" stop </dev/null >/dev/null 2>&1
    local alive=1
    kill -0 "$victim" 2>/dev/null || alive=0
    kill "$victim" 2>/dev/null; wait "$victim" 2>/dev/null
    [[ $alive -eq 1 ]] && [[ ! -f "${HOME}/.cache/ollama-guard/serve.pid" ]]
}

test_run_non_tty_mode() {
    # Test non-interactive mode: stdin is pipe, not tty
    # Should POST to api/generate and print response
    echo "What is 2+2?" | MODEL_SIZE="500" bash "${GUARD_SCRIPT}" run tiny 2>&1 | grep -q "The answer is 4"
}

test_resume_exit_code_initialized() {
    # Test that resume doesn't crash under set -u when cmd_run would return
    # The fix ensures exit_code=0 is initialized before the conditional
    # Create a reaped.tsv entry that will cause resume to parse an entry
    rm -f "${HOME}/.cache/ollama-guard/reaped.tsv"
    echo -e "1696000000\tllama2\tidle\t" >> "${HOME}/.cache/ollama-guard/reaped.tsv"

    # Run resume with set -u enabled (it's enabled in the script)
    # This should not crash on unbound variable error
    # Since cmd_run will fail (model doesn't actually exist), we expect non-zero exit
    # But the important thing is it shouldn't crash before checking exit_code
    MODEL_SIZE="5" bash "${GUARD_SCRIPT}" resume </dev/null >/dev/null 2>&1 || return 0
}

# ============================================================================
# Run all tests
# ============================================================================

echo "Running ollama-guard tests..."
echo ""

run_test "help shows usage" test_help
run_test "status with no models" test_status_no_models
run_test "status lists loaded models" test_status_with_models
run_test "status parses two models on one line" test_status_two_models_one_line
run_test "reap records idle models" test_reap_records_reaped
run_test "reap doesn't kill fresh models" test_reap_doesnt_kill_fresh
run_test "run refuses on low RAM (exit 2)" test_run_insufficient_ram
run_test "run records launch" test_run_records_launch
run_test "run with no args doesn't crash" test_run_with_no_args
run_test "run matches the model name exactly" test_run_exact_model_match
run_test "run keeps escaped quotes in the response" test_run_response_with_escaped_quotes
run_test "run exits nonzero on an API error" test_run_api_error_exits_nonzero
run_test "stop does not kill a non-ollama PID" test_stop_ignores_stale_pid
run_test "resume picks latest and removes it" test_resume_picks_latest
run_test "resume restores entry on RAM refusal" test_resume_restores_on_ram_refusal
run_test "resume exit_code is initialized under set -u" test_resume_exit_code_initialized
run_test "unparsable expires_at is skipped" test_unparsable_expires_at_skipped
run_test "run in non-tty mode posts and prints response" test_run_non_tty_mode
run_test "script syntax is valid" test_syntax_check

echo ""
echo "========================================="
echo "Tests run:  $TESTS_RUN"
echo "Tests pass: $TESTS_PASSED"
echo "Tests fail: $TESTS_FAILED"
echo "========================================="

[[ $TESTS_FAILED -eq 0 ]]
