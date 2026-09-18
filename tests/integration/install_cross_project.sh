#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
home="$tmp/home with spaces"; source="$tmp/source"; bin="$tmp/bin"
mkdir -p "$home" "$bin" "$tmp/project A" "$tmp/project B"
cp -R "$repo" "$source"
cp "$repo/tests/fixtures/fake_codex.py" "$bin/codex"; chmod +x "$bin/codex"
HOME="$home" PATH="$bin:/usr/bin:/bin" PYTHONPATH="$source" python3 -m agents_inc.install.cli install --source "$source"
mv "$source" "$tmp/source-gone"
for project in "$tmp/project A" "$tmp/project B"; do
  printf 'proof' | HOME="$home" PATH="/usr/bin:/bin" "$home/.local/share/agents-inc/current/bin/agents-inc" run --model astra --cwd "$project" >/dev/null
done
echo "install cross-project smoke: PASS"
