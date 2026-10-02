#!/usr/bin/env bash
# Smoke test for at_route.sh. Never calls a real model: claude is stubbed on PATH.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$HERE/../scripts/at_route.sh"
TMP="$(mktemp -d -t at_route_smoke.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
export AT_ROUTE_LOG="$TMP/at_route.log"
export AT_ROUTE_ANSWERS="$TMP/answers.log"
unset AT_ROUTE_ACTIVE
pass=0; total=26

ok()   { echo "PASS $1"; pass=$((pass + 1)); }
fail() { echo "FAIL $1: $2"; }

mkstub() { # $1 = dir, $2 = exit code
  mkdir -p "$1"
  printf '#!/bin/sh\ntouch "%s/called.txt"\necho STUB-OK\necho stub-stderr >&2\nexit %s\n' "$1" "$2" >"$1/claude"
  chmod +x "$1/claude"
}

# (a) non-@ prompt
out="$(echo '{"prompt":"hello there"}' | bash "$HOOK")"; rc=$?
[[ $rc -eq 0 && -z "$out" ]] && ok "a non-@ prompt" || fail a "rc=$rc out=$out"

# (b) recursion guard
out="$(echo '{"prompt":"@haiku hi"}' | AT_ROUTE_ACTIVE=1 bash "$HOOK")"; rc=$?
[[ $rc -eq 0 && -z "$out" ]] && ok "b AT_ROUTE_ACTIVE guard" || fail b "rc=$rc out=$out"

# (c) jq missing: PATH holds only an empty dir
mkdir -p "$TMP/empty"
out="$(echo '{"prompt":"@haiku hi"}' | PATH="$TMP/empty" /bin/bash "$HOOK")"; rc=$?
[[ $rc -eq 0 && -z "$out" ]] && ok "c jq missing" || fail c "rc=$rc out=$out"

# (d) stub success
mkstub "$TMP/ok" 0
# block mode (default): answer on stderr, exit 2, stdout empty
err="$(echo '{"prompt":"@Haiku what is 2+2"}' | PATH="$TMP/ok:$PATH" bash "$HOOK" 2>&1 >/dev/null)"; rc=$?
out="$(echo '{"prompt":"@Haiku what is 2+2"}' | PATH="$TMP/ok:$PATH" bash "$HOOK" 2>/dev/null)"
if [[ $rc -eq 2 && -z "$out" && "$err" == *"┌─ haiku (claude-haiku-4-5-20251001)"* && "$err" == *"│ STUB-OK"* && "$err" == *"└─"* ]]; then
  ok "d stub success (block)"; else fail d "rc=$rc out=$out err=$err"; fi

# relay mode: answer on stdout, exit 0
out="$(echo '{"prompt":"@Haiku what is 2+2"}' | AT_ROUTE_MODE=relay PATH="$TMP/ok:$PATH" bash "$HOOK")"; rc=$?
if [[ $rc -eq 0 && "$out" == *STUB-OK* && "$out" == *"[at_route] Answer from delegate haiku (claude-haiku-4-5-20251001)"* && "$out" == *"haiku ▸"* ]]; then
  ok "d2 stub success (relay)"; else fail d2 "rc=$rc out=$out"; fi

# (e) stub exits 3
mkstub "$TMP/bad" 3
out="$(echo '{"prompt":"@haiku hi"}' | PATH="$TMP/bad:$PATH" bash "$HOOK")"; rc=$?
if [[ $rc -eq 0 && "$out" == *"haiku call failed (exit 3)"* && "$out" == *stub-stderr* && "$out" == *"Answer the operator's question yourself."* ]]; then
  ok "e stub failure"; else fail e "rc=$rc out=$out"; fi

# (f) @@ with Claude alias: persistent session route (with AT_ROUTE_PERSIST=1, the default)
# Prove claude stub NOT called: stub writes marker, assert marker absent after test
# Assert stdout contains --allowedTools "Read,Grep,Glob"
rm -f "$TMP/ok/called.txt"
out="$(echo '{"prompt":"@@haiku what is 2+2"}' | PATH="$TMP/ok:$PATH" bash "$HOOK")"; rc=$?
if [[ $rc -eq 0 && "$out" == *"Persistent-session route for @@haiku"* && "$out" == *"at-haiku"* && "$out" == *"claude-haiku-4-5-20251001"* && "$out" == *"what is 2+2"* && "$out" == *'--allowedTools "Read,Grep,Glob"'* && ! -f "$TMP/ok/called.txt" ]]; then
  ok "f @@ persistent session"; else fail f "rc=$rc out=$out marker=$([[ -f "$TMP/ok/called.txt" ]] && echo present || echo absent)"; fi

# (f2) AT_ROUTE_PERSIST=0: @@ uses old relay path with claude -p
out="$(echo '{"prompt":"@@haiku what is 2+2"}' | AT_ROUTE_PERSIST=0 PATH="$TMP/ok:$PATH" bash "$HOOK")"; rc=$?
if [[ $rc -eq 0 && "$out" == *STUB-OK* && "$out" == *"[at_route] Answer from delegate haiku (claude-haiku-4-5-20251001)"* && "$out" == *"haiku ▸"* ]]; then
  ok "f2 @@ with AT_ROUTE_PERSIST=0"; else fail f2 "rc=$rc out=$out"; fi

# (f4) @@haiku /foo rejects slash command: rc 2, stderr contains "does not forward slash commands", no claude stub called
rm -f "$TMP/ok/called.txt"
err="$(echo '{"prompt":"@@haiku /foo"}' | PATH="$TMP/ok:$PATH" bash "$HOOK" 2>&1 >/dev/null)"; rc=$?
if [[ $rc -eq 2 && "$err" == *"does not forward slash commands"* && ! -f "$TMP/ok/called.txt" ]]; then
  ok "f4 @@haiku /foo rejects"; else fail f4 "rc=$rc err=$err marker=$([[ -f "$TMP/ok/called.txt" ]] && echo present || echo absent)"; fi

# (f5) @haiku /foo (single @) still calls stub: rc 2, stderr contains STUB-OK
err="$(echo '{"prompt":"@haiku /foo"}' | PATH="$TMP/ok:$PATH" bash "$HOOK" 2>&1 >/dev/null)"; rc=$?
if [[ $rc -eq 2 && "$err" == *"STUB-OK"* ]]; then
  ok "f5 @haiku /foo calls stub"; else fail f5 "rc=$rc err=$err"; fi

# (g) escape: ~@ prefix exits silently, passes prompt to session model
out="$(echo '{"prompt":"~@haiku literal"}' | PATH="$TMP/ok:$PATH" bash "$HOOK")"; rc=$?
[[ $rc -eq 0 && -z "$out" ]] && ok "g escape ~@" || fail g "rc=$rc out=$out"

# --- spec 013 cases (h-p). Stubs only; no real model calls. ---
# argv-recording claude stub
mkdir -p "$TMP/argv"
cat >"$TMP/argv/claude" <<'STUB'
#!/bin/sh
for a in "$@"; do printf '%s\n' "$a"; done >"$ARGV_FILE"
echo STUB-OK
exit 0
STUB
chmod +x "$TMP/argv/claude"
ro_ok() { # $1 = argv file
  local f="$1"
  grep -qx -- '--tools' "$f" && grep -A1 -x -- '--tools' "$f" | tail -1 | grep -qx 'Read,Grep,Glob' &&
  grep -qx -- '--disallowedTools' "$f" &&
  grep -A1 -x -- '--disallowedTools' "$f" | tail -1 | grep -q Edit &&
  grep -A1 -x -- '--disallowedTools' "$f" | tail -1 | grep -q Write &&
  grep -A1 -x -- '--disallowedTools' "$f" | tail -1 | grep -q Bash &&
  grep -A1 -x -- '--disallowedTools' "$f" | tail -1 | grep -q NotebookEdit &&
  grep -qx -- '--strict-mcp-config' "$f"
}

# (h) read-only restriction on every Claude alias, hook mode
hfail=""
for a in haiku sonnet opus fable; do
  export ARGV_FILE="$TMP/argv/$a.txt"; rm -f "$ARGV_FILE"
  echo "{\"prompt\":\"@$a hi\"}" | PATH="$TMP/argv:$PATH" bash "$HOOK" >/dev/null 2>&1
  ro_ok "$ARGV_FILE" || hfail="$hfail $a"
done
[[ -z "$hfail" ]] && ok "h read-only flags (hook, 4 aliases)" || fail h "missing read-only flags for:$hfail"

# (h2) same restriction in CLI mode
export ARGV_FILE="$TMP/argv/cli.txt"; rm -f "$ARGV_FILE"
PATH="$TMP/argv:$PATH" bash "$HOOK" opus hi >/dev/null 2>&1
ro_ok "$ARGV_FILE" && ok "h2 read-only flags (CLI)" || fail h2 "argv=$(tr '\n' ' ' <"$ARGV_FILE" 2>/dev/null)"

# (i) timeout names itself
mkdir -p "$TMP/slow"
printf '#!/bin/sh\nsleep 3\necho late\n' >"$TMP/slow/claude"; chmod +x "$TMP/slow/claude"
out="$(echo '{"prompt":"@haiku hi"}' | AT_ROUTE_TIMEOUT=1 PATH="$TMP/slow:$PATH" bash "$HOOK" 2>/dev/null)"; rc=$?
if [[ $rc -eq 0 && "$out" == *"timed out after 1s"* && "$out" == *"Partial files may exist"* && "$out" == *"git status"* ]]; then
  ok "i timeout message"; else fail i "rc=$rc out=$out"; fi

# (j) fast non-alarm failure is not called a timeout
out="$(echo '{"prompt":"@haiku hi"}' | PATH="$TMP/bad:$PATH" bash "$HOOK")"; rc=$?
if [[ $rc -eq 0 && "$out" == *"haiku call failed (exit 3)"* && "$out" != *"timed out"* ]]; then
  ok "j non-timeout failure wording"; else fail j "rc=$rc out=$out"; fi

# openrouter: temp copy of the hook beside stub bridge scripts
B="$TMP/bridge"; mkdir -p "$B"
cp "$HOOK" "$B/at_route.sh"; chmod +x "$B/at_route.sh"
printf '#!/bin/sh\nexit 0\n' >"$B/ask.sh"; chmod +x "$B/ask.sh"
mkoask() { # $1 = mode: ok | nomodel | fail | slow
  cat >"$B/oask.sh" <<STUB
#!/bin/sh
printf '%s\n' "\${MODEL-UNSET}" >"$TMP/oask_model.txt"
case "$1" in
  ok) echo OR-ANSWER; echo '[openrouter vendor/model:free | in 1 out 1]' >&2 ;;
  nomodel) echo OR-ANSWER ;;
  fail) echo "oask: REFUSED" >&2; exit 3 ;;
  slow) sleep 3; echo late ;;
esac
STUB
  chmod +x "$B/oask.sh"
}

# (f3) @@gemini (non-Claude): relay mode, no persistent session route
printf '#!/bin/sh\necho GEMINI-STUB\necho gemini-stderr >&2\nexit 0\n' >"$B/gask.sh"; chmod +x "$B/gask.sh"
out="$(echo '{"prompt":"@@gemini what is 2+2"}' | bash "$B/at_route.sh")"; rc=$?
if [[ $rc -eq 0 && "$out" != *"Persistent-session route"* && "$out" == *"GEMINI-STUB"* ]]; then
  ok "f3 @@gemini relay (no persist)"; else fail f3 "rc=$rc out=$out"; fi

# (k) @openrouter header shows the model oask.sh reports
mkoask ok
err="$(echo '{"prompt":"@openrouter hi"}' | bash "$B/at_route.sh" 2>&1 >/dev/null)"; rc=$?
if [[ $rc -eq 2 && "$err" == *"┌─ openrouter (vendor/model:free)"* && "$err" == *"│ OR-ANSWER"* ]]; then
  ok "k openrouter header"; else fail k "rc=$rc err=$err"; fi

# (l) inherited MODEL never reaches oask.sh
rm -f "$TMP/oask_model.txt"
echo '{"prompt":"@openrouter hi"}' | MODEL=openai/gpt-4o-mini bash "$B/at_route.sh" >/dev/null 2>&1
got="$(cat "$TMP/oask_model.txt" 2>/dev/null)"
[[ "$got" == "UNSET" ]] && ok "l MODEL cleared" || fail l "oask saw MODEL=$got"

# (m) oask.sh refusal gives the failover block
mkoask fail
out="$(echo '{"prompt":"@openrouter hi"}' | bash "$B/at_route.sh")"; rc=$?
if [[ $rc -eq 0 && "$out" == *"openrouter call failed (exit 3)"* && "$out" == *"Answer the operator's question yourself."* ]]; then
  ok "m openrouter failover"; else fail m "rc=$rc out=$out"; fi

# (n) @@openrouter relays
mkoask ok
out="$(echo '{"prompt":"@@openrouter hi"}' | bash "$B/at_route.sh")"; rc=$?
if [[ $rc -eq 0 && "$out" == *"[at_route] Answer from delegate openrouter (vendor/model:free)"* && "$out" == *OR-ANSWER* ]]; then
  ok "n @@openrouter relay"; else fail n "rc=$rc out=$out"; fi

# (o) no model line gives "unknown model"
mkoask nomodel
err="$(echo '{"prompt":"@openrouter hi"}' | bash "$B/at_route.sh" 2>&1 >/dev/null)"; rc=$?
[[ $rc -eq 2 && "$err" == *"┌─ openrouter (unknown model)"* ]] && ok "o unknown model header" || fail o "rc=$rc err=$err"

# (p) CLI mode through an @openrouter link, plus timeout on a non-Claude alias
mkoask ok
ln -sf "$B/at_route.sh" "$B/@openrouter"
out="$("$B/@openrouter" hi 2>/dev/null)"; rc=$?
[[ $rc -eq 0 && "$out" == *"┌─ openrouter (vendor/model:free)"* ]] && ok "p CLI @openrouter" || fail p "rc=$rc out=$out"
mkoask slow
out="$(echo '{"prompt":"@openrouter hi"}' | AT_ROUTE_TIMEOUT=1 bash "$B/at_route.sh" 2>/dev/null)"; rc=$?
[[ $rc -eq 0 && "$out" == *"timed out after 1s"* ]] && ok "p2 openrouter timeout" || fail p2 "rc=$rc out=$out"

# --- check-in cases (q-q3) ---
# (q) @haiku /check-in with stubs: rc 2, stderr has CARD-OK, args.txt has prompt with check-in status card + FAKE-REPO + RECENT-MARKER
ck="$TMP/ck"; mkdir -p "$ck"
printf '#!/bin/sh\necho "repo: FAKE-REPO"\n' >"$ck/state.sh"; chmod +x "$ck/state.sh"
cat >"$ck/claude" <<'CLAUDE_STUB'
#!/bin/sh
{
  for arg in "$@"; do
    printf '%s\n' "$arg"
  done
} >"${CK_ARGS_FILE:-/dev/null}"
echo CARD-OK
exit 0
CLAUDE_STUB
chmod +x "$ck/claude"
printf '{"type":"assistant","message":{"content":[{"type":"text","text":"RECENT-MARKER"}]}}\n' >"$ck/t.jsonl"

export CK_ARGS_FILE="$ck/args.txt"
err="$(echo "{\"prompt\":\"@haiku /check-in\",\"transcript_path\":\"$ck/t.jsonl\",\"session_id\":\"S1\",\"cwd\":\"$ck\"}" | AT_ROUTE_CHECKIN_SCRIPT="$ck/state.sh" PATH="$ck:$PATH" bash "$HOOK" 2>&1 >/dev/null)"; rc=$?
if [[ $rc -eq 2 && "$err" == *"CARD-OK"* ]] && \
   grep -q "check-in status card" "$ck/args.txt" 2>/dev/null && \
   grep -q "FAKE-REPO" "$ck/args.txt" 2>/dev/null && \
   grep -q "RECENT-MARKER" "$ck/args.txt" 2>/dev/null; then
  ok "q @haiku /check-in"; else fail q "rc=$rc err=$err args=$(cat "$ck/args.txt" 2>/dev/null | head -5 | tr '\n' ' ')"; fi

# (q2) @@haiku /check-in with stubs: rc 0, stdout lacks Persistent-session route, stdout has CARD-OK (relay mode)
out="$(echo "{\"prompt\":\"@@haiku /check-in\",\"transcript_path\":\"$ck/t.jsonl\",\"session_id\":\"S1\",\"cwd\":\"$ck\"}" | AT_ROUTE_CHECKIN_SCRIPT="$ck/state.sh" PATH="$ck:$PATH" bash "$HOOK")"; rc=$?
if [[ $rc -eq 0 && "$out" != *"Persistent-session route"* && "$out" == *"CARD-OK"* ]]; then
  ok "q2 @@haiku /check-in"; else fail q2 "rc=$rc out=$(echo "$out" | head -3 | tr '\n' ' ')"; fi

# (q3) @haiku /check-in with missing AT_ROUTE_CHECKIN_SCRIPT: question unchanged, args.txt has /check-in but NOT check-in status card
export CK_ARGS_FILE="$ck/args3.txt"
err="$(echo "{\"prompt\":\"@haiku /check-in\",\"transcript_path\":\"$ck/t.jsonl\",\"session_id\":\"S1\",\"cwd\":\"$ck\"}" | AT_ROUTE_CHECKIN_SCRIPT="/nonexistent/file.sh" PATH="$ck:$PATH" bash "$HOOK" 2>&1 >/dev/null)"; rc=$?
if [[ $rc -eq 2 ]] && grep -q "^/check-in\$" "$ck/args3.txt" 2>/dev/null && ! grep -q "check-in status card" "$ck/args3.txt" 2>/dev/null; then
  ok "q3 missing checkin script"; else fail q3 "rc=$rc args=$(cat "$ck/args3.txt" 2>/dev/null | head -3 | tr '\n' ' ')"; fi

echo "$pass/$total PASS"
[[ $pass -eq $total ]]
