#!/usr/bin/env bash
# Liveness poll for a running delegate. Token-smart by construction: it
# reports STATE, never content. One short line per state CHANGE, nothing on
# a tick where nothing changed.
#
#   poll.sh --pid-match <pattern> --log <file> [--out <file>] [--stall N] [--interval N] [--max N]
#   poll.sh --once ...        single check, print one line, exit
#
# States, and the only things it ever prints:
#   RUNNING   first confirmation the job is alive
#   QUIET     no log growth for --stall seconds; job still alive
#   RESUMED   growth returned after a QUIET
#   DONE      process gone, output produced
#   DIED      process gone, no output          <- the one that matters
#   TIMEOUT   --max exceeded, job still alive
#
# Why state-only: piping a delegate's log into the supervisor's context
# costs the tokens delegation was meant to save. The supervisor needs to
# know THAT it is working, not WHAT it is saying. Read the output once, at
# the end. To actually watch, use watch.sh in another pane — that stream
# goes to a human's eyes, not into a context window.
set -uo pipefail

PAT=""; LOG=""; OUT=""; STALL=480; INTERVAL=60; MAX=7200; ONCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --pid-match) PAT="${2:-}"; shift 2 ;;
    --log)       LOG="${2:-}"; shift 2 ;;
    --out)       OUT="${2:-}"; shift 2 ;;
    --stall)     STALL="${2:-}"; shift 2 ;;
    --interval)  INTERVAL="${2:-}"; shift 2 ;;
    --max)       MAX="${2:-}"; shift 2 ;;
    --once)      ONCE=1; shift ;;
    -h|--help)   sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[ -n "$PAT" ] && [ -n "$LOG" ] || { echo "need --pid-match and --log" >&2; exit 2; }

mtime() { [ -f "$1" ] && stat -f %m "$1" 2>/dev/null || echo 0; }
fsize() { [ -f "$1" ] && stat -f %z "$1" 2>/dev/null || echo 0; }
alive() { pgrep -f "$PAT" >/dev/null 2>&1; }

# Non-empty stdout is the honest completion signal. A job whose process is
# gone and whose output is empty did not finish quietly — it died.
produced() { [ -n "$OUT" ] && [ "$(fsize "$OUT")" -gt 0 ]; }

START=$(date +%s)
state=""
emit() { # only ever fires on a change
  [ "$1" = "$state" ] && return 0
  state="$1"; shift
  echo "[$(date -u +%H:%M:%SZ)] $state${*:+ — $*}"
}

if [ "$ONCE" -eq 1 ]; then
  if alive; then
    age=$(( $(date +%s) - $(mtime "$LOG") ))
    [ "$age" -ge "$STALL" ] && echo "QUIET — alive, no log growth ${age}s" \
                            || echo "RUNNING — alive, last growth ${age}s ago"
  else
    produced && echo "DONE — process gone, $(fsize "$OUT") bytes of output" \
              || echo "DIED — process gone, no output"
  fi
  exit 0
fi

alive && emit RUNNING "watching \"$PAT\""

while :; do
  now=$(date +%s)
  if ! alive; then
    produced && emit DONE "$(fsize "$OUT") bytes of output after $(( (now-START)/60 )) min" \
              || emit DIED "no output after $(( (now-START)/60 )) min — check the log"
    exit 0
  fi
  age=$(( now - $(mtime "$LOG") ))
  if [ "$age" -ge "$STALL" ]; then
    emit QUIET "alive but no log growth for ${age}s"
  elif [ "$state" = "QUIET" ]; then
    # RESUMED is only meaningful after a QUIET. Announcing it on a healthy
    # first pass is noise, and noise is what makes an operator stop reading.
    emit RESUMED "log growing again"
    state=RUNNING            # so a later stall can fire QUIET again
  fi
  if [ $(( now - START )) -ge "$MAX" ]; then
    emit TIMEOUT "still alive after $(( (now-START)/60 )) min — decide manually"
    exit 0
  fi
  sleep "$INTERVAL"
done
