#!/usr/bin/env python3
"""Recover a stopped delegate's transcript summary.

Streams a JSONL transcript line by line and extracts:
- Last text block from assistant messages
- Files written by Write/Edit/MultiEdit/NotebookEdit tool_use blocks
- Last tool_result with is_error=true
- Final status (handback, stop_reason, or unknown)
- Count of malformed lines

Output: fixed labels with truncation to max-chars bound.
"""

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript", type=Path, help="JSONL transcript file")
    parser.add_argument("--max-chars", type=int, default=4000, help="Max output length")
    args = parser.parse_args()

    # Check if file exists and is readable
    if not args.transcript.exists():
        print(f"Error: transcript file not found: {args.transcript}", file=sys.stderr)
        sys.exit(2)

    try:
        fh = args.transcript.open("r")
    except (OSError, IOError) as e:
        print(f"Error: cannot read transcript: {e}", file=sys.stderr)
        sys.exit(2)

    # Track state
    last_text = None
    files_written = OrderedDict()
    last_error = None
    final_status = "unknown"
    skipped_lines = 0

    # Stream line by line
    for line in fh:
        # Check for blank line
        if not line.strip():
            continue

        # Try to parse JSON
        try:
            row = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            skipped_lines += 1
            continue

        # Check if it's a dict
        if not isinstance(row, dict):
            skipped_lines += 1
            continue

        # Process assistant rows
        if row.get("type") == "assistant":
            message = row.get("message", {})

            # Track stop_reason
            if "stop_reason" in message:
                final_status = message.get("stop_reason")

            # Track last text block and tool_use blocks
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue

                    if block.get("type") == "text":
                        last_text = block.get("text")
                    elif block.get("type") == "tool_use":
                        tool_name = block.get("name")
                        if tool_name == "SubagentHandback":
                            final_status = "handback"
                        elif tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                            inp = block.get("input", {})
                            file_path = inp.get("file_path") or inp.get("notebook_path")
                            if file_path:
                                # Move to end if already exists
                                if file_path in files_written:
                                    del files_written[file_path]
                                files_written[file_path] = None
                                # Keep only last 20 unique paths
                                while len(files_written) > 20:
                                    files_written.pop(next(iter(files_written)))

        # Process user rows for tool_result with is_error=true
        elif row.get("type") == "user":
            message = row.get("message", {})
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        if block.get("is_error"):
                            result_content = block.get("content")
                            if result_content:
                                last_error = result_content

    fh.close()

    # Build output
    lines = []
    lines.append(f"status: {final_status}")
    lines.append("files written (Write/Edit/MultiEdit/NotebookEdit; Bash writes not tracked):")
    if files_written:
        for path in files_written.keys():
            lines.append(f"- {path}")
    else:
        lines.append("- none")
    lines.append(f"last error: {last_error if last_error else '(none)'}")
    lines.append(f"last text: {last_text if last_text else '(none)'}")
    lines.append(f"skipped malformed lines: {skipped_lines}")

    output = "\n".join(lines)
    if len(output) > args.max_chars:
        output = output[:args.max_chars]

    sys.stdout.write(output)


if __name__ == "__main__":
    main()
