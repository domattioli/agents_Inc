#!/usr/bin/env bash
# Luna-brain stress run inside docker/Dockerfile.dev. Each scenario runs R times (default 3); a run passes when every
# expected string appears in the session's result text. Prints one row per run and a summary. Never prints a secret.
# The Claude token goes in by variable name only, so its value is never on a command line:
#   docker build -f docker/Dockerfile.dev --build-arg CLAUDE_CODE_VERSION=<host version> --build-arg CODEX_VERSION=<host version> -t agents-inc-dev:luna .
#   export CLAUDE_CODE_OAUTH_TOKEN  # loaded beforehand without echoing it
#   docker run --rm -e CLAUDE_CODE_OAUTH_TOKEN -e R=3 -v "$PWD:/src:ro" -v "$PWD/docker/luna_stress.sh:/stress.sh:ro" \
#     -v "$OUT:/home/dev/out" --mount type=bind,src=$HOME/.codex/auth.json,dst=/run/secrets/codex_auth.json,readonly \
#     agents-inc-dev:luna bash /stress.sh
# SCENARIOS picks a subset of: latin tools follow par. Codex rollouts land in $OUT/codex-sessions.
set -uo pipefail
R=${R:-3}
OUT=$HOME/out; mkdir -p "$OUT"
W=$HOME/work; mkdir -p "$W"; cd "$W"
cp -r /src/mods/luna-brain "$HOME/mod"
seq 1 173 > a.txt; seq 1 95 > b.txt; seq 1 41 > c.txt
git init -q . 2>/dev/null

prompt_latin="Call the Agent tool once with subagent_type luna-brain:luna. Its task: 'Write one Latin sentence with an English translation separated by an em dash. Use no tools.' Quote its report verbatim."
prompt_tools="Call the Agent tool once with subagent_type luna-brain:luna. Its task: 'Run wc -l a.txt with Bash, then Read b.txt and give the text of its line 50. Report A=<count> B=<that text>.' Quote its report verbatim."
prompt_follow="Step 1: call the Agent tool once with subagent_type luna-brain:luna. Its task: 'Run wc -l c.txt with Bash and report the count as C=<n>.' Wait for its report. Step 2: SendMessage the same agent: 'what model are you, exactly'. Wait for its reply. Quote both replies verbatim."
prompt_par="In one message, call the Agent tool three times in parallel, each with subagent_type luna-brain:luna and run_in_background false. Tasks: 1) 'Run wc -l a.txt with Bash; report A=<n>.' 2) 'Run wc -l b.txt with Bash; report B=<n>.' 3) 'Run wc -l c.txt with Bash; report C=<n>.' Quote all three reports verbatim."

declare -A EXPECT=([latin]="—" [tools]="A=173|B=50" [follow]="C=41|gpt-6" [par]="A=173|B=95|C=41")
declare -A PROMPT=([latin]="$prompt_latin" [tools]="$prompt_tools" [follow]="$prompt_follow" [par]="$prompt_par")
pass=0; total=0
printf '%-8s %-3s %-5s %6s %5s %6s %5s %s\n' scenario run ok secs steps codexc errs missing
for s in ${SCENARIOS:-latin tools follow par}; do
  for i in $(seq 1 "$R"); do
    n=$s.$i; before=$(find "$HOME/.codex/sessions" -name 'rollout-*.jsonl' 2>/dev/null | sort)
    t0=$(date +%s)
    timeout 600 claude -p "${PROMPT[$s]}" --model haiku --plugin-dir "$HOME/mod" --output-format stream-json --verbose \
      --debug-file "$OUT/$n.log" --allowedTools "Agent,SendMessage,Bash(wc:*),Read" > "$OUT/$n.jsonl" 2> "$OUT/$n.err"
    rc=$?; secs=$(( $(date +%s) - t0 ))
    python3 -c 'import json,sys
r=[]
for l in open(sys.argv[1]):
    try: d=json.loads(l)
    except Exception: continue
    if d.get("type")=="result": r.append(str(d.get("result") or ""))
print("\n".join(r))' "$OUT/$n.jsonl" > "$OUT/$n.result.txt"
    missing=""; IFS='|' read -ra want <<< "${EXPECT[$s]}"
    for w in "${want[@]}"; do grep -qiF -- "$w" "$OUT/$n.result.txt" || missing="$missing $w"; done
    steps=$(grep -c 'luna-brain: step' "$OUT/$n.log" 2>/dev/null); errs=$(grep -ciE 'luna-brain: .*(fail|empty reply|error)' "$OUT/$n.log" 2>/dev/null)
    new=$(comm -13 <(echo "$before") <(find "$HOME/.codex/sessions" -name 'rollout-*.jsonl' 2>/dev/null | sort))
    cc=0; for f in $new; do cc=$((cc + $(grep -c '"type":"custom_tool_call"\|"type": "custom_tool_call"\|"type":"function_call"' "$f"))); done
    ok=no; [ -z "$missing" ] && [ $rc -eq 0 ] && ok=yes && pass=$((pass+1)); total=$((total+1))
    printf '%-8s %-3s %-5s %6s %5s %6s %5s %s\n' "$s" "$i" "$ok" "$secs" "$steps" "$cc" "$errs" "${missing:-$( [ $rc -ne 0 ] && echo rc=$rc )}"
  done
done
cp -r "$HOME/.codex/sessions" "$OUT/codex-sessions" 2>/dev/null
echo "PASS $pass/$total"
