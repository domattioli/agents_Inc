#!/usr/bin/env bash
# Install at_route as a stable copy + @alias symlinks. Re-run after editing at_route.sh.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/at_route.sh"
DST="$HOME/.claude/scripts/at_route.sh"
mkdir -p "$HOME/.claude/scripts" "$HOME/.local/bin"
cp "$SRC" "$DST"; chmod +x "$DST"
for a in haiku sonnet opus fable astra sol terra luna gemini mistral; do
  ln -sf "$DST" "$HOME/.local/bin/@$a"
done
echo "installed $DST and ~/.local/bin/@{haiku,...,mistral}"
echo "hook line for ~/.claude/settings.json UserPromptSubmit: bash $DST"
