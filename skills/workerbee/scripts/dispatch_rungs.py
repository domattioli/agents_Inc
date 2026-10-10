"""Shared D48 rung tables for render_dispatch.py and check_dispatch_prompt.py.

FAN_OUT_BY_RUNG: per Lead rung (width, total, depth) default and ceiling.
MODEL_RUNG: model alias to rung. LADDER: rungs low to high. ALIAS_VENDOR: model alias to vendor.
Single source; do not copy these tables.
"""
from __future__ import annotations

FAN_OUT_BY_RUNG = {
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
LADDER = ("grunt", "workhorse", "orchestrator", "executive")
ALIAS_VENDOR = {
    "fable": "claude", "opus": "claude", "sonnet": "claude", "haiku": "claude",
    "astra": "codex", "sol": "codex", "terra": "codex", "luna": "codex",
}
