# -*- coding: utf-8 -*-
"""Exporter entrypoint with business-first layout and explicit channel fidelity."""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import sys

_CORE_NAME = "_ctkm_exporter_core"
_CORE_PATH = Path(__file__).with_name("exporter_core.py")

if _CORE_NAME in sys.modules:
    _core = sys.modules[_CORE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(_CORE_NAME, _CORE_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Không nạp được exporter core: {_CORE_PATH}")
    _core = importlib.util.module_from_spec(_spec)
    sys.modules[_CORE_NAME] = _core
    _spec.loader.exec_module(_core)

_performance = importlib.import_module("modules.ctkm_performance")
_original_hide = _core._hide_technical_columns

_core._prepare_action_sheet = _performance.prepare_action_sheet_user_first
_core._filter_selected_columns = _performance.filter_selected_columns_keep_channels
_core._add_work_tracking_columns = _performance.unique_work_tracking_rows


def _hide_technical_columns(ws, *, action_sheet=False):
    return _performance.hide_technical_columns(
        ws,
        get_column_letter=_core.get_column_letter,
        original_hide=_original_hide,
        action_sheet=action_sheet,
    )


_core._hide_technical_columns = _hide_technical_columns
_core._BILINGUAL_HEADERS["key_channel"] = "Phạm vi áp dụng (KEY Channel)"
_core._BILINGUAL_HEADERS["channel"] = "Kênh chương trình (Channel)"

for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

_prepare_action_sheet = _core._prepare_action_sheet
_filter_selected_columns = _core._filter_selected_columns
_add_work_tracking_columns = _core._add_work_tracking_columns
_hide_technical_columns = _core._hide_technical_columns
_BILINGUAL_HEADERS = _core._BILINGUAL_HEADERS
