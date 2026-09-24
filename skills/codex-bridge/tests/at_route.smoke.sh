#!/usr/bin/env bash
# Smoke test for at_route.sh. Never calls a real model: claude is stubbed on PATH.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$HERE/../scripts/at_route.sh"
TMP="$(mktemp -d -t at_route_smoke.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
export AT_ROUTE_LOG="$TMP/at_route.log"
unset AT_ROUTE_ACTIVE
pass=0; total=5

ok()   { echo "PASS $1"; pass=$((pass + 1)); }
fail() { echo "FAIL $1: $2"; }

mkstub() { # $1 = dir, $2 = exit code
  mkdir -p "$1"
  printf '#!/bin/sh\necho STUB-OK\necho stub-stderr >&2\nexit %s\n' "$2" >"$1/claude"
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
if [[ $rc -eq 2 && -z "$out" && "$err" == *STUB-OK* && "$err" == *"[at_route] haiku (claude-haiku-4-5-20251001)"* ]]; then
  ok "d stub success (block)"; else fail d "rc=$rc out=$out err=$err"; fi

# relay mode: answer on stdout, exit 0
total=$((total + 1))
out="$(echo '{"prompt":"@Haiku what is 2+2"}' | AT_ROUTE_MODE=relay PATH="$TMP/ok:$PATH" bash "$HOOK")"; rc=$?
if [[ $rc -eq 0 && "$out" == *STUB-OK* && "$out" == *"[at_route] answer from haiku (claude-haiku-4-5-20251001)"* ]]; then
  ok "d2 stub success (relay)"; else fail d2 "rc=$rc out=$out"; fi

# (e) stub exits 3
mkstub "$TMP/bad" 3
out="$(echo '{"prompt":"@haiku hi"}' | PATH="$TMP/bad:$PATH" bash "$HOOK")"; rc=$?
if [[ $rc -eq 0 && "$out" == *"haiku call failed (exit 3)"* && "$out" == *stub-stderr* && "$out" == *"Answer the operator's question yourself."* ]]; then
  ok "e stub failure"; else fail e "rc=$rc out=$out"; fi

echo "$pass/$total PASS"
[[ $pass -eq $total ]]
