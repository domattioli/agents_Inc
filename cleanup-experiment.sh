#!/usr/bin/env bash
# Removes the three-way dashboard comparison and its artifacts.
# Keeps: the production dashboard, the bridge, the skill, the specs.
set -euo pipefail
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY=0; [[ "${1:-}" == "--dry-run" ]] && DRY=1

targets=(
  "$BASE/demo/compare"
  "$BASE/experiment"
  "$HOME/.codex-bridge/usage-opus.db"
  "$BASE/demo/index.html"
)
echo "cleanup-experiment $([[ $DRY == 1 ]] && echo '(DRY RUN)')"
for t in "${targets[@]}"; do
  if [[ -e "$t" ]]; then
    sz=$(du -sh "$t" 2>/dev/null | cut -f1)
    echo "  remove  $t  ($sz)"
    [[ $DRY == 0 ]] && rm -rf "$t"
  else
    echo "  absent  $t"
  fi
done
echo
echo "KEPT (production):"
for k in "$BASE/demo/usage-dashboard.html" "$BASE/demo/tictactoe-codex.html" \
         "$BASE/demo/tictactoe-gemini.html" "$BASE/skills" "$BASE/specs" \
         "$BASE/bridge.py" "$HOME/.codex-bridge/usage.db" "$HOME/.codex-bridge/usage.jsonl"; do
  [[ -e "$k" ]] && echo "  keep    $k"
done
echo
[[ $DRY == 1 ]] && echo "nothing deleted. re-run without --dry-run to apply." || echo "done."
