# -*- coding: utf-8 -*-
"""Public CTKM orchestrator entrypoint with fidelity contract installed eagerly."""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import sys

_CORE_NAME = "_ctkm_main_core"
_CORE_PATH = Path(__file__).with_name("main_core.py")

if _CORE_NAME in sys.modules:
    _core = sys.modules[_CORE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(_CORE_NAME, _CORE_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Không nạp được CTKM core: {_CORE_PATH}")
    _core = importlib.util.module_from_spec(_spec)
    sys.modules[_CORE_NAME] = _core
    _spec.loader.exec_module(_core)

# Install fidelity/correctness before exposing run_pipeline or helper functions.
# This makes `from main import run_pipeline` behave the same as backend/CLI.
_performance = importlib.import_module("modules.ctkm_performance")
_performance.install_performance_patches(_core)

# Standard company-file inference must obey the same two-channel contract even
# when this helper is used directly, before _process/_ensure_channel_mapping.
_original_infer_standard_fact_mapping = _core._infer_standard_fact_mapping


def _infer_standard_fact_mapping(df):
    mapping = _original_infer_standard_fact_mapping(df)
    if not mapping:
        return mapping
    return _performance.preserve_both_channel_mappings(
        mapping, df, normalize_header=_core._normalized_header,
    )


_core._infer_standard_fact_mapping = _infer_standard_fact_mapping

for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

if __name__ == "__main__":
    _core._cli()
