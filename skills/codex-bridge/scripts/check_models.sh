#!/usr/bin/env bash
set -euo pipefail

# Local-only availability check: no provider commands, sockets, or network calls.
exec python3 - "$HOME/.codex/models_cache.json" <<'PY'
import json
import re
import shutil
import sys
from pathlib import Path


cache_path = Path(sys.argv[1])
home = Path.home()


def present(command):
    return shutil.which(command) is not None


def file_present(path):
    return path.is_file()


def nickname(display_name, slug):
    value = display_name or slug
    value = re.sub(r"^gpt[- ]*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return value.lower() or slug


rows = []
try:
    with cache_path.open(encoding="utf-8") as handle:
        models = json.load(handle).get("models", [])
except (OSError, ValueError, TypeError, AttributeError):
    models = []

for model in models:
    if not isinstance(model, dict):
        continue
    slug = str(model.get("slug") or model.get("id") or "")
    if not slug:
        continue
    levels = []
    for level in model.get("supported_reasoning_levels", []):
        if isinstance(level, dict) and level.get("effort"):
            levels.append(str(level["effort"]))
    rows.append((nickname(model.get("display_name"), slug), "OpenAI", slug,
                 "yes" if present("codex") else "no", ",".join(levels) or "n/a"))

rows.extend([
    ("gemini", "Google", "gemini-cli", "yes" if present("gemini") and
     file_present(home / ".codex-bridge" / "gemini-key") else "no", "n/a"),
    ("mistral", "Mistral", "mistral-cli", "yes" if present("mistral") and
     file_present(home / ".config" / "devstral" / "api_key") else "no", "n/a"),
    ("openrouter", "OpenRouter", "openrouter", "yes" if
     file_present(home / ".codex-bridge" / "openrouter-key") else "no", "n/a"),
])

headers = ("nickname", "vendor", "slug", "wired(yes/no)", "effort levels")
widths = [len(value) for value in headers]
for row in rows:
    widths = [max(width, len(value)) for width, value in zip(widths, row)]

def render(row):
    return " | ".join(value.ljust(width) for value, width in zip(row, widths))

print(render(headers))
print("-+-".join("-" * width for width in widths))
for row in rows:
    print(render(row))
PY
