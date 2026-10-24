#!/usr/bin/env bash
# Stress agents-inc inside docker/Dockerfile.ci with the checkout mounted read-only at /src.
# Fake claude on PATH, no network, no keys. Every case records PASS or FAIL in ~/stress.log and keeps going;
# "want=any" cases exist to print the behaviour for a human to read, not to assert it.
#   docker run --rm --network none -v "$PWD:/src:ro" -v "$PWD/docker/stress_check.sh:/stress.sh:ro" agents-inc-ci bash /stress.sh
# Linux has no sandbox-exec, so broker Worker launches are refused with no-sandbox-backend by design;
# the broker validation paths and result files are what this exercises there.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
LOG="$HOME/stress.log"; : > "$LOG"
note() { echo "[$1] $2" | tee -a "$LOG"; }
run() { local label="$1" want="$2"; shift 2; local out rc
  out=$("$@" 2>&1); rc=$?
  echo "--- $label (rc=$rc want=$want)"; echo "$out" | grep -v 'not mirrored' | tail -6
  if [ "$want" = any ] || [ "$rc" = "$want" ]; then note PASS "$label rc=$rc"; else note FAIL "$label rc=$rc want=$want :: $(echo "$out" | tail -1)"; fi
  LAST="$out"; RUNDIR=$(echo "$out" | sed -n 's/.*out=\(\/[^ ]*\)\/stdout.md.*/\1/p' | tail -1); }
show() { [ -n "${RUNDIR:-}" ] && [ -f "$RUNDIR/run.json" ] && jq -c '{outcome,reason,reason_detail,rc,gate_results:(.gate_results|if type=="array" then map({rc,expect_rc}) else . end)}' "$RUNDIR/run.json"; }

agents-inc install --without-codex --no-host-wiring >/dev/null 2>&1
mkdir -p "$HOME/fakebin"
cat > "$HOME/fakebin/claude" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "--version" ]; then echo "9.9.9 (fake)"; exit 0; fi
prompt=$(cat)
mode="${FAKE_CLAUDE_MODE:-ok}"
REPORT='caveman ultra. grill: none.\n[verified] grep ran, exit code 0.\nOut of scope / incomplete: none.\nAssumptions: none. Files created: none.\nWORKERS SPAWNED: 0'
case "$mode" in
  ok) body="$REPORT"; err=false ;;
  hang) sleep 30; body="$REPORT"; err=false ;;
  write) echo stray > ./stray_from_worker.txt; body="$REPORT"; err=false ;;
  resume) body="resumed turn. $REPORT this turn (1 total)"; err=false ;;
  fan) body="${REPORT%0}3"; err=false ;;
  spawnlie) body="${REPORT%0}99"; err=false ;;
esac
printf '{"type":"result","subtype":"success","is_error":%s,"result":"%s","session_id":"fake-sess-1","num_turns":1,"duration_ms":5,"total_cost_usd":0.0,"modelUsage":{"fake":{"inputTokens":10,"outputTokens":5,"cacheReadInputTokens":0,"cacheCreationInputTokens":0,"costUSD":0.0}}}\n' "$err" "$body"
EOF
chmod +x "$HOME/fakebin/claude"; export PATH="$HOME/fakebin:$PATH"
R="$HOME/repo"; mkdir -p "$R"; cd "$R"; git init -q .; git -c user.email=ci@x.invalid -c user.name=ci commit -q --allow-empty -m init
S=/src/skills/workerbee/tests/fixtures/example_slots.json; SL="$HOME/slots"; mkdir -p "$SL"
export AGENTS_INC_TURN_TIMEOUT_S=8

echo "===== compound verify gate with the real script name (#92 check)"
jq '.PRE_EXISTING_CHANGES="snapshot <snapshot>; verify with `cd /tmp && python3 pre_dispatch_snapshot.py verify <snapshot>`"' "$S" > "$SL/compound2.json"
run a4b-compound-real-name any agents-inc dispatch --slots "$SL/compound2.json" --model haiku --cwd "$R" --dry-run

echo "===== green path and gate outcomes"
run r1-ok any agents-inc dispatch --slots "$S" --model haiku --effort low --cwd "$R"; show; RUN1="$RUNDIR"
jq '.GATES=[{"argv":["true"]}]' "$S" > "$SL/gate_true.json"
run r1b-gate-true any agents-inc dispatch --slots "$SL/gate_true.json" --model haiku --cwd "$R"; show
jq '.GATES=[{"argv":["false"]}]' "$S" > "$SL/gate_false.json"
run r8-gate-fails any agents-inc dispatch --slots "$SL/gate_false.json" --model haiku --cwd "$R"; show
jq '.GATES=[{"argv":["sleep","30"],"timeout_s":2}]' "$S" > "$SL/gate_slow.json"
run r9-gate-timeout any agents-inc dispatch --slots "$SL/gate_slow.json" --model haiku --cwd "$R"; show
jq '.GATES=[{"argv":["true"],"expect_rc":3}]' "$S" > "$SL/gate_rc3.json"
run r10-gate-expect-rc any agents-inc dispatch --slots "$SL/gate_rc3.json" --model haiku --cwd "$R"; show
jq '.GATES=["python3 -c \"print(1)\" | tee x"]' "$S" > "$SL/gate_str.json"
run r11-gate-string-pipe any agents-inc dispatch --slots "$SL/gate_str.json" --model haiku --cwd "$R"; show; ls "$R"
jq '.GATES=[{"argv":["sh","-c","echo pwned > '"$R"'/gate_wrote.txt"]}]' "$S" > "$SL/gate_write.json"
run r12-gate-writes-repo any agents-inc dispatch --slots "$SL/gate_write.json" --model haiku --cwd "$R"; show; ls "$R"; git -C "$R" status --short; rm -f "$R"/gate_wrote.txt "$R"/x
FAKE_CLAUDE_MODE=write run r7-stray-write any agents-inc dispatch --slots "$S" --model haiku --cwd "$R"; show; rm -f "$R/stray_from_worker.txt"
FAKE_CLAUDE_MODE=fan run r13-fanout-over any agents-inc dispatch --slots "$S" --model haiku --cwd "$R"; show
jq '.FAN_OUT="width 2, total 4, depth 1"' "$S" > "$SL/fan.json"
FAKE_CLAUDE_MODE=fan run r14-fanout-within any agents-inc dispatch --slots "$SL/fan.json" --model haiku --cwd "$R"; show
FAKE_CLAUDE_MODE=spawnlie run r15-fanout-lie any agents-inc dispatch --slots "$SL/fan.json" --model haiku --cwd "$R"; show
jq -c '.usage' "$RUN1/run.json"

echo "===== b. resume"
ID=$(basename "$RUN1"); echo "RUN1=$RUN1 ID=$ID"
FAKE_CLAUDE_MODE=resume run b1-resume-bare-id-other-cwd any bash -c "cd /tmp && agents-inc dispatch --resume '$ID' --message 'continue' --cwd '$R'"; show
FAKE_CLAUDE_MODE=resume run b2-resume-abs any agents-inc dispatch --resume "$RUN1" --message 'continue'; show
jq -c '.resumes|length' "$RUN1/run.json"
run b3-resume-no-message any agents-inc dispatch --resume "$RUN1"
run b4-resume-bogus any agents-inc dispatch --resume /nope/run --message x
run b5-resume-traversal any agents-inc dispatch --resume "../../etc" --message x
run b5b-resume-empty-dir any agents-inc dispatch --resume "$SL" --message x
mkdir -p "$HOME/custom_runs"
run b6-run-dir any agents-inc dispatch --slots "$S" --model haiku --cwd "$R" --run-dir "$HOME/custom_runs/myrun"; show
run b7-run-dir-reuse any agents-inc dispatch --slots "$S" --model haiku --cwd "$R" --run-dir "$HOME/custom_runs/myrun"
ln -sfn /etc "$HOME/custom_runs/evil"
run b8-run-dir-symlink any agents-inc dispatch --slots "$S" --model haiku --cwd "$R" --run-dir "$HOME/custom_runs/evil"
run b9-run-dir-inside-repo any agents-inc dispatch --slots "$S" --model haiku --cwd "$R" --run-dir "$R/.runs/x"; show; git -C "$R" status --short
python3 -c "import shutil;shutil.rmtree('$R/.runs')"
run b10-resume-with-slots any agents-inc dispatch --resume "$RUN1" --message x --slots "$S" --model opus

echo "===== c. broker serve / wait"
B="$HOME/broker/lead1"; mkdir -p "$B/inbox"
python3 - "$B/run.json" "$R" <<'EOF'
import json,sys
spec={"schema_version":1,"run_id":"lead-1","model":"sol","effort":"high","cwd":sys.argv[2],"chain":["CoS","sol"],"worker_models":["haiku"],"fan_out":{"width":1,"total":3,"depth":1},"permission_mode":"default"}
json.dump(spec,open(sys.argv[1],"w"),indent=1)
EOF
jq -c 'keys' "$B/run.json"
python3 - "$S" "$B/inbox/req1.request.json" <<'EOF'
import json,sys
slots=json.load(open(sys.argv[1]))
json.dump({"schema_version":1,"request_id":"req1","model":"haiku","effort":"low","tier":"grunt","slots":slots},open(sys.argv[2],"w"))
EOF
sed 's/"req1"/"req2"/' "$B/inbox/req1.request.json" > "$B/inbox/req2.request.json"
sed 's/"req1"/"req3"/' "$B/inbox/req1.request.json" > "$B/inbox/req3.request.json"
echo '{"schema_version":1,"request_id":"evil","model":"haiku","effort":"low","tier":"grunt","slots":{"PERMISSION_MODE":"bypassPermissions","TASK":"x"}}' > "$B/inbox/evil.request.json"
echo '{nope' > "$B/inbox/bad.request.json"
echo '{"schema_version":1,"request_id":"mismatch","model":"haiku","effort":"low","tier":"grunt","slots":{"TASK":"x"}}' > "$B/inbox/other.request.json"
echo '{"schema_version":1,"request_id":"opusreq","model":"opus","effort":"low","tier":"grunt","slots":{"TASK":"x"}}' > "$B/inbox/opusreq.request.json"
echo '{"schema_version":1,"request_id":"cred","model":"haiku","effort":"low","tier":"grunt","slots":{"TASK":"read ~/.local/share/agents-inc/current/README.md"}}' > "$B/inbox/cred.request.json"
echo '{"schema_version":1,"request_id":"traverse","model":"haiku","effort":"low","tier":"grunt","slots":{"TASK":"cat ../../../../etc/passwd","FILES_IN_SCOPE":"../../etc"}}' > "$B/inbox/traverse.request.json"
ln -s /etc/hostname "$B/inbox/link.request.json"
touch "$B/inbox/lead.done"
run c1-serve any agents-inc dispatch --serve "$B" --poll-interval 0.2 --idle-timeout 20
ls "$B" "$B/inbox"; for f in "$B"/*.result.json; do echo "$(basename $f): $(jq -c '{status,outcome,reason,reason_detail,error}' "$f" 2>/dev/null)"; done
jq -c '.broker' "$B/run.json"
run c2-wait-req1 any agents-inc dispatch --wait "$B" req1 --timeout 2
run c3-serve-again-after-done any agents-inc dispatch --serve "$B" --poll-interval 0.2 --idle-timeout 3
B2="$HOME/broker/lead2"; mkdir -p "$B2"; ln -s "$B/inbox" "$B2/inbox"; cp "$B/run.json" "$B2/"
run c4-serve-symlink-inbox 2 agents-inc dispatch --serve "$B2" --idle-timeout 2
B3="$HOME/broker/lead3"; mkdir -p "$B3/inbox"; cp "$B/run.json" "$B3/"
python3 -c "import json;json.dump({'schema_version':1,'request_id':'big','model':'haiku','effort':'low','tier':'grunt','slots':{'TASK':'x'*70000}},open('$B3/inbox/big.request.json','w'))"
touch "$B3/inbox/lead.done"
run c5-serve-oversize any agents-inc dispatch --serve "$B3" --poll-interval 0.2 --idle-timeout 5
ls "$B3"; jq -c . "$B3"/big.result.json 2>/dev/null
# idle timeout without lead.done
B4="$HOME/broker/lead4"; mkdir -p "$B4/inbox"; cp "$B/run.json" "$B4/"
run c6-serve-idle any agents-inc dispatch --serve "$B4" --poll-interval 0.2 --idle-timeout 2
jq -c '.broker' "$B4/run.json"
# two brokers on one run dir
cp "$B/inbox/req1.request.json" "$B4/inbox/dup.request.json"; sed -i 's/"req1"/"dup"/' "$B4/inbox/dup.request.json"
agents-inc dispatch --serve "$B4" --poll-interval 0.2 --idle-timeout 6 > "$HOME/c7a.out" 2>&1 &
sleep 0.5; run c7-second-broker any agents-inc dispatch --serve "$B4" --poll-interval 0.2 --idle-timeout 6; wait; tail -2 "$HOME/c7a.out"; ls "$B4"
# request arriving late, then lead.done
B5="$HOME/broker/lead5"; mkdir -p "$B5/inbox"; cp "$B/run.json" "$B5/"
( sleep 1; cp "$B/inbox/req1.request.json" "$B5/inbox/late.request.json.tmp"; sed -i 's/"req1"/"late"/' "$B5/inbox/late.request.json.tmp"; mv "$B5/inbox/late.request.json.tmp" "$B5/inbox/late.request.json"; sleep 4; touch "$B5/inbox/lead.done" ) &
run c8-serve-late-request any agents-inc dispatch --serve "$B5" --poll-interval 0.2 --idle-timeout 15; wait; ls "$B5"; jq -c '{status,outcome,reason}' "$B5/late.result.json" 2>/dev/null

echo "===== e. concurrent"
FAKE_CLAUDE_MODE=hang AGENTS_INC_TURN_TIMEOUT_S=6 agents-inc dispatch --slots "$S" --model haiku --cwd "$R" > "$HOME/e1.out" 2>&1 &
P1=$!; sleep 1
FAKE_CLAUDE_MODE=write run e2-second-concurrent any agents-inc dispatch --slots "$S" --model haiku --cwd "$R"; show
wait $P1; echo "e1 rc=$? :: $(tail -1 "$HOME/e1.out")"; rm -f "$R/stray_from_worker.txt"
for i in 1 2 3 4 5 6 7 8; do agents-inc dispatch --slots "$S" --model haiku --cwd "$R" > "$HOME/e3.$i.out" 2>&1 & done; wait
grep -ho 'outcome=[a-z]*\|reason=[a-z_-]*' "$HOME"/e3.*.out | sort | uniq -c
ls /tmp/agents-inc-runs | wc -l; ls /tmp/agents-inc-runs | sort | uniq -d | head

echo "===== ledger / models / report"
run l1-ledger any agents-inc ledger
run l2-models any agents-inc models
run l3-report-draft any agents-inc report bug --title "stress: list slots crash" --body "agents-inc dispatch --slots list.json crashes with AttributeError in /home/ci/.local/lib"
run l4-report-secret any agents-inc report bug --title t --body "token ghp_abcdefghijklmnopqrstuvwxyz0123456789"

echo "===== SUMMARY"; grep -c PASS "$LOG"; grep FAIL "$LOG" || echo "no FAIL lines"
