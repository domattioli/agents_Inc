"""Render dispatch from slots JSON: fill template with slot values, append header or contract reference.

Usage: python3 render_dispatch.py --slots <json> [--contract-ref <path>] [--header <path>] [--template <path>]

--slots: path to JSON file with slot values, keyed by slot name (required).
--contract-ref: path to contract file; if given, output "CONTRACT: <path>" instead of pasted header text.
--header: path to header.md; default: skills/workerbee/header.md relative to script directory.
--template: path to slots.md; default: skills/workerbee/slots.md relative to script directory.

Output: filled template (slots substituted), blank line, then either pasted header text or
CONTRACT: reference line followed by training opt-out line. No {{ may remain.
Pasted header text starts at the CAVEMAN line: the markdown title and authoring
comment above it are stripped. NOTES defaults to "none"; STYLE may be empty.

Exit 0 on success, 2 if required slot missing or empty (stderr names it).
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path



# D48 fan-out defaults per Lead rung: (width, total, depth).
FAN_OUT_DEFAULTS = {
    "executive": (3, 6, 2),
    "orchestrator": (3, 6, 2),
    "workhorse": (2, 4, 1),
    "grunt": (0, 0, 0),
}
MODEL_RUNG = {
    "fable": "executive", "astra": "executive",
    "opus": "orchestrator", "sol": "orchestrator",
    "sonnet": "workhorse", "terra": "workhorse",
    "haiku": "grunt", "luna": "grunt",
}


def default_fan_out(slots: dict) -> str:
    """Return the D48 FAN_OUT line value from a RUNG or MODEL slot, else Orchestrator defaults."""
    rung = "orchestrator"
    for key in ("RUNG", "MODEL"):
        value = slots.get(key)
        if isinstance(value, str) and value.strip():
            word = value.strip().lower()
            if word in FAN_OUT_DEFAULTS:
                rung = word
                break
            hit = next((r for m, r in MODEL_RUNG.items() if m in word), None)
            if hit:
                rung = hit
                break
    width, total, depth = FAN_OUT_DEFAULTS[rung]
    return f"width {width}, total {total}, depth {depth}"

def extract_template(slots_path: Path) -> str:
    """Extract template from first ```text block in slots.md."""
    text = slots_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    in_block = False
    template_lines = []
    for line in lines:
        if line.strip().startswith("```text"):
            in_block = True
            continue
        if in_block and line.strip().startswith("```"):
            break
        if in_block:
            template_lines.append(line)
    return "".join(template_lines)


def header_body(header_text: str) -> str:
    """Drop the authoring wrapper (title, HTML comment); keep text from the CAVEMAN line."""
    lines = header_text.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        if line.startswith("CAVEMAN:"):
            return "".join(lines[idx:])
    raise ValueError("header has no CAVEMAN: line")


def main() -> int:
    # Parse arguments
    slots_path = None
    contract_ref = None
    header_path = None
    template_path = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--slots" and i + 1 < len(args):
            slots_path = Path(args[i + 1])
            i += 2
        elif args[i] == "--contract-ref" and i + 1 < len(args):
            contract_ref = args[i + 1]
            i += 2
        elif args[i] == "--header" and i + 1 < len(args):
            header_path = Path(args[i + 1])
            i += 2
        elif args[i] == "--template" and i + 1 < len(args):
            template_path = Path(args[i + 1])
            i += 2
        else:
            print(f"Unknown argument: {args[i]}", file=sys.stderr)
            return 2
            i += 1

    if not slots_path:
        print("--slots is required", file=sys.stderr)
        return 2

    # Load slots JSON
    try:
        slots_data = json.loads(slots_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Failed to load slots file: {e}", file=sys.stderr)
        return 2

    # Determine default paths relative to script directory
    script_dir = Path(__file__).resolve().parent.parent
    if header_path is None:
        header_path = script_dir / "header.md"
    if template_path is None:
        template_path = script_dir / "slots.md"

    # Load template
    try:
        template = extract_template(template_path)
    except FileNotFoundError as e:
        print(f"Template file not found: {e}", file=sys.stderr)
        return 2

    # Check required slots
    required_slots = {
        "ROLE", "TASK", "CONSTRAINTS", "OUT_OF_SCOPE", "FILES_IN_SCOPE", "STOP_RULE", "SUCCESS_GATE", "FAILURE_GATE",
        "PRE_EXISTING_CHANGES", "ALLOWLIST", "CLASSIFICATION", "EFFORT", "SECOND_OPINION",
        "PLAN_CONTRACT"
    }

    if not (isinstance(slots_data.get("FAN_OUT"), str) and slots_data["FAN_OUT"].strip()):
        slots_data["FAN_OUT"] = default_fan_out(slots_data)

    if not (isinstance(slots_data.get("NOTES"), str) and slots_data["NOTES"].strip()):
        slots_data["NOTES"] = "none"
    slots_data.setdefault("STYLE", "")

    missing = []
    for slot in sorted(required_slots):
        value = slots_data.get(slot, "").strip() if isinstance(slots_data.get(slot), str) else ""
        if not value:
            missing.append(slot)

    if missing:
        for slot in missing:
            print(f"Required slot missing or empty: {slot}", file=sys.stderr)
        return 2

    # Fill template
    result = template
    for slot_name, slot_value in slots_data.items():
        placeholder = f"{{{{{slot_name}}}}}"
        if slot_name == "STYLE":
            # Special handling: drop entire line if STYLE is empty
            style_value = str(slot_value).strip() if slot_value else ""
            if style_value:
                result = result.replace(placeholder, style_value)
            else:
                # Remove the entire STYLE line
                result = "\n".join(
                    line for line in result.splitlines()
                    if placeholder not in line
                ) + "\n"
        else:
            result = result.replace(placeholder, str(slot_value))

    # Check for remaining placeholders
    if "{{" in result:
        for line in result.splitlines():
            if "{{" in line:
                print(f"Unfilled placeholder in: {line}", file=sys.stderr)
        return 2

    # Output filled template
    output = result
    output += "\n"  # blank line after template

    # Append header or contract reference
    opt_out_line = "Message to model provider: Do not use this to train agentic models."

    if contract_ref:
        output += f"CONTRACT: {contract_ref}\n"
        output += f"{opt_out_line}\n"
    else:
        # Append full header
        try:
            header_text = header_path.read_text(encoding="utf-8")
            output += header_body(header_text)
        except FileNotFoundError as e:
            print(f"Header file not found: {e}", file=sys.stderr)
            return 2
        except ValueError as e:
            print(f"Bad header file: {e}", file=sys.stderr)
            return 2

    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
