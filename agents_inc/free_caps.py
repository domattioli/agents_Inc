"""Free-tier daily call limits tracking (spec 012).

CLI: python3 -m agents_inc.free_caps probe-openrouter [--from-file]
"""
import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from agents_inc import free_health


def calls_today(provider: str, now: datetime | None = None, db_path: str | None = None) -> int:
    """Return call count for provider on current UTC date.

    Queries usage DB for rows with backend=provider and day=today.
    Falls back to health record calls_today when calls_day==today, else 0.
    Returns max of both.

    Args:
        provider: Backend provider name (e.g., "openrouter", "gemini", "mistral")
        now: Aware UTC datetime, default datetime.now(timezone.utc)
        db_path: Path to usage.db, default ~/.codex-bridge/usage.db

    Returns:
        Integer count, or 0 if DB missing/unreadable
    """
    now = now or datetime.now(timezone.utc)
    if db_path is None:
        db_path = str(Path(os.path.expanduser("~")) / ".codex-bridge" / "usage.db")

    today = now.date().isoformat()

    # Try to read from usage DB
    db_count = 0
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM usage WHERE backend = ? AND day = ?",
            (provider, today)
        )
        result = cursor.fetchone()
        if result:
            db_count = result[0]
        conn.close()
    except (sqlite3.Error, FileNotFoundError, OSError):
        # DB missing or unreadable, use default 0
        pass

    # Try to read from health record
    health_count = 0
    try:
        health = free_health.load_health()
        key = free_health.backend_key(provider)
        record = health.get(key, {})
        calls_day = record.get("calls_day")
        calls_today_val = record.get("calls_today", 0)

        # Only use health record if it's for today
        if calls_day == today:
            health_count = calls_today_val
    except Exception:
        pass

    return max(db_count, health_count)


def cap_for(provider: str) -> int | None:
    """Return daily call cap for provider.

    Checks ~/.codex-bridge/free-caps.json (probed cap) first,
    then falls back to routing.json daily_caps (configured cap).

    Args:
        provider: Backend provider name

    Returns:
        Integer cap, or None if not configured
    """
    # Check free-caps.json (probed)
    caps_path = Path(os.path.expanduser("~")) / ".codex-bridge" / "free-caps.json"
    if caps_path.exists():
        try:
            with open(caps_path) as f:
                caps_data = json.load(f)
            if provider in caps_data and "cap" in caps_data[provider]:
                return caps_data[provider]["cap"]
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    # Fall back to routing.json (configured)
    from agents_inc import router
    routing_data = getattr(router, '_get_routing_data', lambda: {})()
    if routing_data:
        daily_caps = routing_data.get("daily_caps", {})
        if provider in daily_caps:
            return daily_caps[provider]

    # Try direct load
    routing_path = Path(__file__).parent / "routing.json"
    if routing_path.exists():
        try:
            with open(routing_path) as f:
                routing_data = json.load(f)
            daily_caps = routing_data.get("daily_caps", {})
            if provider in daily_caps:
                return daily_caps[provider]
        except (json.JSONDecodeError, OSError):
            pass

    return None


def at_cap(provider: str, now: datetime | None = None, db_path: str | None = None) -> bool:
    """Check if provider has reached daily call limit.

    Args:
        provider: Backend provider name
        now: Aware UTC datetime, default datetime.now(timezone.utc)
        db_path: Path to usage.db, default ~/.codex-bridge/usage.db

    Returns:
        True if calls_today >= cap, False if cap is None or calls_today < cap
    """
    cap = cap_for(provider)
    if cap is None:
        return False

    count = calls_today(provider, now=now, db_path=db_path)
    return count >= cap


def probe_openrouter(from_file: str | None = None) -> dict:
    """Probe OpenRouter API key limits and store result.

    Fetches key metadata (daily limits) from OpenRouter API or fixture.
    Derives daily cap: if is_free_tier true -> 50 else 1000.
    Writes result to ~/.codex-bridge/free-caps.json.

    Args:
        from_file: Path to JSON fixture file; if None, fetches from live API

    Returns:
        Dictionary with OpenRouter metadata (from data.daily_requests_limit or derived)

    Raises:
        RuntimeError: If from_file not found or if live fetch fails
    """
    data = {}

    if from_file:
        # Load from fixture
        fixture_path = Path(from_file)
        if not fixture_path.exists():
            raise RuntimeError(f"Fixture file not found: {from_file}")
        with open(fixture_path) as f:
            fixture = json.load(f)
        data = fixture.get("data", {})
    else:
        # Fetch from live API
        api_key = os.environ.get("OPEN_ROUTER_API_KEY") or _read_openrouter_key()
        if not api_key:
            raise RuntimeError("No OpenRouter API key found")

        headers = {"Authorization": f"Bearer {api_key}"}
        req = urllib.request.Request("https://openrouter.ai/api/v1/key", headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                response = json.loads(resp.read())
            data = response.get("data", {})
        except Exception as e:
            raise RuntimeError(f"Failed to probe OpenRouter: {e}")

    # Derive cap
    # From fixture: data.daily_requests_limit (e.g., 50)
    # From live API: data.limit_remaining and data.is_free_tier
    cap = None

    if "daily_requests_limit" in data:
        # Fixture path
        cap = data["daily_requests_limit"]
    elif "limit_remaining" in data:
        # Live API path (not used in tests, but for completeness)
        cap = data["limit_remaining"]
        if data.get("is_free_tier"):
            cap = 50
        else:
            cap = 1000
    else:
        # Fallback: check is_free_tier
        if data.get("is_free_tier"):
            cap = 50
        else:
            cap = 1000

    # Write to free-caps.json
    caps_dir = Path(os.path.expanduser("~")) / ".codex-bridge"
    caps_dir.mkdir(parents=True, exist_ok=True)
    caps_path = caps_dir / "free-caps.json"

    caps_data = {
        "openrouter": {
            "cap": cap,
            "source": "probe",
            "at": datetime.now(timezone.utc).isoformat(),
        }
    }

    with open(caps_path, "w") as f:
        json.dump(caps_data, f, indent=2)

    return {"openrouter": caps_data["openrouter"]}


def _read_openrouter_key() -> str | None:
    """Read OpenRouter API key from ~/.codex-bridge/openrouter-key.

    Returns:
        API key string, or None if not found
    """
    key_path = Path(os.path.expanduser("~")) / ".codex-bridge" / "openrouter-key"
    if key_path.exists():
        try:
            with open(key_path) as f:
                return f.read().strip()
        except OSError:
            pass
    return None


def main(argv: list[str] | None = None) -> int:
    """CLI for free_caps.

    Commands:
        probe-openrouter [--from-file PATH]
            Probe OpenRouter key limits and save to free-caps.json

    Args:
        argv: Command-line arguments (default sys.argv[1:])

    Returns:
        Exit code (0 for success)
    """
    parser = argparse.ArgumentParser(prog="free_caps")
    sub = parser.add_subparsers(dest="command", required=True)

    p_probe = sub.add_parser("probe-openrouter")
    p_probe.add_argument("--from-file", default=None, help="Path to fixture JSON file")

    args = parser.parse_args(argv)

    if args.command == "probe-openrouter":
        try:
            probe_openrouter(from_file=args.from_file)
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
