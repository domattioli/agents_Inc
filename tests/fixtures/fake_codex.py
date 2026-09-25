#!/usr/bin/env python3
"""Deterministic Codex stand-in used by cross-project installer smoke tests."""
import json
import os
import sys
print(json.dumps({"argv": sys.argv[1:], "stdin": sys.stdin.read(), "cwd": os.getcwd()}))
