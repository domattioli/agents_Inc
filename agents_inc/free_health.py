"""Free-tier backend health tracking (spec 012).

CLI: python3 -m agents_inc.free_health {report|classify|pick-default}
"""
import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

_OUTCOMES = ("ok", "withdrawn", "zdr", "rate_limited", "overloaded", "error")


def health_path() -> Path:
    return Path(os.path.expanduser("~")) / ".codex-bridge" / "backend-health.json"


def overlay_path() -> Path:
    return Path(os.path.expanduser("~")) / ".codex-bridge" / "model-status.json"


def _load_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print("free_health: warning: corrupt file (not an object): %s" % path, file=sys.stderr)
            return {}
        return data
    except (json.JSONDecodeError, OSError):
        print("free_health: warning: corrupt file: %s" % path, file=sys.stderr)
        return {}


def _save_json_file(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp_name, str(path))
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_health() -> dict:
    return _load_json_file(health_path())


def save_health(data: dict) -> None:
    _save_json_file(health_path(), data)


def load_overlay() -> dict:
    return _load_json_file(overlay_path())


def save_overlay(data: dict) -> None:
    _save_json_file(overlay_path(), data)


def classify(status: int, body: str, headers: dict | None = None):
    """Return (outcome, retry_seconds|None)."""
    body_l = (body or "").lower()

    if 200 <= status < 300:
        return "ok", None

    if status == 404:
        if "unavailable for free" in body_l:
            return "withdrawn", None
        if "data policy" in body_l or "zero data retention" in body_l or "zero-data-retention" in body_l:
            return "zdr", None
        return "error", None

    if status in (429, 503):
        outcome = "rate_limited" if status == 429 else "overloaded"
        retry = None
        if headers:
            for k, v in headers.items():
                if k.lower() == "retry-after":
                    try:
                        retry = float(v)
                    except (TypeError, ValueError):
                        retry = None
                    break
        if retry is None:
            m = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", body_l)
            if m:
                retry = float(m.group(1))
        if retry is None and outcome == "rate_limited":
            retry = 60.0
        return outcome, retry

    return "error", None


def backend_key(provider: str, model: str | None = None) -> str:
    if provider == "gemini":
        if model and "flash-lite" in model:
            return "gemini-flash-lite"
        return "gemini-flash"
    return provider


def _default_models_path() -> Path:
    return Path(__file__).resolve().parent / "models.json"


def report(provider: str, model: str, outcome: str, retry_after: float | None = None,
           message: str | None = None, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    if outcome in ("withdrawn", "zdr"):
        overlay = load_overlay()
        overlay[model] = {
            "status": "unavailable",
            "reason": outcome,
            "at": now.isoformat(),
        }
        save_overlay(overlay)

    health = load_health()
    key = backend_key(provider, model)
    record = health.get(key) or {}

    record.setdefault("cooldown_until", None)
    record.setdefault("failure_streak", 0)
    calls_day = record.get("calls_day")
    calls_today = record.get("calls_today", 0)
    if calls_day != today:
        calls_today = 0
    calls_today += 1

    if outcome == "ok":
        record["status"] = "ok"
        record["failure_streak"] = 0
        record["cooldown_until"] = None
    elif outcome in ("rate_limited", "overloaded"):
        streak = record.get("failure_streak", 0) + 1
        record["failure_streak"] = streak
        if retry_after is not None:
            delay = retry_after
        else:
            delay = min(60 * (2 ** (streak - 1)), 3600)
        delay = min(delay, 3600)
        record["cooldown_until"] = (now + timedelta(seconds=delay)).isoformat()
        record["status"] = "degraded"
    elif outcome == "error":
        record["last_error"] = message
    # withdrawn/zdr: backend record untouched except calls counter

    record["calls_day"] = today
    record["calls_today"] = calls_today

    health[key] = record
    save_health(health)


def in_cooldown(provider: str, model: str | None = None, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    health = load_health()
    key = backend_key(provider, model)
    record = health.get(key)
    if not record:
        return False
    cooldown_until = record.get("cooldown_until")
    if not cooldown_until:
        return False
    try:
        until = datetime.fromisoformat(cooldown_until)
    except ValueError:
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return now < until


def effective_status(model_id: str, catalog_entry: dict) -> str:
    overlay = load_overlay()
    entry = overlay.get(model_id)
    if entry and "status" in entry:
        return entry["status"]
    return catalog_entry.get("status", "unprobed")


def pick_default(provider: str, task: str, catalog: dict | None = None, now: datetime | None = None):
    if catalog is None:
        try:
            with open(_default_models_path()) as f:
                catalog = json.load(f)
        except (OSError, json.JSONDecodeError):
            catalog = {}

    models = catalog.get("models", {})
    for model_id, entry in models.items():
        if entry.get("provider") != provider:
            continue
        if not model_id.endswith(":free"):
            continue
        status = effective_status(model_id, entry)
        if status == "unavailable":
            continue
        if task not in entry.get("tasks_good", []):
            continue
        if task in entry.get("tasks_bad", []):
            continue
        return model_id
    return None


def _cmd_report(args) -> int:
    report(
        provider=args.provider,
        model=args.model,
        outcome=args.outcome,
        retry_after=args.retry_after,
        message=args.message,
    )
    return 0


def _cmd_classify(args) -> int:
    with open(args.body_file) as f:
        body = f.read()
    outcome, retry = classify(status=args.status, body=body)
    retry_str = "-" if retry is None else str(retry)
    print("%s %s" % (outcome, retry_str))
    return 0


def _cmd_pick_default(args) -> int:
    result = pick_default(provider=args.provider, task=args.task)
    if result is None:
        print("no eligible free model", file=sys.stderr)
        return 3
    print(result)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="free_health")
    sub = parser.add_subparsers(dest="command", required=True)

    p_report = sub.add_parser("report")
    p_report.add_argument("--provider", required=True)
    p_report.add_argument("--model", required=True)
    p_report.add_argument("--outcome", required=True, choices=_OUTCOMES)
    p_report.add_argument("--retry-after", type=float, default=None)
    p_report.add_argument("--message", default=None)
    p_report.set_defaults(func=_cmd_report)

    p_classify = sub.add_parser("classify")
    p_classify.add_argument("--status", type=int, required=True)
    p_classify.add_argument("--body-file", required=True)
    p_classify.set_defaults(func=_cmd_classify)

    p_pick = sub.add_parser("pick-default")
    p_pick.add_argument("--provider", required=True)
    p_pick.add_argument("--task", required=True)
    p_pick.set_defaults(func=_cmd_pick_default)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
