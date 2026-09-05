#!/usr/bin/env bash
set -euo pipefail

readonly TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SKILL_DIR="$(cd "$TEST_DIR/.." && pwd)"
readonly MODULE="$SKILL_DIR/scripts/data_policy.py"
readonly FIXTURE="$TEST_DIR/fixtures/optout_payload.txt"
readonly GASK="$SKILL_DIR/scripts/gask.sh"
readonly MASK="$SKILL_DIR/scripts/mask.sh"
TEST_ROOT=$(mktemp -d)
readonly TEST_ROOT
trap 'rm -rf "$TEST_ROOT"' EXIT

assertion=0
pass() {
  assertion=$((assertion + 1))
  printf 'ok %d - %s\n' "$assertion" "$1"
}
fail() {
  printf 'not ok - %s\n' "$1" >&2
  exit 1
}

python3 - "$MODULE" "$FIXTURE" <<'PY' || fail "constant differs from fixture"
import importlib.util
import pathlib
import sys

spec = importlib.util.spec_from_file_location("data_policy", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert module.OPT_OUT_PAYLOAD.encode("utf-8") == pathlib.Path(sys.argv[2]).read_bytes()
PY
pass "OPT_OUT_PAYLOAD is byte-identical to the supplied fixture"

python3 - "$MODULE" <<'PY' || fail "prepare_prompt is not idempotent"
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("data_policy", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
once = module.prepare_prompt("prompt  \n")
assert once == "prompt" + module.OPT_OUT_PAYLOAD
assert module.prepare_prompt(once) == once
assert once.count(module.OPT_OUT_PAYLOAD) == 1
PY
pass "prepare_prompt appends exactly once"

python3 - "$MODULE" <<'PY' || fail "blank input gained a payload"
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("data_policy", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
for value in ("", "   ", "\t\n  "):
    assert module.prepare_prompt(value) == value
PY
pass "empty and whitespace-only input remains unchanged"

python3 - "$TEST_ROOT/cli-input" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_text("single ' double \" slash \\\nline two — café\n", encoding="utf-8")
PY
python3 "$MODULE" < "$TEST_ROOT/cli-input" > "$TEST_ROOT/cli-output"
python3 - "$MODULE" "$TEST_ROOT/cli-input" "$TEST_ROOT/cli-output" <<'PY' || fail "CLI mangled prompt content"
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location("data_policy", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
source = Path(sys.argv[2]).read_text(encoding="utf-8")
assert Path(sys.argv[3]).read_bytes() == module.prepare_prompt(source).encode("utf-8")
PY
pass "CLI preserves quotes, backslashes, newlines, and non-ASCII"

CODEX_BRIDGE_OPTOUT=0 python3 "$MODULE" < "$TEST_ROOT/cli-input" > "$TEST_ROOT/disabled-output"
cmp -s "$TEST_ROOT/cli-input" "$TEST_ROOT/disabled-output" || fail "disabled CLI changed stdin"
pass "CODEX_BRIDGE_OPTOUT=0 passes stdin through byte-for-byte"

mkdir -p "$TEST_ROOT/bin" "$TEST_ROOT/home/.codex-bridge"
printf 'test-key' > "$TEST_ROOT/home/.codex-bridge/gemini-key"
chmod 600 "$TEST_ROOT/home/.codex-bridge/gemini-key"
cat > "$TEST_ROOT/bin/curl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
output=""
body=""
args=("$@")
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) output="$2"; shift 2 ;;
    --data-binary) body="$2"; shift 2 ;;
    *) shift ;;
  esac
done
[[ -z "${CURL_ARGS_FILE:-}" ]] || printf '%s\n' "${args[@]}" > "$CURL_ARGS_FILE"
cp "${body#@}" "$CAPTURE_FILE"
printf '%s' '{"candidates":[{"content":{"parts":[{"text":"ok"}]}}],"usageMetadata":{}}' > "$output"
printf '200'
SH
chmod +x "$TEST_ROOT/bin/curl"

CAPTURE_FILE="$TEST_ROOT/body-present" PATH="$TEST_ROOT/bin:$PATH" HOME="$TEST_ROOT/home" \
  "$GASK" "prompt" > "$TEST_ROOT/gask.out" 2> "$TEST_ROOT/gask.err"
python3 - "$MODULE" "$TEST_ROOT/body-present" <<'PY' || fail "gask body lacks one trailing payload"
import importlib.util
import json
import sys
spec = importlib.util.spec_from_file_location("data_policy", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with open(sys.argv[2], encoding="utf-8") as handle:
    text = json.load(handle)["contents"][0]["parts"][0]["text"]
assert text.endswith(module.OPT_OUT_PAYLOAD)
assert text.count(module.OPT_OUT_PAYLOAD) == 1
PY
pass "gask builds a body with one payload at the final position"

printf 'file context' > "$TEST_ROOT/context.txt"
python3 - "$MODULE" "$GASK" "$TEST_ROOT" <<'PY' || fail "gask duplicated a caller-supplied payload"
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

spec = importlib.util.spec_from_file_location("data_policy", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = Path(sys.argv[3])
env = os.environ.copy()
env.update({
    "CAPTURE_FILE": str(root / "body-prepared"),
    "HOME": str(root / "home"),
    "PATH": f"{root / 'bin'}:{env['PATH']}",
})
subprocess.run(
    [sys.argv[2], "--file", str(root / "context.txt"), module.prepare_prompt("prompt")],
    env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
)
with open(root / "body-prepared", encoding="utf-8") as handle:
    text = json.load(handle)["contents"][0]["parts"][0]["text"]
assert text.endswith(module.OPT_OUT_PAYLOAD)
assert text.count(module.OPT_OUT_PAYLOAD) == 1
assert text.index("file context") < text.index(module.OPT_OUT_PAYLOAD)
PY
pass "gask relocates an existing payload after file blocks without duplication"

mkdir -p "$TEST_ROOT/hidden"
cp "$GASK" "$TEST_ROOT/hidden/gask.sh"
chmod +x "$TEST_ROOT/hidden/gask.sh"
CAPTURE_FILE="$TEST_ROOT/body-hidden" PATH="$TEST_ROOT/bin:$PATH" HOME="$TEST_ROOT/home" \
  "$TEST_ROOT/hidden/gask.sh" "prompt" > "$TEST_ROOT/hidden.out" 2> "$TEST_ROOT/hidden.err"
python3 - "$TEST_ROOT/body-hidden" <<'PY' || fail "gask failed when data_policy was hidden"
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    text = json.load(handle)["contents"][0]["parts"][0]["text"]
assert text == "prompt"
PY
pass "gask builds an unaugmented body when data_policy import fails"

CURL_ARGS_FILE="$TEST_ROOT/curl-args" CAPTURE_FILE="$TEST_ROOT/body-timeouts" \
  GASK_TIMEOUT=731 GASK_CONNECT_TIMEOUT=9 PATH="$TEST_ROOT/bin:$PATH" HOME="$TEST_ROOT/home" \
  "$GASK" "prompt" >/dev/null 2>/dev/null
grep -Fxq -- '--max-time' "$TEST_ROOT/curl-args" || fail "gask omitted --max-time"
grep -Fxq -- '731' "$TEST_ROOT/curl-args" || fail "gask omitted GASK_TIMEOUT value"
grep -Fxq -- '--connect-timeout' "$TEST_ROOT/curl-args" || fail "gask omitted --connect-timeout"
grep -Fxq -- '9' "$TEST_ROOT/curl-args" || fail "gask omitted GASK_CONNECT_TIMEOUT value"
pass "gask passes both timeout overrides to curl"

mkdir -p "$TEST_ROOT/timeout-bin"
cat > "$TEST_ROOT/timeout-bin/curl" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
limit=99
while [[ $# -gt 0 ]]; do
  case "$1" in
    --max-time) limit="$2"; shift 2 ;;
    *) shift ;;
  esac
done
sleep "$limit"
exit 28
SH
chmod +x "$TEST_ROOT/timeout-bin/curl"
start=$SECONDS
set +e
CAPTURE_FILE="$TEST_ROOT/unused" GASK_TIMEOUT=1 PATH="$TEST_ROOT/timeout-bin:$PATH" HOME="$TEST_ROOT/home" \
  "$GASK" "prompt" >/dev/null 2>"$TEST_ROOT/gask-timeout.err"
timeout_status=$?
set -e
elapsed=$((SECONDS - start))
[[ $timeout_status -ne 0 && $elapsed -ge 1 && $elapsed -le 3 ]] || fail "gask timeout did not fail near its bound"
grep -Fq 'gemini timeout after 1s' "$TEST_ROOT/gask-timeout.err" || fail "gask timeout message omitted its limit"
pass "gask timeout fails promptly with a distinct timeout message"

mkdir -p "$TEST_ROOT/python-hook"
cat > "$TEST_ROOT/python-hook/sitecustomize.py" <<'PY'
import json
import os
import urllib.request

class Response:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        if os.environ.get("MOCK_AGENT") == "1":
            body = {"outputs": [{"type": "message.output", "role": "assistant", "content": "ok"}]}
        else:
            body = {"choices": [{"message": {"content": "ok"}}]}
        return json.dumps(body).encode()

def urlopen(request, timeout):
    with open(os.environ["MASK_TIMEOUT_CAPTURE"], "w", encoding="utf-8") as handle:
        handle.write(str(timeout))
    if os.environ.get("MOCK_TIMEOUT") == "1":
        raise TimeoutError("simulated slow backend")
    return Response()

urllib.request.urlopen = urlopen
PY

MASK_TIMEOUT_CAPTURE="$TEST_ROOT/mask-plain-timeout" MASK_TIMEOUT=47 MISTRAL_API_KEY=test \
  PYTHONPATH="$TEST_ROOT/python-hook" HOME="$TEST_ROOT/home" "$MASK" "prompt" >/dev/null 2>/dev/null
[[ "$(<"$TEST_ROOT/mask-plain-timeout")" == "47.0" ]] || fail "MASK_TIMEOUT did not reach urlopen"
pass "mask passes the plain-completion timeout override to urlopen"

MASK_TIMEOUT_CAPTURE="$TEST_ROOT/mask-agent-timeout" MASK_AGENT_TIMEOUT=503 MISTRAL_API_KEY=test \
  MISTRAL_AGENT_ID=agent MOCK_AGENT=1 PYTHONPATH="$TEST_ROOT/python-hook" HOME="$TEST_ROOT/home" \
  "$MASK" --agent --reset "prompt" >/dev/null 2>/dev/null
[[ "$(<"$TEST_ROOT/mask-agent-timeout")" == "503.0" ]] || fail "MASK_AGENT_TIMEOUT did not reach urlopen"
pass "mask passes the agent timeout override to urlopen"

set +e
MASK_TIMEOUT_CAPTURE="$TEST_ROOT/mask-timeout-value" MASK_AGENT_TIMEOUT=3 MISTRAL_API_KEY=test \
  MISTRAL_AGENT_ID=agent MOCK_AGENT=1 MOCK_TIMEOUT=1 PYTHONPATH="$TEST_ROOT/python-hook" HOME="$TEST_ROOT/home" \
  "$MASK" --agent --reset "prompt" >/dev/null 2>"$TEST_ROOT/mask-timeout.err"
mask_status=$?
set -e
[[ $mask_status -ne 0 ]] || fail "mask agent timeout returned success"
grep -Fq 'mistral agent timeout after 3s' "$TEST_ROOT/mask-timeout.err" || fail "mask agent timeout message omitted kind or limit"
! grep -Fq 'cannot reach' "$TEST_ROOT/mask-timeout.err" || fail "mask agent timeout was misreported as unreachable"
pass "mask identifies an agent timeout and reports its limit"

mkdir -p "$TEST_ROOT/probe-bin"
cat > "$TEST_ROOT/probe-bin/curl" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$@" >> "$PROBE_ARGS_FILE"
exit 0
SH
chmod +x "$TEST_ROOT/probe-bin/curl"
cat > "$TEST_ROOT/probe-bin/pgrep" <<'SH'
#!/usr/bin/env bash
printf '4242\n'
SH
chmod +x "$TEST_ROOT/probe-bin/pgrep"
printf '%s\n' '{"port":8787,"url":"http://127.0.0.1:8787","workdir":"/tmp","sandbox":"workspace-write"}' \
  > "$TEST_ROOT/home/.codex-bridge/state.json"
printf 'token' > "$TEST_ROOT/home/.codex-bridge/token"
PROBE_ARGS_FILE="$TEST_ROOT/status-probes" PATH="$TEST_ROOT/probe-bin:$PATH" HOME="$TEST_ROOT/home" \
  "$SKILL_DIR/scripts/status.sh" >/dev/null
[[ $(grep -Fxc -- '--max-time' "$TEST_ROOT/status-probes") -eq 2 ]] || fail "status probes omitted --max-time"
[[ $(grep -Fxc -- '2' "$TEST_ROOT/status-probes") -eq 2 ]] || fail "status probes omitted the two-second value"
pass "status bounds both localhost health and session probes to two seconds"

PROBE_ARGS_FILE="$TEST_ROOT/up-probe" PATH="$TEST_ROOT/probe-bin:$PATH" HOME="$TEST_ROOT/home" \
  "$SKILL_DIR/scripts/up.sh" --workdir /tmp >/dev/null
grep -Fxq -- '--max-time' "$TEST_ROOT/up-probe" || fail "up health probe omitted --max-time"
grep -Fxq -- '2' "$TEST_ROOT/up-probe" || fail "up health probe omitted the two-second value"
pass "up bounds its localhost existing-bridge probe to two seconds"

printf 'passed %d assertions\n' "$assertion"
