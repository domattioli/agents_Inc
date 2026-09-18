"""Optional-provider key setup. Runs in the user's terminal; the agent only ever sees 'stored'/'skipped'.

Reconstructed 2026-09-18 from plan Task 5 + phase-2 amendment because the file was gitignored by *key* and never committed.
"""
from __future__ import annotations
import getpass
import os
import webbrowser
from pathlib import Path

ENV_PATH = Path.home() / ".config" / "workerbees" / ".env"
KEY_PAGES = {
    "gemini": "https://aistudio.google.com/apikey",
    "mistral": "https://console.mistral.ai/api-keys",
    "openrouter": "https://openrouter.ai/settings/keys",
}
REQUIRED = {"claude", "codex"}

def setup_key(provider: str, env_path: Path = ENV_PATH, prompt=getpass.getpass, opener=webbrowser.open) -> str:
    if provider not in KEY_PAGES:
        raise ValueError(f"unknown optional provider: {provider}")
    opener(KEY_PAGES[provider])
    key = prompt(f"Paste your {provider} API key (input hidden; Enter to skip): ").strip()
    if not key:
        return "skipped"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    var = f"{provider.upper()}_API_KEY"
    lines = [line for line in env_path.read_text().splitlines() if not line.startswith(var + "=")] if env_path.exists() else []
    lines.append(f"{var}={key}")
    env_path.write_text("\n".join(lines) + "\n")
    os.chmod(env_path, 0o600)
    return "stored"

def available_providers(env_path: Path = ENV_PATH, extra_env_paths: list | None = None) -> set[str]:
    out = set(REQUIRED)
    paths_to_scan = [env_path]
    if extra_env_paths:
        paths_to_scan.extend(extra_env_paths)
    for path in paths_to_scan:
        if path.exists():
            for line in path.read_text().splitlines():
                name, _, val = line.partition("=")
                if name.endswith("_API_KEY") and val:
                    out.add(name[:-len("_API_KEY")].lower())
    return out

if __name__ == "__main__":
    import sys
    print(setup_key(sys.argv[1]))
