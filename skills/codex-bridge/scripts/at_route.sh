#!/usr/bin/env bash
# at_route.sh - UserPromptSubmit hook. Routes "@<alias> <question>" to a cheap model.
# Stdout becomes extra context for the main model. Always exits 0.
set -euo pipefail

[[ "${AT_ROUTE_ACTIVE:-}" == "1" ]] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${AT_ROUTE_LOG:-$HOME/.codex-bridge/at_route.log}"
TIMEOUT_S="${AT_ROUTE_TIMEOUT:-120}"

input="$(cat)"
prompt="$(printf '%s' "$input" | jq -r '.prompt // empty' 2>/dev/null || true)"
[[ -z "$prompt" ]] && exit 0

# Escape: ~@ prefix → exit 0, pass prompt to session model untouched
[[ "$prompt" =~ ^~@ ]] && exit 0

shopt -s nocasematch
re='^(@@?)(haiku|sonnet|opus|fable|astra|sol|terra|luna)[[:space:]]+(.+)$'
if [[ ! "$prompt" =~ $re ]]; then
  exit 0
fi
prefix="${BASH_REMATCH[1]}"
alias_name="$(printf '%s' "${BASH_REMATCH[2]}" | tr '[:upper:]' '[:lower:]')"
question="${BASH_REMATCH[3]}"
shopt -u nocasematch

kind="claude"
case "$alias_name" in
  haiku)  model="claude-haiku-4-5-20251001" ;;
  sonnet) model="claude-sonnet-5" ;;
  opus)   model="claude-opus-5-5" ;;
  fable)  model="claude-fable-5-1" ;;
  astra)  model="gpt-6-astra"; kind="codex" ;;
  sol)    model="gpt-5.6-sol"; kind="codex" ;;
  terra)  model="gpt-5.6-terra"; kind="codex" ;;
  luna)   model="gpt-5.6-luna"; kind="codex" ;;
  *) exit 0 ;;
esac

out_f="$(mktemp -t at_route_out.XXXXXX)"
err_f="$(mktemp -t at_route_err.XXXXXX)"
trap 'rm -f "$out_f" "$err_f"' EXIT

# Portable timeout: perl alarm survives exec, SIGALRM kills the child.
run_with_timeout() {
  perl -e 'alarm shift @ARGV; exec @ARGV or die "exec failed: $!\n"' "$TIMEOUT_S" "$@"
}

start=$SECONDS
rc=0
if [[ "$kind" == "claude" ]]; then
  AT_ROUTE_ACTIVE=1 run_with_timeout claude -p "$question" --model "$model" \
    >"$out_f" 2>"$err_f" </dev/null || rc=$?
else
  # submit --wait prints job metadata; the answer text comes from `agent.sh result <id>`.
  AT_ROUTE_ACTIVE=1 run_with_timeout "$SCRIPT_DIR/agent.sh" submit --backend codex \
    --model "$model" --wait "$question" >"$out_f" 2>"$err_f" </dev/null || rc=$?
  if [[ "$rc" -eq 0 ]]; then
    job_id="$(awk -F': ' '/^id: /{print $2; exit}' "$out_f")"
    if [[ -n "$job_id" ]]; then
      AT_ROUTE_ACTIVE=1 "$SCRIPT_DIR/agent.sh" result "$job_id" >"$out_f" 2>>"$err_f" </dev/null || rc=$?
    else
      rc=1; echo "no job id in submit output" >>"$err_f"
    fi
  fi
fi
elapsed=$((SECONDS - start))

{
  mkdir -p "$(dirname "$LOG_FILE")" &&
    printf '%s\t%s\t%s\t%ss\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$alias_name" "$rc" "$elapsed" >>"$LOG_FILE"
} 2>/dev/null || true

if [[ "$rc" -eq 0 ]]; then
  # Exit 2 blocks the prompt: the main model never runs, stderr is shown to the
  # operator, and nothing enters the conversation. Zero main-model cost.
  # @@ prefix or AT_ROUTE_MODE=relay injects the answer as context (relay mode).
  mode="block"
  [[ "$prefix" == "@@" ]] && mode="relay"
  [[ "${AT_ROUTE_MODE:-}" == "relay" && "$mode" != "relay" ]] && mode="relay"
  if [[ "$mode" == "relay" ]]; then
    echo "[at_route] Answer from delegate ${alias_name} (${model}) below. Begin your reply with the literal prefix \"${alias_name} ▸ \" and then relay the answer verbatim. Do not re-answer, do not reason, do not add commentary."
    echo "---"
    cat "$out_f"
    echo "---"
    exit 0
  fi
  {
    # AT_ROUTE_COLOR=1 wraps the box in ANSI cyan; experimental, depends on
    # whether Claude Code passes escape codes from hook stderr through.
    c=""; r=""
    if [[ "${AT_ROUTE_COLOR:-0}" == "1" ]]; then c=$'\033[36m'; r=$'\033[0m'; fi
    printf '%s┌─ %s (%s) · %ss ─%s\n' "$c" "$alias_name" "$model" "$elapsed" "$r"
    sed "s/^/${c}│ /; s/\$/${r}/" "$out_f"
    printf '%s└─%s\n' "$c" "$r"
  } >&2
  exit 2
else
  echo "[at_route] ${alias_name} call failed (exit ${rc}). Stderr:"
  echo '```'
  cat "$err_f"
  echo '```'
  echo "Answer the operator's question yourself."
fi
exit 0
