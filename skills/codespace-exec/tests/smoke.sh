#!/usr/bin/env bash
set -euo pipefail

readonly TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SKILL_DIR="$(cd "$TEST_DIR/.." && pwd)"
FAKE_ROOT=$(mktemp -d)
trap 'rm -rf "$FAKE_ROOT"' EXIT
mkdir -p "$FAKE_ROOT/home"
export HOME="$FAKE_ROOT/home"
# shellcheck source=../scripts/lib.sh
source "$SKILL_DIR/scripts/lib.sh"

PASS_COUNT=0

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  echo "ok $PASS_COUNT - $1"
}

fail() {
  echo "not ok - $1" >&2
  exit 1
}

parse_exec_args --dir "repo path" -- printf '%s' "two words" "it's quoted" || fail "argument parser returned failure"
[[ "$REQUESTED_DIR" == "repo path" ]] || fail "--dir was not parsed"
[[ ${#EXEC_COMMAND[@]} -eq 4 ]] || fail "command argv count changed"
[[ "${EXEC_COMMAND[2]}" == "two words" && "${EXEC_COMMAND[3]}" == "it's quoted" ]] || fail "command arguments changed"
pass "argument parsing preserves the -- separator, spaces, and quotes"

QUOTING_DIR="$FAKE_ROOT/repo path"
mkdir -p "$QUOTING_DIR"
QUOTED_COMMAND=$(build_remote_command "$QUOTING_DIR" printf '<%s>\n' "two words" "it's quoted" 'dollar $HOME')
QUOTING_STATUS="$FAKE_ROOT/quoting-status"
QUOTED_OUTPUT=$(bash -c "$QUOTED_COMMAND" | capture_remote_stdout "$QUOTING_STATUS")
EXPECTED_OUTPUT=$'<two words>\n<it\'s quoted>\n<dollar $HOME>'
[[ "$QUOTED_OUTPUT" == "$EXPECTED_OUTPUT" ]] || fail "remote command quoting changed argument values"
[[ "$(<"$QUOTING_STATUS")" == "0" ]] || fail "quoted remote command did not emit a success sentinel"
pass "remote command quoting survives spaces, single quotes, and dollar signs"

SENTINEL_STATUS="$FAKE_ROOT/sentinel-status"
SENTINEL_OUTPUT=$(printf 'first\nsecond\n__CSEXIT__7\n' | capture_remote_stdout "$SENTINEL_STATUS")
[[ "$SENTINEL_OUTPUT" == $'first\nsecond' ]] || fail "sentinel parser changed normal output"
[[ "$(<"$SENTINEL_STATUS")" == "7" ]] || fail "sentinel parser lost the remote status"
pass "sentinel parser strips only the final sentinel and captures its status"

: > "$SENTINEL_STATUS"
LOOKALIKE_OUTPUT=$(printf 'first\n__CSEXIT__7x\n__CSEXIT__0\n' | capture_remote_stdout "$SENTINEL_STATUS")
[[ "$LOOKALIKE_OUTPUT" == $'first\n__CSEXIT__7x' ]] || fail "sentinel parser confused command output with the final sentinel"
[[ "$(<"$SENTINEL_STATUS")" == "0" ]] || fail "sentinel parser missed the final exact sentinel"
pass "sentinel parser preserves output that only resembles a sentinel"

: > "$SENTINEL_STATUS"
MISSING_OUTPUT=$(printf 'first\nlast\n' | capture_remote_stdout "$SENTINEL_STATUS")
[[ "$MISSING_OUTPUT" == $'first\nlast' ]] || fail "missing-sentinel handling dropped output"
[[ ! -s "$SENTINEL_STATUS" ]] || fail "missing-sentinel handling invented a status"
[[ "$(resolve_remote_status "$SENTINEL_STATUS" 7)" == "7" ]] || fail "missing sentinel did not fall back to gh status"
set +e
UNKNOWN_ERROR=$(resolve_remote_status "$SENTINEL_STATUS" 0 2>&1)
UNKNOWN_RESULT=$?
set -e
[[ $UNKNOWN_RESULT -ne 0 && "$UNKNOWN_ERROR" == *"remote status could not be determined"* ]] || fail "unknown remote status was reported as success"
pass "missing-sentinel handling falls back to gh or reports an unknown status"

mkdir -p "$FAKE_ROOT/timeout-bin"
cat > "$FAKE_ROOT/timeout-bin/timeout" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$@" >> "$TIMEOUT_ARGS_FILE"
[[ "${1:-}" == "--foreground" ]] && shift
shift
exec "$@"
SH
cat > "$FAKE_ROOT/timeout-bin/gh" <<'SH'
#!/usr/bin/env bash
[[ "${*: -1}" == "true" ]] && exit 0
printf '%s\n' '__CSEXIT__0'
SH
chmod +x "$FAKE_ROOT/timeout-bin/timeout" "$FAKE_ROOT/timeout-bin/gh"
TIMEOUT_ARGS_FILE="$FAKE_ROOT/timeout-args" CODESPACE_CONNECT_TIMEOUT=17 CODESPACE_EXEC_TIMEOUT=83 \
  PATH="$FAKE_ROOT/timeout-bin:$PATH" bash -c \
  'source "$1"; codespace_ssh "command"' _ "$SKILL_DIR/scripts/lib.sh" >/dev/null
grep -Fxq '17' "$FAKE_ROOT/timeout-args" || fail "connection timeout override did not reach timeout"
grep -Fxq '83' "$FAKE_ROOT/timeout-args" || fail "execution timeout override did not reach timeout"
pass "codespace passes separate connection and execution bounds to timeout"

mkdir -p "$FAKE_ROOT/enforce-bin"
cat > "$FAKE_ROOT/enforce-bin/gh" <<'SH'
#!/usr/bin/env bash
[[ "${*: -1}" == "true" ]] && exit 0
sleep 5
printf '%s\n' '__CSEXIT__0'
SH
chmod +x "$FAKE_ROOT/enforce-bin/gh"
start=$SECONDS
set +e
timeout_output=$(CODESPACE_CONNECT_TIMEOUT=2 CODESPACE_EXEC_TIMEOUT=1 PATH="$FAKE_ROOT/enforce-bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  bash -c 'source "$1"; codespace_ssh "command"' _ "$SKILL_DIR/scripts/lib.sh" 2>&1)
timeout_result=$?
set -e
elapsed=$((SECONDS - start))
[[ $timeout_result -eq 124 && $elapsed -ge 1 && $elapsed -le 3 ]] || fail "remote execution timeout did not return 124 near its bound"
[[ "$timeout_output" == *"remote command timeout after 1s"* ]] || fail "remote execution timeout was not identified"
[[ "$timeout_output" != *"__CSEXIT__0"* ]] || fail "timed-out command emitted a success sentinel"
pass "codespace timeout is reported as timeout, exits 124, and cannot become remote exit 0"

codespace_ssh() {
  printf '%s\n' '/workspaces/.codespaces' '/workspaces/QuADMESH-RL' '/workspaces/.oryx'
}
RESOLVED_PATH=$(resolve_repository_path "")
[[ "$RESOLVED_PATH" == "/workspaces/QuADMESH-RL" ]] || fail "dot-directories affected repository resolution"
[[ "$(<"$STATE_FILE")" == "/workspaces/QuADMESH-RL" ]] || fail "resolved repository path was not cached"
pass "repository resolution ignores dot-directories and caches the sole real candidate"

mkdir -p "$FAKE_ROOT/bin" "$FAKE_ROOT/home"
FAKE_GH="$FAKE_ROOT/bin/gh"
printf '%s\n' '#!/usr/bin/env bash' \
  'if [[ "${1:-}" == "auth" && "${2:-}" == "status" ]]; then exit 0; fi' \
  'echo "error getting codespaces: HTTP 403: Must have admin rights to Repository." >&2' \
  'echo "This API operation needs the \"codespace\" scope." >&2' \
  'exit 1' > "$FAKE_GH"
chmod +x "$FAKE_GH"

set +e
PREFLIGHT_OUTPUT=$(PATH="$FAKE_ROOT/bin:$PATH" HOME="$FAKE_ROOT/home" "$SKILL_DIR/scripts/preflight.sh" 2>&1)
PREFLIGHT_STATUS=$?
set -e
[[ $PREFLIGHT_STATUS -ne 0 ]] || fail "scope failure returned success"
grep -Fq 'gh auth refresh -h github.com -s codespace' <<< "$PREFLIGHT_OUTPUT" || fail "scope remedy was absent"
pass "preflight rejects the recorded 403 and prints the exact scope remedy"

if grep -R -E 'gh[[:space:]]+codespace[[:space:]]+(create|delete)' "$SKILL_DIR" >/dev/null; then
  fail "a script can create or delete a Codespace"
fi
pass "scripts contain no Codespace create or delete invocation"

echo "passed $PASS_COUNT assertions"
