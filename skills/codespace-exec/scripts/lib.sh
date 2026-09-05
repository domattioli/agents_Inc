#!/usr/bin/env bash

readonly CODESPACE_NAME="super-duper-fortnight-6r44v6jwxjrhr5x5"
readonly STATE_DIR="$HOME/.codespace-exec"
readonly STATE_FILE="$STATE_DIR/state"
readonly CODESPACE_TIMEOUT_STATUS=124
CODESPACE_CONNECT_TIMEOUT="${CODESPACE_CONNECT_TIMEOUT:-120}"
CODESPACE_EXEC_TIMEOUT="${CODESPACE_EXEC_TIMEOUT:-600}"

shell_quote() {
  local value="$1"
  value=${value//\'/\'\\\'\'}
  printf "'%s'" "$value"
}

build_remote_command() {
  local remote_dir="$1"
  shift
  local result arg

  result="cd $(shell_quote "$remote_dir") && {"
  for arg in "$@"; do
    result+=" $(shell_quote "$arg")"
  done
  result+="; csexit=\$?; printf '\\n__CSEXIT__%d\\n' \"\$csexit\"; }"
  printf '%s' "$result"
}

capture_remote_stdout() {
  local status_file="$1" line previous="" have_previous=false

  while IFS= read -r line; do
    if [[ "$have_previous" == true ]]; then
      printf '%s\n' "$previous"
    fi
    previous="$line"
    have_previous=true
  done

  if [[ "$have_previous" == true && "$previous" =~ ^__CSEXIT__([0-9]+)$ ]]; then
    printf '%s\n' "${BASH_REMATCH[1]}" > "$status_file"
  elif [[ "$have_previous" == true ]]; then
    printf '%s\n' "$previous"
  fi
}

resolve_remote_status() {
  local status_file="$1" gh_status="$2" remote_status

  if [[ -s "$status_file" ]]; then
    remote_status=$(<"$status_file")
    if [[ "$remote_status" =~ ^[0-9]+$ ]]; then
      printf '%s\n' "$remote_status"
      return 0
    fi
  fi
  if [[ "$gh_status" -ne 0 ]]; then
    printf '%s\n' "$gh_status"
    return 0
  fi

  echo "error: remote status could not be determined (completion sentinel missing)" >&2
  return 1
}

parse_exec_args() {
  REQUESTED_DIR=""
  INVALIDATE_CACHE=false
  EXEC_COMMAND=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dir)
        [[ $# -ge 2 ]] || { echo "error: --dir requires a path" >&2; return 2; }
        REQUESTED_DIR="$2"
        shift 2
        ;;
      --invalidate-cache)
        INVALIDATE_CACHE=true
        shift
        ;;
      --)
        shift
        EXEC_COMMAND=("$@")
        break
        ;;
      *)
        echo "error: unknown argument before --: $1" >&2
        return 2
        ;;
    esac
  done

  [[ ${#EXEC_COMMAND[@]} -gt 0 ]] || {
    echo "usage: exec.sh [--dir PATH] [--invalidate-cache] -- <command> [args...]" >&2
    return 2
  }
}

run_with_timeout() {
  local limit="$1"
  shift
  local timeout_command="" child_pid watchdog_pid status marker

  if command -v timeout >/dev/null 2>&1; then
    timeout_command=timeout
  elif command -v gtimeout >/dev/null 2>&1; then
    timeout_command=gtimeout
  fi
  if [[ -n "$timeout_command" ]]; then
    "$timeout_command" "$limit" "$@"
    return $?
  fi

  marker=$(mktemp "${TMPDIR:-/tmp}/codespace-timeout.XXXXXX")
  rm -f "$marker"
  set -m
  "$@" &
  child_pid=$!
  set +m
  (
    sleep "$limit"
    if kill -0 "$child_pid" 2>/dev/null; then
      : > "$marker"
      kill -TERM -- "-$child_pid" 2>/dev/null || true
      kill -TERM "$child_pid" 2>/dev/null || true
      sleep 1
      kill -KILL -- "-$child_pid" 2>/dev/null || true
      kill -KILL "$child_pid" 2>/dev/null || true
    fi
  ) >/dev/null 2>&1 &
  watchdog_pid=$!
  if wait "$child_pid"; then
    status=0
  else
    status=$?
  fi
  kill "$watchdog_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true
  if [[ -e "$marker" ]]; then
    rm -f "$marker"
    return "$CODESPACE_TIMEOUT_STATUS"
  fi
  rm -f "$marker"
  return "$status"
}

codespace_ssh() {
  local status
  set +e
  run_with_timeout "$CODESPACE_CONNECT_TIMEOUT" \
    gh codespace ssh -c "$CODESPACE_NAME" -- true >/dev/null
  status=$?
  set -e
  if [[ "$status" -eq "$CODESPACE_TIMEOUT_STATUS" ]]; then
    echo "error: Codespace connection/startup timeout after ${CODESPACE_CONNECT_TIMEOUT}s" >&2
    return "$CODESPACE_TIMEOUT_STATUS"
  fi
  if [[ "$status" -ne 0 ]]; then
    return "$status"
  fi

  set +e
  run_with_timeout "$CODESPACE_EXEC_TIMEOUT" \
    gh codespace ssh -c "$CODESPACE_NAME" -- "$1"
  status=$?
  set -e
  if [[ "$status" -eq "$CODESPACE_TIMEOUT_STATUS" ]]; then
    echo "error: Codespace remote command timeout after ${CODESPACE_EXEC_TIMEOUT}s (completion sentinel missing)" >&2
  fi
  return "$status"
}

write_cached_path() {
  mkdir -p "$STATE_DIR"
  chmod 700 "$STATE_DIR"
  printf '%s\n' "$1" > "$STATE_FILE"
  chmod 600 "$STATE_FILE"
}

resolve_repository_path() {
  local requested_dir="${1:-}" candidate candidates_output
  local -a candidates=()

  if [[ -n "$requested_dir" ]]; then
    if [[ "$requested_dir" == /workspaces/* ]]; then
      candidate="$requested_dir"
    elif [[ "$requested_dir" == /* ]]; then
      echo "error: --dir must name a directory under /workspaces" >&2
      return 20
    else
      candidate="/workspaces/$requested_dir"
    fi
    if ! codespace_ssh "test -d $(shell_quote "$candidate")"; then
      echo "error: remote repository directory not found: $candidate" >&2
      return 21
    fi
    write_cached_path "$candidate"
    printf '%s\n' "$candidate"
    return 0
  fi

  if [[ -s "$STATE_FILE" ]]; then
    IFS= read -r candidate < "$STATE_FILE"
    if [[ "$candidate" == /workspaces/* ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi

  if ! candidates_output=$(codespace_ssh \
    "find /workspaces -mindepth 1 -maxdepth 1 -type d ! -name '.*' -print"); then
    echo "error: could not list repository directories in /workspaces" >&2
    return 22
  fi

  while IFS= read -r candidate; do
    [[ -z "$candidate" || "${candidate##*/}" == .* ]] && continue
    candidates+=("$candidate")
  done <<< "$candidates_output"

  if [[ ${#candidates[@]} -eq 0 ]]; then
    echo "error: no repository directory found under /workspaces" >&2
    return 23
  fi
  if [[ ${#candidates[@]} -gt 1 ]]; then
    echo "error: multiple directories found under /workspaces; rerun with --dir PATH" >&2
    printf '  %s\n' "${candidates[@]}" >&2
    return 24
  fi

  write_cached_path "${candidates[0]}"
  printf '%s\n' "${candidates[0]}"
}
