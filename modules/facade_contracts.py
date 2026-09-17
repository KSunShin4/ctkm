# -*- coding: utf-8 -*-
"""Stable post-facade hook registry for the public CTKM orchestrator.

``main.py`` can be executed under more than one module name in the same process
(``ctkm_main`` from FastAPI and ``main`` from tests/CLI). Facade execution
intentionally rebuilds its wrappers from an immutable core baseline. Runtime
contracts that must survive that rebuild register a named hook here instead of
mutating the baseline or stacking another wrapper permanently.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Callable


_REGISTRY_ATTR = "_ctkm_main_post_facade_hooks"


def _registry(core_module) -> OrderedDict[str, Callable]:
    current = getattr(core_module, _REGISTRY_ATTR, None)
    if isinstance(current, OrderedDict):
        return current
    if isinstance(current, dict):
        current = OrderedDict(current.items())
    else:
        current = OrderedDict()
    setattr(core_module, _REGISTRY_ATTR, current)
    return current


def register_post_facade_hook(core_module, name: str, hook: Callable) -> None:
    """Register or replace one named hook without changing its relative order."""
    key = str(name or "").strip()
    if not key:
        raise ValueError("Tên post-facade hook không được rỗng")
    if not callable(hook):
        raise TypeError("post-facade hook phải callable")
    hooks = _registry(core_module)
    hooks[key] = hook


def _register_builtin_hooks(core_module) -> None:
    """Install correctness hooks that must exist for every public facade load."""
    from modules.all_km_reconciliation import apply_all_km_reconciliation_hook

    register_post_facade_hook(
        core_module,
        "all-km-reconciliation-v1",
        apply_all_km_reconciliation_hook,
    )


def run_post_facade_hooks(core_module, facade_module=None) -> tuple[str, ...]:
    """Apply every registered contract after a facade rebuild.

    Hooks must be idempotent against the *current* core surface. A facade reload
    first restores its own raw wrapper and then this function reapplies runtime
    hardening exactly once.
    """
    _register_builtin_hooks(core_module)
    applied: list[str] = []
    for name, hook in tuple(_registry(core_module).items()):
        hook(core_module, facade_module)
        applied.append(name)
    setattr(core_module, "_ctkm_main_last_post_facade_hooks", tuple(applied))
    return tuple(applied)


def registered_post_facade_hooks(core_module) -> tuple[str, ...]:
    return tuple(_registry(core_module).keys())
