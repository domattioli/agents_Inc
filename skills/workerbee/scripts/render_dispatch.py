"""Render dispatch from slots JSON: fill template with slot values, append header or contract reference.

Usage: python3 render_dispatch.py --slots <json> [--contract-ref <path>] [--header <path>] [--template <path>] [--model <alias>]

--slots: path to JSON file with slot values, keyed by slot name (required).
--contract-ref: path to contract file; if given, output "CONTRACT: <path>" instead of pasted header text.
--header: path to header.md; default: skills/workerbee/header.md relative to script directory.
--template: path to slots.md; default: skills/workerbee/slots.md relative to script directory.
--model: delegate model alias; feeds the derived REPORTING CHAIN line (see derive_chain).

Output: filled template (slots substituted), blank line, then either pasted header text or
CONTRACT: reference line followed by training opt-out line. No {{ may remain.
Pasted header text starts at the CAVEMAN line: the markdown title and authoring
comment above it are stripped. NOTES defaults to "none"; STYLE may be empty.

Exit 0 on success, 2 if required slot missing or empty (stderr names it).
"""
from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path



# D48 fan-out defaults per Lead rung and model-to-rung table: dispatch_rungs.py.
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
from dispatch_rungs import ALIAS_VENDOR, FAN_OUT_BY_RUNG, LADDER, MODEL_RUNG  # noqa: E402


def default_fan_out(slots: dict) -> str:
    """Return the D48 FAN_OUT line value from a RUNG or MODEL slot, else Orchestrator defaults."""
    rung = "orchestrator"
    for key in ("RUNG", "MODEL"):
        value = slots.get(key)
        if isinstance(value, str) and value.strip():
            word = value.strip().lower()
            if word in FAN_OUT_BY_RUNG:
                rung = word
                break
            hit = next((r for m, r in MODEL_RUNG.items() if m in word), None)
            if hit:
                rung = hit
                break
    width, total, depth = FAN_OUT_BY_RUNG[rung]
    return f"width {width}, total {total}, depth {depth}"

def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _first_alias(text: str) -> str | None:
    """Return the model alias that appears earliest in text, else None."""
    best = None
    for alias in MODEL_RUNG:
        m = re.search(r"\b%s\b" % alias, text, re.IGNORECASE)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), alias)
    return best[1] if best else None


def _alias_on_rung(vendor: str | None, rung: str) -> str | None:
    for alias, r in MODEL_RUNG.items():
        if r == rung and ALIAS_VENDOR.get(alias) == vendor:
            return alias
    return None


def derive_chain(slots: dict, model: str | None, settings: dict) -> dict:
    """Return DELEGATE, SUPERVISOR, EXECUTIVE plus a sources map (slot|setting|default).

    Precedence per seat: explicit slot, then setting chain.*, then the ladder default.
    DELEGATE: slot, then model argument, then MODEL slot, then the first alias named
    in ROLE (earliest position wins), else the word delegate. Pure: reads no files.
    """
    chain_cfg = settings.get("chain") if isinstance(settings, dict) else None
    chain_cfg = chain_cfg if isinstance(chain_cfg, dict) else {}
    sources = {}

    delegate = _text(slots.get("DELEGATE"))
    sources["DELEGATE"] = "slot"
    if not delegate:
        for cand in (model, slots.get("MODEL")):
            word = _text(cand).lower()
            if word:
                delegate = _first_alias(word) or word
                break
    if not delegate:
        delegate = _first_alias(_text(slots.get("ROLE"))) or "delegate"
        sources["DELEGATE"] = "default"

    key = delegate.lower()
    vendor = ALIAS_VENDOR.get(key)
    rung = MODEL_RUNG.get(key)

    supervisor = _text(slots.get("SUPERVISOR"))
    sources["SUPERVISOR"] = "slot"
    if not supervisor:
        if _text(chain_cfg.get("supervisor")):
            supervisor, sources["SUPERVISOR"] = _text(chain_cfg["supervisor"]), "setting"
        else:
            sources["SUPERVISOR"] = "default"
            above = None
            if rung in LADDER and LADDER.index(rung) + 1 < len(LADDER):
                above = _alias_on_rung(vendor, LADDER[LADDER.index(rung) + 1])
            supervisor = above or "CoS"

    executive = _text(slots.get("EXECUTIVE"))
    sources["EXECUTIVE"] = "slot"
    if not executive:
        if _text(chain_cfg.get("executive")):
            executive, sources["EXECUTIVE"] = _text(chain_cfg["executive"]), "setting"
        else:
            sources["EXECUTIVE"] = "default"
            top = _alias_on_rung(vendor, "executive")
            executive = top if top and top not in (key, supervisor.lower()) else supervisor
    return {"DELEGATE": delegate, "SUPERVISOR": supervisor, "EXECUTIVE": executive, "sources": sources}


def read_settings() -> dict:
    """Read ~/.config/agents-inc/settings.json via HOME; {} on any error. Never writes."""
    path = Path(os.environ.get("HOME", "~")).expanduser() / ".config/agents-inc/settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


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
    model = None

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
        elif args[i] == "--model" and i + 1 < len(args):
            model = args[i + 1]
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

    chain = derive_chain(slots_data, model, read_settings())
    src = chain.pop("sources")
    slots_data.update(chain)
    print("chain: %s < %s < %s (%s, %s, %s)" % (
        chain["DELEGATE"], chain["SUPERVISOR"], chain["EXECUTIVE"],
        src["DELEGATE"], src["SUPERVISOR"], src["EXECUTIVE"]), file=sys.stderr)

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

    # A top-rung supervisor is also the executive: drop the "X reports to X" link.
    result = re.sub(r"(?m)(REPORTING CHAIN: .*?)(\S+) reports to \2; ", r"\1", result)

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
