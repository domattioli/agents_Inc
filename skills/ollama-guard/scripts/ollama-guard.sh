#!/bin/bash
set -euo pipefail

# ollama-guard: deterministic local Ollama management
# No daemon, no background loop. Scanning runs ONLY when invoked.

readonly OLLAMA_BIN="${OLLAMA_BIN:-/opt/homebrew/bin/ollama}"
readonly OLLAMA_API_BASE="localhost:11434"
readonly CACHE_DIR="${HOME}/.cache/ollama-guard"
readonly SERVE_LOG="${CACHE_DIR}/serve.log"
readonly SERVE_PID_FILE="${CACHE_DIR}/serve.pid"
readonly KEEP_ALIVE_MIN="${OLLAMA_GUARD_KEEP_ALIVE_MIN:-5}"
readonly OLLAMA_GUARD_NUM_CTX="${OLLAMA_GUARD_NUM_CTX:-16384}"

# Allow time override for testing (epoch seconds)
readonly NOW="${OLLAMA_GUARD_NOW:=$(date +%s)}"

# ============================================================================
# Utility: Get usable RAM in GB from vm_stat (macOS)
# ============================================================================
get_usable_ram_gb() {
    # vm_stat returns: "Pages free: N", "Pages inactive: N", "Pages speculative: N"
    # Usable RAM = (free + inactive + speculative) * page_size
    local page_size
    page_size=$(sysctl -n hw.pagesize)

    local free_pages inactive_pages speculative_pages
    free_pages=$(vm_stat | awk '/^Pages free:/ {print $3}' | tr -d '.')
    inactive_pages=$(vm_stat | awk '/^Pages inactive:/ {print $3}' | tr -d '.')
    speculative_pages=$(vm_stat | awk '/^Pages speculative:/ {print $3}' | tr -d '.')

    # Avoid division by zero
    free_pages="${free_pages:-0}"
    inactive_pages="${inactive_pages:-0}"
    speculative_pages="${speculative_pages:-0}"

    local total_pages
    total_pages=$((free_pages + inactive_pages + speculative_pages))

    local bytes
    bytes=$((total_pages * page_size))

    # Convert to GB (divide by 1073741824)
    echo "scale=2; $bytes / 1073741824" | bc
}

# ============================================================================
# Utility: Parse ISO 8601 timestamp to epoch seconds (macOS date -j)
# Handles timezone offset, strips fractional seconds.
# Returns empty string on parse failure.
# ============================================================================
parse_iso_timestamp() {
    local ts="$1"

    # Strip fractional seconds and timezone offset (e.g., .123Z or .123+00:00)
    # Input: "2026-09-29T10:30:45.123456Z" or "2026-09-29T10:30:45.123+05:30"
    # Result: "2026-09-29T10:30:45Z" or compute offset adjustment

    # Remove fractional seconds
    ts="${ts%\.*}"

    # Handle timezone: if ends with Z, add +00:00; if has ±HH:MM, normalize
    local tz_offset=0
    if [[ "$ts" =~ \+([0-9]{2}):([0-9]{2})$ ]]; then
        # Positive offset: +05:30
        local tz_h="${BASH_REMATCH[1]}"
        local tz_m="${BASH_REMATCH[2]}"
        tz_offset=$((tz_h * 3600 + tz_m * 60))
        ts="${ts%+*}"  # Remove the offset from string
    elif [[ "$ts" =~ -([0-9]{2}):([0-9]{2})$ ]] && [[ ! "$ts" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2} ]]; then
        # Negative offset at the end: -05:30
        local tz_h="${BASH_REMATCH[1]}"
        local tz_m="${BASH_REMATCH[2]}"
        tz_offset=$((-1 * (tz_h * 3600 + tz_m * 60)))
        ts="${ts%-*}"  # Remove the offset from string
    elif [[ "$ts" == *Z ]]; then
        ts="${ts%Z}"
        tz_offset=0
    fi

    # Try to parse: date -j -f format input
    # macOS date -j does not support '%z', so we'll use a reference format
    local epoch
    if ! epoch=$(date -j -f "%Y-%m-%dT%H:%M:%S" "$ts" +%s 2>/dev/null); then
        # Parse failed
        return 1
    fi

    # Adjust for timezone offset
    epoch=$((epoch + tz_offset))
    echo "$epoch"
}

# ============================================================================
# Utility: Check if Ollama server is running
# ============================================================================
is_server_running() {
    curl -s "http://${OLLAMA_API_BASE}/api/version" >/dev/null 2>&1
}

# ============================================================================
# Utility: Check if a process has a live TTY/parent
# A process is orphaned if PPID=1 and has no controlling terminal.
# ============================================================================
is_process_orphaned() {
    local pid="$1"
    local ppid

    ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | xargs) || return 1

    # If PPID is 1, it's orphaned
    [[ "$ppid" == "1" ]]
}

# ============================================================================
# Utility: Record a model unload action to reaped.tsv
# Format: epoch \t model \t reason \t original_args
# ============================================================================
record_reaped() {
    local model="$1"
    local reason="$2"
    local args="${3:-}"

    mkdir -p "$CACHE_DIR"
    echo -e "${NOW}\t${model}\t${reason}\t${args}" >> "${CACHE_DIR}/reaped.tsv"
}

# ============================================================================
# Utility: Record a model launch to launches.tsv
# Format: epoch \t model \t args
# ============================================================================
record_launch() {
    local model="$1"
    local args="${2:-}"

    mkdir -p "$CACHE_DIR"
    echo -e "${NOW}\t${model}\t${args}" >> "${CACHE_DIR}/launches.tsv"
}

# ============================================================================
# Utility: JSON-escape a string (backslash, quote, tab, newline, CR)
# ============================================================================
json_escape() {
    local s="$1"
    # Use sed to escape special characters for JSON
    # Order matters: escape backslash first
    s="${s//\\/\\\\}"   # backslash → \\
    s="${s//\"/\\\"}"   # quote → \"
    s="${s//$'\t'/\\t}"  # tab → \t
    s="${s//$'\n'/\\n}"  # newline → \n
    s="${s//$'\r'/\\r}"  # CR → \r
    echo "$s"
}

# ============================================================================
# Utility: Start Ollama server (once, if not running)
# Stores PID file so we only kill servers we started.
# ============================================================================
# Print the decoded value of top-level string key $1 from the JSON on stdin.
# Walks the string honouring backslash escapes, so embedded \" does not
# truncate it. \uXXXX escapes stay literal. Exit 1 when the key is absent.
json_string_field() {
    awk -v key="$1" 'BEGIN { RS = "\001" }
    {
        pat = "\"" key "\"[ \t\r\n]*:[ \t\r\n]*\""
        if (!match($0, pat)) exit 1
        s = substr($0, RSTART + RLENGTH); out = ""; i = 1; n = length(s)
        while (i <= n) {
            c = substr(s, i, 1)
            if (c == "\\") {
                d = substr(s, i + 1, 1)
                if (d == "n") out = out "\n"
                else if (d == "t") out = out "\t"
                else if (d == "r") out = out "\r"
                else if (d == "u") { out = out "\\u" substr(s, i + 2, 4); i += 4 }
                else out = out d
                i += 2
                continue
            }
            if (c == "\"") { printf "%s", out; found = 1; exit 0 }
            out = out c; i++
        }
        exit 1
    }'
}

start_server() {
    if is_server_running; then
        return 0
    fi

    mkdir -p "$CACHE_DIR"

    # Start server in background, redirect output to log
    nohup "$OLLAMA_BIN" serve >"$SERVE_LOG" 2>&1 &
    local pid=$!
    echo "$pid" > "$SERVE_PID_FILE"

    # Wait up to 10 seconds for server to be ready
    local wait_count=0
    while [[ $wait_count -lt 100 ]]; do
        if is_server_running; then
            return 0
        fi
        sleep 0.1
        ((wait_count++))
    done

    # Server failed to start
    return 1
}

# ============================================================================
# Command: status
# Print loaded models with name, size_vram GB, expires_at.
# Also print usable RAM.
# ============================================================================
cmd_status() {
    echo "=== Loaded Models ==="

    # Fetch running models via /api/ps
    local ps_output
    if ! ps_output=$(curl -s "http://${OLLAMA_API_BASE}/api/ps"); then
        echo "Error: cannot reach Ollama server at ${OLLAMA_API_BASE}"
        return 1
    fi

    # Parse JSON-like output without jq.
    # Expected format: {"models":[{"name":"...", "size_vram":..., "expires_at":"..."}]}
    # Use awk to extract fields manually

    # Parse JSON using sed and awk (no jq, no python)
    # Split on },{ to separate model objects, then parse each with sed
    echo "$ps_output" | sed 's/},{/\n/g' | while IFS= read -r obj; do
        # Extract name using sed
        name=$(echo "$obj" | sed -n 's/.*"name":"\([^"]*\)".*/\1/p')
        # Extract size_vram using sed
        size_vram=$(echo "$obj" | sed -n 's/.*"size_vram":\([0-9]*\).*/\1/p')
        # Fallback to size if size_vram is empty
        if [[ -z "$size_vram" ]]; then
            size_vram=$(echo "$obj" | sed -n 's/.*"size":\([0-9]*\).*/\1/p')
        fi
        # Extract expires_at using sed
        expires=$(echo "$obj" | sed -n 's/.*"expires_at":"\([^"]*\)".*/\1/p')

        # Print if we have name and expires
        if [[ -n "$name" && -n "$expires" ]]; then
            if [[ -n "$size_vram" ]]; then
                size_gb=$(echo "scale=2; $size_vram / 1073741824" | bc)
            else
                size_gb="0.00"
            fi
            printf "%s: %.2f GB, expires_at=%s\n" "$name" "$size_gb" "$expires"
        fi
    done

    echo ""
    echo "=== System RAM ==="
    local ram_gb
    ram_gb=$(get_usable_ram_gb)
    echo "Usable RAM: ${ram_gb} GB"

    # Show recent reaped entries
    if [[ -f "${CACHE_DIR}/reaped.tsv" ]]; then
        echo ""
        echo "=== Recent Reaped Models (use 'resume' to restart) ==="
        tail -5 "${CACHE_DIR}/reaped.tsv" | while IFS=$'\t' read -r epoch model reason args; do
            echo "  $model ($reason)"
            if [[ -n "$args" ]]; then
                echo "    run: ollama-guard run $model $args"
            fi
        done
    fi
}

# ============================================================================
# Command: reap [--idle-min N]
# Unload idle models. Default idle_min=10 minutes.
# Also kill orphaned ollama run processes (PPID=1).
# ============================================================================
cmd_reap() {
    local idle_min=10

    # Parse args
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --idle-min)
                idle_min="$2"
                shift 2
                ;;
            *)
                echo "reap: unknown option $1" >&2
                return 1
                ;;
        esac
    done

    # Fetch running models
    local ps_output
    if ! ps_output=$(curl -s "http://${OLLAMA_API_BASE}/api/ps"); then
        echo "Error: cannot reach Ollama server"
        return 1
    fi

    # Parse each model and check if idle using tr and awk
    echo "$ps_output" | tr ',' '\n' | awk '
    /"name"/ {
        val = $0
        sub(/.*"name":"/, "", val)
        sub(/".*/, "", val)
        name = val
    }
    /"expires_at"/ {
        val = $0
        sub(/.*"expires_at":"/, "", val)
        sub(/".*/, "", val)
        expires = val

        if (name != "") {
            print name "\t" expires
            name = ""
            expires = ""
        }
    }
    ' | while IFS=$'\t' read -r model_name expires_at; do
        # Parse expires_at timestamp (strip fractional seconds and Z/tz offset)
        local ts="${expires_at%.*}"  # Remove .fractional
        ts="${ts%Z}"                  # Remove Z suffix
        ts="${ts%+*}"                 # Remove +HH:MM offset

        local expire_epoch
        if ! expire_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%S" "$ts" +%s 2>/dev/null); then
            echo "reap: warn: unparsable timestamp for model $model_name: $expires_at"
            continue
        fi

        # Compute idle_since and idle duration
        local idle_since=$((expire_epoch - KEEP_ALIVE_MIN * 60))
        local idle_seconds=$((NOW - idle_since))
        local idle_minutes=$((idle_seconds / 60))

        if [[ $idle_minutes -ge $idle_min ]]; then
            echo "reap: unloading idle model: $model_name (idle ${idle_minutes} min)"
            curl -s "http://${OLLAMA_API_BASE}/api/generate" \
                -d "{\"model\":\"$model_name\",\"keep_alive\":0}" \
                >/dev/null 2>&1 || echo "reap: warn: failed to unload $model_name"
            record_reaped "$model_name" "idle"
        fi
    done

    # Kill only orphaned ollama run processes (PPID=1, no live TTY)
    ps aux | awk '/ollama run/ && !/awk/ {print $2}' | while read -r pid; do
        if is_process_orphaned "$pid"; then
            echo "reap: killing orphaned ollama run process: $pid"
            kill "$pid" 2>/dev/null || true
            record_reaped "orphan:$pid" "orphan"
        fi
    done
}

# ============================================================================
# Command: run <model> [args...]
# Reap idle models first, ensure server is up, check RAM, then exec model.
# ============================================================================
cmd_run() {
    if [[ $# -lt 1 ]]; then
        echo "run: model name required" >&2
        return 1
    fi

    local model_name="$1"
    shift
    local model_args=("$@")

    # Step 1: Reap idle models
    cmd_reap --idle-min 5 >/dev/null 2>&1 || true

    # Step 2: Ensure server is running
    if ! start_server; then
        echo "Error: failed to start Ollama server" >&2
        return 1
    fi

    # Step 3: Get model size via 'ollama list'
    # Format: NAME ID SIZE UNIT MODIFIED...
    # where SIZE might be "7.0" and UNIT is "GB" or "MB"
    local model_size_gb
    model_size_gb=$("$OLLAMA_BIN" list 2>/dev/null | awk -v model="$model_name" '
        NR > 1 && ($1 == model || $1 == model ":latest") {
            # SIZE is $3, UNIT is $4
            size_val = $3
            size_unit = $4

            if (size_unit ~ /GB/) {
                print size_val
                exit
            } else if (size_unit ~ /MB/) {
                printf "%.2f\n", size_val / 1024
                exit
            }
        }
    ') || model_size_gb=""

    if [[ -z "$model_size_gb" ]]; then
        echo "Error: cannot determine size for model $model_name" >&2
        return 1
    fi

    # Step 4: Check available RAM
    local usable_ram_gb
    usable_ram_gb=$(get_usable_ram_gb)

    local required_ram_gb
    required_ram_gb=$(echo "scale=2; $model_size_gb * 1.25 + 1" | bc)

    if (( $(echo "$usable_ram_gb < $required_ram_gb" | bc -l) )); then
        # Not enough RAM. Try unloading all other models.
        echo "Insufficient RAM: need ${required_ram_gb} GB, have ${usable_ram_gb} GB"
        echo "Unloading all other models..."

        curl -s "http://${OLLAMA_API_BASE}/api/ps" | tr ',' '\n' | awk '
        /"name"/ {
            val = $0
            sub(/.*"name":"/, "", val)
            sub(/".*/, "", val)
            if (val != "") print val
        }
        ' | while read -r loaded_model; do
            if [[ "$loaded_model" != "$model_name" ]]; then
                curl -s "http://${OLLAMA_API_BASE}/api/generate" \
                    -d "{\"model\":\"$loaded_model\",\"keep_alive\":0}" \
                    >/dev/null 2>&1 || true
                record_reaped "$loaded_model" "make-room"
            fi
        done

        # Recheck RAM
        usable_ram_gb=$(get_usable_ram_gb)
        if (( $(echo "$usable_ram_gb < $required_ram_gb" | bc -l) )); then
            echo "Error: insufficient RAM after unloading other models" >&2
            echo "Need: ${required_ram_gb} GB, Have: ${usable_ram_gb} GB" >&2
            return 2
        fi
    fi

    # Step 5: Check if running interactively
    local args_str="${model_args[*]+${model_args[*]}}"
    record_launch "$model_name" "$args_str"

    # If stdin is a tty, run interactively with exec
    if [[ -t 0 ]]; then
        exec "$OLLAMA_BIN" run "$model_name" ${model_args[@]+"${model_args[@]}"}
    else
        # Non-interactive mode: read prompt from stdin and POST to API
        local prompt
        prompt=$(cat)

        # JSON-escape the prompt
        local escaped_prompt
        escaped_prompt=$(json_escape "$prompt")

        # POST to /api/generate with stream=false
        local response
        response=$(curl -s "http://${OLLAMA_API_BASE}/api/generate" \
            -d "{\"model\":\"$model_name\",\"prompt\":\"$escaped_prompt\",\"stream\":false,\"options\":{\"num_ctx\":$OLLAMA_GUARD_NUM_CTX}}" \
            2>/dev/null) || {
            echo "Error: failed to reach Ollama API" >&2
            return 1
        }

        # An API error comes back as {"error":"..."}: report it and fail.
        local api_error
        if api_error=$(printf '%s' "$response" | json_string_field error); then
            echo "Error: Ollama API: ${api_error}" >&2
            return 1
        fi

        # Extract the "response" field (escape-aware, no jq)
        local extracted
        if ! extracted=$(printf '%s' "$response" | json_string_field response); then
            echo "Error: no response field in Ollama API reply" >&2
            return 1
        fi

        printf '%s\n' "$extracted"
        return 0
    fi
}

# ============================================================================
# Command: stop
# Unload all models and stop the server if we started it.
# ============================================================================
cmd_stop() {
    echo "stop: unloading all models..."

    curl -s "http://${OLLAMA_API_BASE}/api/ps" | tr ',' '\n' | awk '
    /"name"/ {
        val = $0
        sub(/.*"name":"/, "", val)
        sub(/".*/, "", val)
        if (val != "") print val
    }
    ' | while read -r model; do
        curl -s "http://${OLLAMA_API_BASE}/api/generate" \
            -d "{\"model\":\"$model\",\"keep_alive\":0}" \
            >/dev/null 2>&1 || true
    done

    # Stop server if we started it
    if [[ -f "$SERVE_PID_FILE" ]]; then
        local serve_pid
        serve_pid=$(cat "$SERVE_PID_FILE")
        # Kill only a live process whose command is ollama; a stale pid file
        # may name a reused PID that belongs to an unrelated process.
        local serve_comm=""
        if [[ "$serve_pid" =~ ^[0-9]+$ ]] && kill -0 "$serve_pid" 2>/dev/null; then
            serve_comm=$(ps -p "$serve_pid" -o comm= 2>/dev/null || true)
        fi
        if [[ "$(basename "${serve_comm:-none}")" == ollama* ]]; then
            echo "stop: killing Ollama server (PID $serve_pid)"
            kill "$serve_pid" 2>/dev/null || true
        else
            echo "stop: stale pid file (PID $serve_pid is not ollama); not killing"
        fi
        rm -f "$SERVE_PID_FILE"
    fi
}

# ============================================================================
# Command: resume [model]
# Re-launch the most recent reaped model (or specific model if named).
# Removes the entry from reaped.tsv once relaunched.
# ============================================================================
cmd_resume() {
    local target_model="${1:-}"
    local reaped_file="${CACHE_DIR}/reaped.tsv"

    if [[ ! -f "$reaped_file" ]]; then
        echo "resume: no reaped models to resume" >&2
        return 1
    fi

    # Find the target entry (most recent if no model specified)
    local entry
    if [[ -z "$target_model" ]]; then
        # Most recent entry
        entry=$(tail -1 "$reaped_file")
    else
        # Most recent entry for the specified model
        entry=$(tac "$reaped_file" 2>/dev/null | grep "^[^[:space:]]*	$target_model	" | head -1) || \
        entry=$(grep "^[^[:space:]]*	$target_model	" "$reaped_file" | tail -1)
    fi

    if [[ -z "$entry" ]]; then
        echo "resume: no reaped entry found" >&2
        return 1
    fi

    # Parse the reaped entry: epoch \t model \t reason \t args
    local epoch model reason args
    IFS=$'\t' read -r epoch model reason args <<<"$entry" || {
        echo "resume: malformed reaped entry" >&2
        return 1
    }

    echo "resume: relaunching $model with args: $args"

    # Remove entry BEFORE launching to avoid double-entries if cmd_run fails and is retried
    local tmp_file="${reaped_file}.tmp"
    # Use a pattern that matches even if args is empty (trailing tab) or has content
    if [[ -n "$args" ]]; then
        grep -v "^${epoch}	${model}	${reason}	${args}$" "$reaped_file" > "$tmp_file" || true
    else
        # When args is empty, just match the beginning to skip the exact entry
        grep -v "^${epoch}	${model}	${reason}	" "$reaped_file" > "$tmp_file" || true
    fi
    mv "$tmp_file" "$reaped_file"

    # Re-launch via run command (which does reap + RAM check)
    # exec never returns, so this sets up the launch.
    # If cmd_run returns before exec (error), capture the exit code.
    # Note: we must handle the exit code before set -e causes an exit on non-zero
    local exit_code=0
    if [[ -n "$args" ]]; then
        cmd_run "$model" "$args" || exit_code=$?
    else
        cmd_run "$model" || exit_code=$?
    fi

    # If RAM refused (exit 2), restore the entry so user can retry when RAM available
    if [[ $exit_code -eq 2 ]]; then
        echo "resume: RAM refused, restoring entry for later retry" >&2
        echo -e "${epoch}\t${model}\t${reason}\t${args}" >> "$reaped_file"
        return 2
    fi

    # Other errors: entry already removed, return the error
    if [[ $exit_code -ne 0 ]]; then
        echo "resume: failed to relaunch $model (exit $exit_code)" >&2
        return "$exit_code"
    fi

    # If we get here, cmd_run succeeded (exec was called and process replaced)
    # The entry is already removed, and process is now ollama
    return 0
}

# ============================================================================
# Command: help
# ============================================================================
cmd_help() {
    cat <<'EOF'
ollama-guard: deterministic local Ollama management

Usage:
  ollama-guard status                    Show loaded models and usable RAM
  ollama-guard reap [--idle-min N]       Unload idle models (default: 10 min)
  ollama-guard run <model> [args...]     Run a model (checks RAM, reaps idle first)
  ollama-guard resume [model]            Re-launch most recent reaped model
  ollama-guard stop                      Unload all and stop server
  ollama-guard help                      Show this help

Environment:
  OLLAMA_GUARD_KEEP_ALIVE_MIN           Keep-alive timeout in minutes (default: 5)
  OLLAMA_GUARD_NOW                      Override current time (epoch, for testing)

Exit codes:
  0   Success
  1   Error or usage issue
  2   Insufficient RAM

Idle Rule:
  A model is idle after: now - (expires_at - KEEP_ALIVE_MIN) >= idle_min_seconds

RAM Fit Rule:
  Model requires: size_gb * 1.25 + 1 GB of usable RAM
  If insufficient, all other models are unloaded before attempting run.

Session & Chat History:
  Unloading a model (via reap or run's make-room) loses nothing server-side.
  But chat history lives in the 'ollama run' client process; killing an orphan
  client loses that history unless it was saved with '/save <name>' inside the chat.
  Then 'resume <name>' will restore the named session.

  resume never kills clients with live parents/TTY — only orphans (PPID=1).

Note:
  ollama-guard only kills servers it started.
  Running models are unloaded via keep_alive=0 (immediate unload).
EOF
}

# ============================================================================
# Main
# ============================================================================
main() {
    if [[ $# -lt 1 ]]; then
        cmd_help >&2
        return 1
    fi

    case "$1" in
        status)
            shift
            cmd_status "$@"
            ;;
        reap)
            shift
            cmd_reap "$@"
            ;;
        run)
            shift
            cmd_run "$@"
            ;;
        resume)
            shift
            cmd_resume "$@"
            ;;
        stop)
            shift
            cmd_stop "$@"
            ;;
        help)
            cmd_help
            ;;
        *)
            echo "Error: unknown command $1" >&2
            cmd_help >&2
            return 1
            ;;
    esac
}

main "$@"
