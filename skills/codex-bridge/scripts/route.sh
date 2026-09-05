#!/usr/bin/env bash
set -euo pipefail

readonly STATE_FILE="${HOME}/.codex-bridge/backend-health.json"
readonly MODE="${CODEX_BRIDGE_MODE:-standard}"
readonly ANTHROPIC_BACKENDS="haiku sonnet opus fable"

if [[ "$MODE" != "standard" && "$MODE" != "budget" && "$MODE" != "ultra" ]]; then
    echo "invalid CODEX_BRIDGE_MODE: $MODE (accepted values: standard, budget, ultra)" >&2
    exit 2
fi

_is_anthropic() {
    local backend
    for backend in $ANTHROPIC_BACKENDS; do
        [[ "$1" == "$backend" ]] && return 0
    done
    return 1
}

_get_chain() {
    local task_class="$1"

    if [[ "$MODE" == "ultra" ]]; then
        case "$task_class" in
            digest) echo "gemini-flash codex" ;;
            triage) echo "gemini-flash-lite gemini-flash" ;;
            logs) echo "gemini-flash-lite gemini-flash codex" ;;
            survey) echo "codex gemini-flash" ;;
            debug) echo "codex mistral gemini-flash" ;;
            review) echo "codex mistral gemini-flash" ;;
            code) echo "codex mistral gemini-flash ask" ;;
            transform) echo "gemini-flash-lite gemini-flash" ;;
            plan) echo "codex mistral gemini-flash" ;;
            orchestrate)
                echo "orchestration cannot be delegated in ultra mode and stays in the current session" >&2
                return 4
                ;;
            *) return 1 ;;
        esac
        return 0
    fi

    case "$task_class" in
        digest) echo "gemini-flash codex haiku openrouter" ;;
        triage) echo "gemini-flash-lite gemini-flash haiku openrouter" ;;
        logs) echo "gemini-flash-lite gemini-flash codex openrouter" ;;
        survey) echo "codex haiku gemini-flash" ;;
        debug) echo "codex sonnet gemini-flash" ;;
        review) echo "codex sonnet haiku" ;;
        code) echo "haiku gemini-flash codex ask" ;;
        transform) echo "gemini-flash-lite haiku" ;;
        plan) echo "sonnet opus fable" ;;
        orchestrate)
            if [[ "$MODE" == "budget" ]]; then
                echo "sonnet opus fable"
            else
                echo "fable opus sonnet"
            fi
            ;;
        *) return 1 ;;
    esac
}

_valid_classes() {
    echo "digest triage logs survey debug review code transform plan orchestrate"
}

_init_state() {
    if [[ ! -f "$STATE_FILE" ]]; then
        mkdir -p "$(dirname "$STATE_FILE")"
        python3 - <<'PYEOF'
import json
import os

state = {}
for backend in ["gemini-flash", "gemini-flash-lite", "codex", "mistral", "openrouter", "haiku", "sonnet", "opus", "fable"]:
    state[backend] = {
        "status": "ok",
        "cooldown_until": None,
        "last_error": None,
        "last_checked": None
    }

path = os.path.expanduser("~/.codex-bridge/backend-health.json")
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'w') as f:
    json.dump(state, f, indent=2)
os.chmod(path, 0o600)
PYEOF
    else
        local state_json=$(_read_state)
        local new_state
        new_state=$(python3 - "$state_json" <<'PYEOF'
import json
import sys

data = json.loads(sys.argv[1])
for backend in ["mistral", "opus", "fable"]:
    data.setdefault(backend, {
        "status": "ok",
        "cooldown_until": None,
        "last_error": None,
        "last_checked": None
    })
print(json.dumps(data))
PYEOF
)
        _write_state "$new_state"
    fi
}

_read_state() {
    python3 - <<'PYEOF'
import json
import os

path = os.path.expanduser("~/.codex-bridge/backend-health.json")
with open(path, 'r') as f:
    print(json.dumps(json.load(f)))
PYEOF
}

_write_state() {
    local new_state="$1"
    python3 - "$new_state" <<'PYEOF'
import json
import os
import tempfile
import sys

path = os.path.expanduser("~/.codex-bridge/backend-health.json")
new_state = sys.argv[1]

with tempfile.NamedTemporaryFile(mode='w', dir=os.path.dirname(path), delete=False, suffix='.json') as tmp:
    tmp.write(new_state)
    tmp_path = tmp.name

os.replace(tmp_path, path)
os.chmod(path, 0o600)
PYEOF
}

_classify() {
    local text="$1"

    if echo "$text" | grep -qiE '(RESOURCE_EXHAUSTED|Quota exceeded|free_tier_requests|limit: 0|rate limit|429)'; then
        echo "quota"
    elif echo "$text" | grep -qiE '(high demand|503|temporarily|try again later|connection|timeout)'; then
        echo "transient"
    else
        echo "unknown"
    fi
}

cmd_pick() {
    local task_class="$1"
    local chain

    chain=$(_get_chain "$task_class") || {
        local chain_status=$?
        [[ "$chain_status" -eq 4 ]] && exit 4
        echo "unknown task class: $task_class" >&2
        echo "Valid: $(_valid_classes)" >&2
        exit 2
    }

    _init_state
    local state_json=$(_read_state)

    for backend in $chain; do
        # Handle terminal pseudo-backend 'ask'
        if [[ "$backend" == "ask" ]]; then
            echo "ask"
            return 0
        fi

        # Check if backend has an active cooldown
        local is_cooling
        is_cooling=$(python3 - "$state_json" "$backend" <<'PYEOF'
import json
import sys
from datetime import datetime, timezone

data = json.loads(sys.argv[1])
backend = sys.argv[2]

cooldown_str = data.get(backend, {}).get('cooldown_until')
if cooldown_str:
    cooldown_dt = datetime.fromisoformat(cooldown_str)
    now = datetime.now(timezone.utc)
    print("yes" if now < cooldown_dt else "no")
else:
    print("no")
PYEOF
)

        if [[ "$is_cooling" == "no" ]]; then
            if [[ "$MODE" == "ultra" ]] && _is_anthropic "$backend"; then
                echo "ultra mode refused Anthropic backend '$backend' for task class '$task_class'" >&2
                exit 5
            fi
            echo "$backend"
            return 0
        fi
    done

    echo "NONE"
    exit 3
}

cmd_report() {
    local backend="$1"
    local result="$2"
    local message="${3:-}"

    _init_state
    local state_json=$(_read_state)

    local new_state
    new_state=$(python3 - "$state_json" "$backend" "$result" "$message" <<'PYEOF'
import json
import sys
from datetime import datetime, timezone, timedelta

data = json.loads(sys.argv[1])
backend = sys.argv[2]
result = sys.argv[3]
message = sys.argv[4] if len(sys.argv) > 4 else ""

if result == 'ok':
    data[backend]['status'] = 'ok'
    data[backend]['cooldown_until'] = None
elif result == 'transient':
    data[backend]['status'] = 'degraded'
elif result == 'quota':
    data[backend]['status'] = 'exhausted'
    now = datetime.now(timezone.utc)

    if backend.startswith('gemini'):
        # Until next UTC midnight
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        data[backend]['cooldown_until'] = next_midnight.isoformat()
    else:
        # 60 minutes from now
        cooldown_time = now + timedelta(minutes=60)
        data[backend]['cooldown_until'] = cooldown_time.isoformat()

if message:
    data[backend]['last_error'] = message[:200]
data[backend]['last_checked'] = datetime.now(timezone.utc).isoformat()

print(json.dumps(data))
PYEOF
)

    _write_state "$new_state"
}

cmd_status() {
    local format="${1:-text}"

    _init_state
    local state_json=$(_read_state)

    if [[ "$format" == "--json" ]]; then
        echo "$state_json"
    else
        python3 - "$state_json" <<'PYEOF'
import json
import sys
from datetime import datetime, timezone

data = json.loads(sys.argv[1])
now = datetime.now(timezone.utc)

print("Backend           Status      Cooldown Remaining     Last Error")
print("-" * 85)

for backend in ["gemini-flash", "gemini-flash-lite", "codex", "mistral", "openrouter", "haiku", "sonnet", "opus", "fable"]:
    info = data.get(backend, {})
    status = info.get('status', 'unknown')
    cooldown_str = info.get('cooldown_until')
    last_error = info.get('last_error', '')

    # Normalize status: if cooldown has expired, show as ok
    if cooldown_str:
        cooldown_dt = datetime.fromisoformat(cooldown_str)
        if now < cooldown_dt:
            remaining = cooldown_dt - now
            mins = int(remaining.total_seconds() / 60)
            secs = int(remaining.total_seconds() % 60)
            cooldown_display = f"{mins}m {secs}s"
        else:
            # Cooldown expired, normalize status to ok
            cooldown_display = "-"
            status = "ok"
            last_error = None
    else:
        cooldown_display = "-"

    error_display = last_error[:60] if last_error else "-"

    print(f"{backend:17} {status:11} {cooldown_display:22} {error_display}")
PYEOF
    fi
}

cmd_classify() {
    local text="$1"
    _classify "$text"
}

cmd_clear() {
    local target_backend="${1:-}"

    _init_state
    local state_json=$(_read_state)

    local new_state
    if [[ -z "$target_backend" ]]; then
        new_state=$(python3 - "$state_json" <<'PYEOF'
import json
import sys
from datetime import datetime, timezone

data = json.loads(sys.argv[1])
now = datetime.now(timezone.utc).isoformat()
for backend in data:
    data[backend]['status'] = 'ok'
    data[backend]['cooldown_until'] = None
    data[backend]['last_error'] = None
    data[backend]['last_checked'] = now
print(json.dumps(data))
PYEOF
)
    else
        new_state=$(python3 - "$state_json" "$target_backend" <<'PYEOF'
import json
import sys
from datetime import datetime, timezone

data = json.loads(sys.argv[1])
backend = sys.argv[2]
now = datetime.now(timezone.utc).isoformat()
if backend in data:
    data[backend]['status'] = 'ok'
    data[backend]['cooldown_until'] = None
    data[backend]['last_error'] = None
    data[backend]['last_checked'] = now
print(json.dumps(data))
PYEOF
)
    fi

    _write_state "$new_state"
}

# Guard
command -v python3 >/dev/null || { echo "python3 required" >&2; exit 127; }

# Dispatch
case "${1:-}" in
    pick) cmd_pick "${2:-}" ;;
    report) cmd_report "$2" "$3" "${4:-}" ;;
    status) cmd_status "${2:-}" ;;
    classify) cmd_classify "$2" ;;
    clear) cmd_clear "${2:-}" ;;
    *) echo "Usage: route.sh {pick|report|status|classify|clear}" >&2; exit 1 ;;
esac
