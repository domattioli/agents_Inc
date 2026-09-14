"""Compatibility import namespace for the agents-inc distribution.

The implementation remains in :mod:`workerbees` for backwards compatibility.
This namespace exposes the same modules without duplicating or moving them.
"""
from pathlib import Path
import importlib
import sys

# Let Python resolve ``agents_inc.<module>`` against the existing implementation.
_implementation = Path(__file__).resolve().parent.parent / "workerbees"
__path__ = [str(_implementation)]

# Preserve class identity for the most commonly imported public module.  More
# modules can be added here if callers compare objects across namespaces.
sys.modules.setdefault(__name__ + ".router", importlib.import_module("workerbees.router"))

__all__ = []
