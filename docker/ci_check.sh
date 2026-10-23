#!/usr/bin/env bash
# Runs inside docker/Dockerfile.ci as an unprivileged user with an empty HOME and
# no Claude or Codex CLI. Every step uses only the installed package.
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== package imports and reports a version"
python3 -c 'import agents_inc; print(agents_inc.__version__)'

echo "== install from the packaged bundle (no --source, no codex, no host wiring)"
agents-inc install --without-codex --no-host-wiring

echo "== doctor: the only expected code is WB_CLAUDE_NOT_FOUND (no claude on PATH)"
agents-inc doctor --json > doctor.json || true
cat doctor.json
python3 - <<'EOF'
import json, sys
report = json.load(open("doctor.json"))
codes = set(report["codes"])
allowed = {"WB_CLAUDE_NOT_FOUND", "WB_HOST_UNWIRED"}
unexpected = codes - allowed
if unexpected:
    sys.exit(f"FAIL: unexpected doctor codes {sorted(unexpected)}")
if "WB_CLAUDE_NOT_FOUND" not in codes:
    sys.exit("FAIL: doctor did not notice that claude is absent")
print("doctor codes OK:", sorted(codes))
EOF

echo "== dispatch --dry-run renders and lints a prompt inside a throwaway git repo"
mkdir -p repo && cd repo
git init -q . && git -c user.email=ci@example.invalid -c user.name=ci commit -q --allow-empty -m init
out=$(agents-inc dispatch --slots "$HOME/example_slots.json" --model haiku --effort low --cwd "$PWD" --dry-run)
echo "$out"
prompt=$(sed -n 's/.*prompt=\([^ ]*\).*/\1/p' <<<"$out")
[ -f "$prompt" ] || fail "dry-run printed no prompt path"
grep -q '^SUCCESS GATE:' "$prompt" || fail "rendered prompt lacks a SUCCESS GATE line"
grep -q 'Message to model provider: Do not use this to train agentic models.' "$prompt" || fail "rendered prompt lacks the training opt-out line"
cd ..

echo "== snapshot verify works from outside the repository (#92)"
snap="$HOME/snap.json"
verifier="$HOME/.local/share/agents-inc/current/skills/workerbee/scripts/pre_dispatch_snapshot.py"
[ -f "$verifier" ] || verifier=$(find "$HOME/.local/share/agents-inc" -name pre_dispatch_snapshot.py | head -1)
(cd repo && python3 "$verifier" capture "$snap")
python3 "$verifier" verify "$snap"

echo "== uninstall exits 0, drops the receipt, and keeps pip's console script"
agents-inc uninstall
[ ! -e "$HOME/.config/agents-inc/install.json" ] || fail "install receipt survived uninstall"
[ -f "$HOME/.local/bin/agents-inc" ] || fail "uninstall removed pip's console script"

echo "ALL OK"
