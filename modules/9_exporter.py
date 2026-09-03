# -*- coding: utf-8 -*-
"""Exporter entrypoint with business-first layout and explicit channel fidelity."""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import sys

from openpyxl import load_workbook

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
_original_shelf_colors = _core._apply_alternating_shelf_colors
_original_export_final_report = _core.export_final_report

# Snapshot quality is an operational field, not a technical audit tail. Keep it
# adjacent to the other location fields in the user-first action layout.
if "pog_month_status" not in _performance.USER_ACTION_COLUMNS:
    _before = (
        _performance.USER_ACTION_COLUMNS.index("location_status")
        if "location_status" in _performance.USER_ACTION_COLUMNS
        else len(_performance.USER_ACTION_COLUMNS)
    )
    _performance.USER_ACTION_COLUMNS.insert(_before, "pog_month_status")

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


def _apply_alternating_shelf_colors(ws, df):
    """Keep shelf grouping, then visibly flag rows whose POG needs verification."""
    _original_shelf_colors(ws, df)
    if ws is None or df is None or df.empty or "location_needs_review" not in df.columns:
        return

    headers = [ws.cell(row=1, column=i).value for i in range(1, ws.max_column + 1)]
    review_fields = [
        field for field in (
            "location_completeness", "pog_month_status",
            "location_status", "location_needs_review",
        )
        if field in headers
    ]
    if not review_fields:
        return

    review_fill = _core.PatternFill(fill_type="solid", fgColor="FFC7CE")
    review_font = _core.Font(bold=True, color="9C0006")
    column_indexes = [headers.index(field) + 1 for field in review_fields]

    for excel_row, (_, row) in enumerate(df.iterrows(), start=2):
        value = row.get("location_needs_review")
        needs_review = (
            value is True
            or str(value).strip().lower() in {"true", "1", "yes"}
        )
        if not needs_review:
            continue
        for column in column_indexes:
            cell = ws.cell(row=excel_row, column=column)
            cell.fill = review_fill
            cell.font = review_font


def _append_pog_metadata_audit(output_path, metadata) -> None:
    """Preserve export control rows without presenting them as operational errors."""
    if metadata is None or metadata.empty:
        return
    workbook = load_workbook(output_path)
    sheet_name = "POG metadata"
    if sheet_name in workbook.sheetnames:
        del workbook[sheet_name]
    ws = workbook.create_sheet(sheet_name)
    columns = list(metadata.columns)
    ws.append(columns)
    for _, row in metadata.iterrows():
        values = []
        for column in columns:
            value = row[column]
            try:
                missing = bool(_core.pd.isna(value))
            except (TypeError, ValueError):
                missing = False
            values.append(None if missing else value)
        ws.append(values)
    ws.freeze_panes = "A2"
    if ws.max_row >= 1 and ws.max_column >= 1:
        ws.auto_filter.ref = ws.dimensions
    ws.sheet_state = "hidden"
    workbook.save(output_path)


def export_final_report(*args, **kwargs):
    """Export normal report and retain recognized POG control rows in hidden audit."""
    df_pog_review = kwargs.get("df_pog_review")
    if df_pog_review is None and len(args) > 11:
        df_pog_review = args[11]
    metadata = None
    if df_pog_review is not None:
        metadata = getattr(df_pog_review, "attrs", {}).get("pog_metadata")
    output_path = _original_export_final_report(*args, **kwargs)
    _append_pog_metadata_audit(output_path, metadata)
    return output_path


_core._hide_technical_columns = _hide_technical_columns
_core._apply_alternating_shelf_colors = _apply_alternating_shelf_colors
_core._BILINGUAL_HEADERS["key_channel"] = "Phạm vi áp dụng (KEY Channel)"
_core._BILINGUAL_HEADERS["channel"] = "Kênh chương trình (Channel)"

for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

# Keep facade wrappers after the core symbol export above.
_prepare_action_sheet = _core._prepare_action_sheet
_filter_selected_columns = _core._filter_selected_columns
_add_work_tracking_columns = _core._add_work_tracking_columns
_hide_technical_columns = _core._hide_technical_columns
_apply_alternating_shelf_colors = _core._apply_alternating_shelf_colors
_BILINGUAL_HEADERS = _core._BILINGUAL_HEADERS
