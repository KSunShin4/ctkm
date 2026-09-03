# -*- coding: utf-8 -*-
"""Reconciler entrypoint with KEY Channel included in business identity."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

_CORE_NAME = "_ctkm_reconciler_core"
_CORE_PATH = Path(__file__).with_name("reconciler_core.py")

if _CORE_NAME in sys.modules:
    _core = sys.modules[_CORE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(_CORE_NAME, _CORE_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Không nạp được reconciler core: {_CORE_PATH}")
    _core = importlib.util.module_from_spec(_spec)
    sys.modules[_CORE_NAME] = _core
    _spec.loader.exec_module(_core)

for _constant in ("_BUSINESS_COLUMNS", "_PROMOTION_ID_COLUMNS"):
    _columns = getattr(_core, _constant, None)
    if isinstance(_columns, list) and "key_channel" not in _columns:
        _index = _columns.index("channel") if "channel" in _columns else len(_columns)
        _columns.insert(_index, "key_channel")

for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)
