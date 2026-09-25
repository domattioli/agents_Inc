"""Refresh agents_inc/models.json against OpenRouter's public models catalog.

Public GET https://openrouter.ai/api/v1/models only. No key, no generation call.
See specs/012-free-tier-routing/contracts/cli.md and api012.md (T015) for the contract.
"""
import argparse
import json
import os
import sys
import urllib.request

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def _overlay_path():
    return os.path.join(os.path.expanduser("~"), ".codex-bridge", "model-status.json")


def _load_overlay(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _atomic_write_json(path, data, indent):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = _mkstemp(directory)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=indent)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _mkstemp(directory):
    import tempfile
    return tempfile.mkstemp(prefix=".tmp-", dir=directory)


def _fetch_models(from_file=None):
    """Return the raw fetch payload's `data` list, or raise on failure."""
    if from_file is not None:
        with open(from_file, "r") as f:
            payload = json.load(f)
    else:
        req = urllib.request.Request(OPENROUTER_MODELS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("data", [])


def _is_free(entry):
    model_id = entry.get("id", "")
    if model_id.endswith(":free"):
        return True
    pricing = entry.get("pricing", {}) or {}
    if pricing and all(str(v) == "0" for v in pricing.values()):
        return True
    return False


def _is_text_output(entry):
    architecture = entry.get("architecture", {}) or {}
    modalities = architecture.get("output_modalities")
    if not modalities:
        return True
    return list(modalities) == ["text"]


def refresh(apply=False, from_file=None, models_path=None):
    """Compare models.json against the OpenRouter catalog fetch.

    Returns a list of report lines. Raises on fetch failure (caller maps to
    exit code 2). Only writes models.json / overlay when apply=True.
    """
    if models_path is None:
        models_path = os.path.join(os.path.dirname(__file__), "models.json")

    fetch_data = _fetch_models(from_file=from_file)
    fetched_ids = {entry.get("id") for entry in fetch_data if entry.get("id")}
    free_entries_by_id = {entry.get("id"): entry for entry in fetch_data if _is_free(entry)}

    with open(models_path, "r") as f:
        text = f.read()
    catalog = json.loads(text)
    models = catalog.setdefault("models", {})

    # Preserve existing formatting: infer indent from the raw text.
    indent = 2
    for line in text.splitlines():
        stripped = line.lstrip(" ")
        if stripped != line and stripped:
            indent = len(line) - len(stripped)
            break

    lines = []
    touched_ids = []

    # Catalog openrouter ids absent from fetch -> would mark unavailable.
    for model_id, entry in models.items():
        if entry.get("provider") != "openrouter":
            continue
        if model_id not in fetched_ids:
            lines.append("would mark unavailable: {}".format(model_id))
            touched_ids.append(model_id)
            if apply:
                entry["status"] = "unavailable"

    # Free fetched ids not in catalog -> would add.
    for model_id, entry in free_entries_by_id.items():
        if model_id in models:
            continue
        lines.append("would add: {}".format(model_id))
        touched_ids.append(model_id)
        if apply:
            text_output = _is_text_output(entry)
            models[model_id] = {
                "vendor": None,
                "provider": "openrouter",
                "tier": "grunt",
                "tasks_good": [],
                "tasks_bad": [],
                "ctx_hint": 0,
                "cost_class": "free",
                "status": "unprobed" if text_output else "unavailable",
            }

    if apply:
        _atomic_write_json(models_path, catalog, indent)

        overlay_path = _overlay_path()
        overlay = _load_overlay(overlay_path)
        if overlay:
            changed = False
            for model_id in touched_ids:
                if model_id in overlay:
                    del overlay[model_id]
                    changed = True
            if changed:
                _atomic_write_json(overlay_path, overlay, 2)

    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m agents_inc.catalog_refresh")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--from-file", default=None)
    parser.add_argument("--models-path", default=None)
    args = parser.parse_args(argv)

    try:
        lines = refresh(apply=args.apply, from_file=args.from_file, models_path=args.models_path)
    except Exception as exc:
        print("catalog_refresh: fetch error: {}".format(exc), file=sys.stderr)
        return 2

    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
