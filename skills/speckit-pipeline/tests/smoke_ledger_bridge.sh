#!/usr/bin/env bash
# Smoke test for resolve_rung.py + ledger_bridge.py -- the agents_for_dummies
# synergy pieces added to the DomI fork (D35). Exercises the full
# rung-resolve -> dispatch -> return flow against an isolated temp
# workspace (never touches this repo's real .workerbees/ ledger) and
# asserts the rung-to-schema-tier fix actually persists to SQLite.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts" && pwd)"
TMPWS="$(mktemp -d)"
trap 'rm -rf "$TMPWS"' EXIT

FAILED=0
pass() { echo "[OK] $1"; }
fail() { echo "[FAIL] $1"; FAILED=1; }

echo "test artifact content" > "$TMPWS/artifact.md"

# 1. resolve_rung.py resolves a real rung against this repo's live canon
RESOLVED="$(python3 "$SCRIPT_DIR/resolve_rung.py" Workhorse)"
if echo "$RESOLVED" | grep -q '"default": \["sonnet", "terra"\]'; then
  pass "resolve_rung.py Workhorse -> sonnet/terra"
else
  fail "resolve_rung.py Workhorse: got $RESOLVED"
fi

# 2. Supervisor synonym resolves to the Orchestrator row (D34)
SUP="$(python3 "$SCRIPT_DIR/resolve_rung.py" Supervisor)"
ORCH="$(python3 "$SCRIPT_DIR/resolve_rung.py" Orchestrator)"
if [[ "$(echo "$SUP" | python3 -c 'import json,sys;print(json.load(sys.stdin)["default"])')" == \
      "$(echo "$ORCH" | python3 -c 'import json,sys;print(json.load(sys.stdin)["default"])')" ]]; then
  pass "resolve_rung.py Supervisor == Orchestrator (D34 synonym)"
else
  fail "Supervisor and Orchestrator resolved differently: $SUP vs $ORCH"
fi

# 3. Unknown rung fails closed (exit 1, no silent guess)
if python3 "$SCRIPT_DIR/resolve_rung.py" Bogus 2>/dev/null; then
  fail "resolve_rung.py Bogus should have exited non-zero"
else
  pass "resolve_rung.py Bogus fails closed"
fi

# 4. Full dispatch -> return cycle persists to SQLite with the mapped tier
RUN_ID="$(python3 "$SCRIPT_DIR/ledger_bridge.py" new-run)"
NODE_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
WORKERBEES_STORE=both python3 "$SCRIPT_DIR/ledger_bridge.py" dispatch \
  --repo-root "$TMPWS" --run-id "$RUN_ID" --node-id "$NODE_ID" \
  --model opus --rung Orchestrator --task speckit-plan --provider claude \
  --gate-reason "frontier-tier phase dispatch" --artifact-file "$TMPWS/artifact.md" >/dev/null
WORKERBEES_STORE=both python3 "$SCRIPT_DIR/ledger_bridge.py" return \
  --repo-root "$TMPWS" --node-id "$NODE_ID" --status verified --seconds 1.0 >/dev/null

NODE_ROW="$(python3 -c "
import sqlite3
conn = sqlite3.connect('$TMPWS/.workerbees/workerbees.db')
print(conn.execute('SELECT tier, task FROM node WHERE node_id=?', ('$NODE_ID',)).fetchone())
")"
if [[ "$NODE_ROW" == "('frontier', 'speckit-plan:Orchestrator')" ]]; then
  pass "dispatch persists to SQLite: tier mapped to 'frontier', rung preserved in task"
else
  fail "unexpected node row: $NODE_ROW"
fi

# 5. Lint is clean (frontier dispatch supplied a gate_reason)
LINT="$(python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR/../../..')
from pathlib import Path
from workerbees import ledger
l = ledger.load(Path('$TMPWS'))
print(ledger.lint(l, source='sqlite', workspace=Path('$TMPWS')))
")"
if [[ "$LINT" == "[]" ]]; then
  pass "lint clean on the recorded frontier-tier dispatch"
else
  fail "unexpected lint findings: $LINT"
fi

if [[ "$FAILED" -eq 0 ]]; then
  echo "=== smoke_ledger_bridge.sh: ALL PASS ==="
  exit 0
else
  echo "=== smoke_ledger_bridge.sh: FAILURES ABOVE ==="
  exit 1
fi
