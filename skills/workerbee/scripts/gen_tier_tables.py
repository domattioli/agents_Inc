#!/usr/bin/env python3
"""Generate tier table for skills/workerbee/SKILL.md from models.json and routing.json.

Validates that all model tiers and routing tiers are valid rungs, that routing
defaults exist in models.json, and that their tiers match. Renders the table
between marker comments with --write or checks freshness with --check.
"""

import argparse
import json
import sys
from pathlib import Path


RUNGS = ("executive", "orchestrator", "workhorse", "grunt")
BEGIN_MARKER = "<!-- BEGIN GENERATED tier-table (skills/workerbee/scripts/gen_tier_tables.py --write); do not edit by hand -->"
END_MARKER = "<!-- END GENERATED tier-table -->"


def resolve_paths(skill_path=None, models_path=None, routing_path=None):
    """Resolve file paths relative to repo root."""
    repo_root = Path(__file__).resolve().parents[3]

    if skill_path is None:
        skill_path = repo_root / "skills" / "workerbee" / "SKILL.md"
    else:
        skill_path = Path(skill_path)

    if models_path is None:
        models_path = repo_root / "agents_inc" / "models.json"
    else:
        models_path = Path(models_path)

    if routing_path is None:
        routing_path = repo_root / "agents_inc" / "routing.json"
    else:
        routing_path = Path(routing_path)

    return skill_path, models_path, routing_path


def load_json(path):
    """Load JSON file."""
    return json.loads(path.read_text())


def validate_and_build_table(models_data, routing_data):
    """Validate configs and build tier table data.

    Returns (errors, tier_table) where tier_table is dict of (rung, provider) -> list of ids.
    """
    errors = []
    models = models_data.get("models", {})
    tiers = routing_data.get("tiers", {})

    # Validate models.json tiers
    for model_id, model_info in models.items():
        tier = model_info.get("tier")
        if tier not in RUNGS:
            errors.append(model_id)

    # Validate routing.json tiers keys and defaults
    for rung, providers in tiers.items():
        if rung not in RUNGS:
            errors.append(rung)

        for provider, default_id in providers.items():
            # Check default_id exists in models.json
            if default_id not in models:
                errors.append(default_id)
            else:
                # Check tier matches
                model_tier = models[default_id].get("tier")
                if model_tier != rung:
                    errors.append(default_id)

    if errors:
        return errors, None

    # Build table data: (rung, provider) -> list of ids
    tier_table = {}

    # Collect all (rung, provider) pairs and their model ids from models.json
    for model_id, model_info in models.items():
        rung = model_info.get("tier")
        provider = model_info.get("provider")
        if rung and provider:
            key = (rung, provider)
            if key not in tier_table:
                tier_table[key] = []
            tier_table[key].append(model_id)

    # Ensure all (rung, provider) pairs from routing are in the table
    for rung, providers in tiers.items():
        for provider in providers.keys():
            key = (rung, provider)
            if key not in tier_table:
                tier_table[key] = []

    return [], tier_table


def render_table(tier_table):
    """Render markdown table from tier data."""
    if not tier_table:
        return ""

    # Sort by rung order, then provider
    rung_order = {rung: i for i, rung in enumerate(RUNGS)}
    sorted_keys = sorted(
        tier_table.keys(),
        key=lambda x: (rung_order[x[0]], x[1])
    )

    lines = []
    lines.append("| rung | provider | default (routing.json) | all ids (models.json) |")
    lines.append("|---|---|---|---|")

    # Load routing to get defaults for each (rung, provider)
    routing = load_json(Path(__file__).resolve().parents[3] / "agents_inc" / "routing.json")
    tiers_config = routing.get("tiers", {})

    for rung, provider in sorted_keys:
        # Get default from routing.json
        default_id = tiers_config.get(rung, {}).get(provider)
        default_cell = f"`{default_id}`" if default_id else "—"

        # Get all ids from tier_table, sorted
        ids = sorted(tier_table[(rung, provider)])
        ids_cell = ", ".join(f"`{id}`" for id in ids) if ids else "—"

        lines.append(f"| {rung} | {provider} | {default_cell} | {ids_cell} |")

    return "\n".join(lines)


def write_block(skill_path, body):
    """Write table to SKILL.md between markers."""
    text = skill_path.read_text()

    if BEGIN_MARKER not in text or END_MARKER not in text:
        print("Missing markers in SKILL.md", file=sys.stderr)
        sys.exit(1)

    before = text.split(BEGIN_MARKER, 1)[0]
    after = text.split(END_MARKER, 1)[1]

    new_text = before + BEGIN_MARKER + "\n" + body + "\n" + END_MARKER + after
    skill_path.write_text(new_text)


def parse_table(text):
    """Parse markdown table into dict of (rung, provider) -> {ids, default}."""
    data = {}
    for line in text.split("\n"):
        if line.startswith("|") and "rung" not in line and "---|" not in line:
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 4:
                rung = parts[0]
                provider = parts[1]
                default_cell = parts[2]
                ids_cell = parts[3]

                key = (rung, provider)
                default_id = default_cell.strip("`").strip("—") if default_cell != "—" else None
                ids = set()
                for id_text in ids_cell.split(","):
                    id_text = id_text.strip().strip("`").strip("—")
                    if id_text:
                        ids.add(id_text)

                data[key] = {"ids": ids, "default": default_id}
    return data


def check_block(skill_path, body):
    """Check if table in SKILL.md matches rendered body."""
    text = skill_path.read_text()

    if BEGIN_MARKER not in text or END_MARKER not in text:
        print("Missing markers in SKILL.md", file=sys.stderr)
        sys.exit(1)

    current_block = text.split(BEGIN_MARKER, 1)[1].split(END_MARKER, 1)[0].strip()
    rendered = body.strip()

    if current_block == rendered:
        print("tier-table: current")
        sys.exit(0)
    else:
        # Parse both tables by (rung, provider) key
        current_data = parse_table(current_block)
        rendered_data = parse_table(rendered)

        # Find all keys in either version
        all_keys = set(current_data.keys()) | set(rendered_data.keys())

        # Collect differing ids and defaults
        diff_ids = set()
        for key in all_keys:
            current_row = current_data.get(key, {"ids": set(), "default": None})
            rendered_row = rendered_data.get(key, {"ids": set(), "default": None})

            # Compare id sets
            current_ids = current_row["ids"]
            rendered_ids = rendered_row["ids"]
            diff_ids.update(current_ids ^ rendered_ids)

            # Compare defaults
            if current_row["default"] != rendered_row["default"]:
                if current_row["default"]:
                    diff_ids.add(current_row["default"])
                if rendered_row["default"]:
                    diff_ids.add(rendered_row["default"])

        if diff_ids:
            for id_val in sorted(diff_ids):
                print(id_val)

        print("tier-table: stale", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Generate tier table for SKILL.md")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Check if table is current")
    group.add_argument("--write", action="store_true", help="Write table to SKILL.md")

    parser.add_argument("--skill", help="Path to SKILL.md")
    parser.add_argument("--models", help="Path to models.json")
    parser.add_argument("--routing", help="Path to routing.json")

    args = parser.parse_args()

    skill_path, models_path, routing_path = resolve_paths(
        args.skill, args.models, args.routing
    )

    # Load configs
    models_data = load_json(models_path)
    routing_data = load_json(routing_path)

    # Validate and build table
    errors, tier_table = validate_and_build_table(models_data, routing_data)

    if errors:
        for error in errors:
            print(error)
        sys.exit(1)

    # Render table
    body = render_table(tier_table)

    if args.check:
        check_block(skill_path, body)
    elif args.write:
        write_block(skill_path, body)
        sys.exit(0)


if __name__ == "__main__":
    main()
