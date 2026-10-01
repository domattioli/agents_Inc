"""Optional-provider key setup. Runs in the user's terminal; the agent only ever sees 'stored'/'skipped'."""
from __future__ import annotations
import getpass, os, webbrowser
from pathlib import Path

ENV_PATH = Path.home() / ".config" / "workerbees" / ".env"
_PROVIDER_ALIASES = {"open_router": "openrouter"}
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
    lines = [l for l in env_path.read_text().splitlines() if not l.startswith(var + "=")] if env_path.exists() else []
    lines.append(f"{var}={key}")
    env_path.write_text("\n".join(lines) + "\n")
    os.chmod(env_path, 0o600)
    return "stored"

def available_providers(env_path: Path = ENV_PATH, extra_env_paths: list[Path] | None = None) -> set[str]:
    if extra_env_paths is None:
        extra_env_paths = [Path.home() / "Projects" / ".env"]
    out = set(REQUIRED)

    # Default path: also read the pre-014 location; agents-inc writes only ENV_PATH.
    if env_path is None or env_path == ENV_PATH:
        paths_to_scan = [ENV_PATH, Path.home() / ".config" / "agents_inc" / ".env"]
    else:
        paths_to_scan = [env_path]

    # Helper to extract provider name and apply aliases
    def get_provider(api_key_var: str) -> str:
        provider = api_key_var[:-len("_API_KEY")].lower()
        return _PROVIDER_ALIASES.get(provider, provider)

    # Scan primary paths
    for path in paths_to_scan:
        if path.exists():
            for line in path.read_text().splitlines():
                name, _, val = line.partition("=")
                if name.endswith("_API_KEY") and val:
                    out.add(get_provider(name))
    # Scan extra_env_paths for API key names only
    for path in extra_env_paths:
        if path.exists():
            for line in path.read_text().splitlines():
                name, _, val = line.partition("=")
                if name.endswith("_API_KEY") and val:
                    out.add(get_provider(name))
    return out

if __name__ == "__main__":
    import sys
    print(setup_key(sys.argv[1]))
