"""Backward-compatible namespace for :mod:`agents_inc`.

``workerbees`` remains importable for existing callers.  Its public modules
are aliases of the canonical modules, so objects retain identity across both
import paths.
"""
from importlib import import_module
import sys

_MODULES = (
    "adapters",
    "adapters.base",
    "adapters.claude",
    "adapters.codex",
    "artifacts",
    "bench",
    "config_schema",
    "control",
    "derivation_store",
    "doctor",
    "envelope",
    "gateway",
    "hosts",
    "hosts.gen_stubs",
    "keys",
    "ledger",
    "lineup_router",
    "pipeline",
    "policy",
    "registry",
    "reviewer",
    "router",
    "schema",
    "store",
    "verifier",
    "install",
    "install.bundle",
    "install.cli",
    "install.discovery",
    "install.doctor",
    "install.paths",
    "install.receipt",
    "install.runtime",
    "install.transaction",
)

for _module in _MODULES:
    sys.modules[f"{__name__}.{_module}"] = import_module(f"agents_inc.{_module}")

__all__: list[str] = []
