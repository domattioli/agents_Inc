#!/usr/bin/env bash
# Live view of a running delegate. Read-only. Safe to start, stop, restart
# at any time — it never touches the job it is watching.
#
#   watch.sh <logfile>        follow one job's stream
#   watch.sh --raw <logfile>  no filtering, everything
#   watch.sh --list           recent job logs under ~/.codex-bridge/jobs
#
# Why this exists: a delegate that runs for ten minutes with no output is
# indistinguishable from a delegate that has hung. Watching is also the
# only progress signal available to an operator who cannot read a test.
set -uo pipefail

JOBS_DIR="${CODEX_BRIDGE_JOBS:-$HOME/.codex-bridge/jobs}"
RAW=0

usage() { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

case "${1:-}" in
  -h|--help) usage 0 ;;
  --list)
    [ -d "$JOBS_DIR" ] || { echo "no jobs dir: $JOBS_DIR"; exit 1; }
    ls -t "$JOBS_DIR"/*/stderr.log "$JOBS_DIR"/*/stdout.log 2>/dev/null | head -20
    exit 0 ;;
  --raw) RAW=1; shift ;;
esac

LOG="${1:-}"
[ -n "$LOG" ] || usage 2
[ -f "$LOG" ] || { echo "not a file: $LOG" >&2; exit 1; }

echo "watching $LOG  (ctrl-c to stop; the job keeps running)"
echo "----------------------------------------------------------------"

if [ "$RAW" -eq 1 ]; then
  exec tail -f -n 40 "$LOG"
fi

# Filtered view: the lines that say what the delegate is DOING, plus every
# failure signature. Silence must not be able to hide a crash, so the
# failure half of this alternation is deliberately wide.
exec tail -f -n 40 "$LOG" | grep -aE --line-buffered \
  -e '^(exec|codex|web search|thinking|tokens used)' \
  -e '^(model|sandbox|reasoning effort|workdir):' \
  -e 'succeeded in|failed in|exited with' \
  -e 'error|Error|ERROR|Traceback|refused|REFUSED|denied|blocked|timed out|not permitted' \
  -e 'API error|rate.?limit|429|401|503|quota|capacity'
