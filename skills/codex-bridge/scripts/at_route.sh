#!/usr/bin/env bash
# at_route.sh - UserPromptSubmit hook. Routes "@<alias> <question>" to a cheap model.
# Stdout becomes extra context for the main model. Always exits 0.
set -euo pipefail

[[ "${AT_ROUTE_ACTIVE:-}" == "1" ]] && exit 0
command -v jq >/dev/null 2>&1 || exit 0

# Resolve symlinks (~/.local/bin/@luna -> this file) so agent.sh is found.
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
LOG_FILE="${AT_ROUTE_LOG:-$HOME/.codex-bridge/at_route.log}"
TIMEOUT_S="${AT_ROUTE_TIMEOUT:-120}"

# CLI mode: invoked as "@luna <question>" (symlink named after the alias) or
# "at_route.sh luna <question>". Used with Claude Code's "!" prefix:
#   ! @luna say hi
# Output goes to stdout, exit 0, no hook framing, no model turn.
CLI=0
if [[ $# -gt 0 ]]; then
  CLI=1
  self="$(basename "${BASH_SOURCE[0]}")"
  if [[ "$self" == @* ]]; then
    prompt="${self} $*"
  else
    prompt="@$1 ${*:2}"
  fi
else
  input="$(cat)"
  prompt="$(printf '%s' "$input" | jq -r '.prompt // empty' 2>/dev/null || true)"
fi
[[ -z "$prompt" ]] && exit 0

# Escape: ~@ prefix → exit 0, pass prompt to session model untouched
[[ "$prompt" =~ ^~@ ]] && exit 0

shopt -s nocasematch
re='^(@@?)(haiku|sonnet|opus|fable|astra|sol|terra|luna|gemini|mistral)[[:space:]]+(.+)$'
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
  gemini) model="gemini-3.8-flash"; kind="gemini" ;;
  mistral) model="codestral-latest"; kind="mistral" ;;
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
elif [[ "$kind" == "gemini" ]]; then
  AT_ROUTE_ACTIVE=1 run_with_timeout "$SCRIPT_DIR/gask.sh" --tier digest "$question" \
    >"$out_f" 2>"$err_f" </dev/null || rc=$?
  # gask.sh prints upstream errors on stdout with exit 0
  if [[ "$rc" -eq 0 ]] && grep -q '^gemini error' "$out_f"; then rc=1; cat "$out_f" >>"$err_f"; fi
elif [[ "$kind" == "mistral" ]]; then
  AT_ROUTE_ACTIVE=1 run_with_timeout "$SCRIPT_DIR/mask.sh" --tier code "$question" \
    >"$out_f" 2>"$err_f" </dev/null || rc=$?
else
  # Fresh thread per question. The persistent agent.sh thread accumulated
  # 442k input tokens per call by the 6th question (measured 2026-09-23);
  # --fresh costs ~26k (Codex system prompt) instead.
  AT_ROUTE_ACTIVE=1 run_with_timeout "$SCRIPT_DIR/ask.sh" --fresh --raw \
    --model "$model" "$question" >"$out_f" 2>"$err_f" </dev/null || rc=$?
  if [[ "$rc" -eq 0 ]]; then
    resp="$(jq -r '.response // empty' "$out_f" 2>/dev/null || true)"
    if [[ -n "$resp" ]]; then
      printf '%s\n' "$resp" >"$out_f"
    else
      rc=1; echo "no .response in ask.sh output" >>"$err_f"
    fi
  fi
fi
elapsed=$((SECONDS - start))

{
  mkdir -p "$(dirname "$LOG_FILE")" &&
    printf '%s\t%s\t%s\t%ss\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$alias_name" "$rc" "$elapsed" >>"$LOG_FILE"
} 2>/dev/null || true

# Every answer is also appended to a transcript, because Claude Code shows
# hook stderr only between turns: a block-mode prompt sent mid-turn would
# otherwise be lost. Read it with: tail -20 ~/.codex-bridge/at_route_answers.log
ANS_LOG="${AT_ROUTE_ANSWERS:-${LOG_FILE%/*}/at_route_answers.log}"
if [[ "$rc" -eq 0 ]]; then
  {
    printf '\n=== %s %s (%s) %ss\nQ: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$alias_name" "$model" "$elapsed" "$question"
    cat "$out_f"
  } >>"$ANS_LOG" 2>/dev/null || true
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
    # ANSI cyan box, on by default. Claude Code passes hook stderr escapes through
    # (verified 2026-09-23). AT_ROUTE_COLOR=0 disables.
    c=""; r=""
    if [[ "${AT_ROUTE_COLOR:-1}" == "1" ]]; then c=$'\033[36m'; r=$'\033[0m'; fi
    printf '%s┌─ %s (%s) · %ss ─%s\n' "$c" "$alias_name" "$model" "$elapsed" "$r"
    sed "s/^/${c}│ /; s/\$/${r}/" "$out_f"
    printf '%s└─%s\n' "$c" "$r"
  } > >(if [[ "$CLI" == 1 ]]; then cat; else cat >&2; fi)
  wait
  [[ "$CLI" == 1 ]] && exit 0
  exit 2
else
  echo "[at_route] ${alias_name} call failed (exit ${rc}). Stderr:"
  echo '```'
  cat "$err_f"
  echo '```'
  echo "Answer the operator's question yourself."
fi
exit 0
