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
_original_style = _core._apply_professional_style
_original_export_final_report = _core.export_final_report

# Comparison-only keys remain available for audit/code but should not clutter
# operational/confirmation sheets. Raw source/new codes stay visible instead.
for _field in ("new_item_key", "transition_match_key"):
    if _field not in _performance.TECHNICAL_ACTION_COLUMNS:
        _performance.TECHNICAL_ACTION_COLUMNS.append(_field)

# Keep the approved first five business columns untouched:
# KEY Channel -> Channel -> item_id -> item_name -> promo_uom.
# Replacement-code context remains visible, but starts only after product identity.
for _field in ("new_item_id", "item_code_transition_status"):
    if _field not in _performance.USER_ACTION_COLUMNS:
        _before = (
            _performance.USER_ACTION_COLUMNS.index("pog_code")
            if "pog_code" in _performance.USER_ACTION_COLUMNS
            else len(_performance.USER_ACTION_COLUMNS)
        )
        _performance.USER_ACTION_COLUMNS.insert(_before, _field)
if "pog_month_status" not in _performance.USER_ACTION_COLUMNS:
    _before = (
        _performance.USER_ACTION_COLUMNS.index("location_status")
        if "location_status" in _performance.USER_ACTION_COLUMNS
        else len(_performance.USER_ACTION_COLUMNS)
    )
    _performance.USER_ACTION_COLUMNS.insert(_before, "pog_month_status")
if "pog_applicable" not in _performance.USER_ACTION_COLUMNS:
    _before = (
        _performance.USER_ACTION_COLUMNS.index("location_completeness")
        if "location_completeness" in _performance.USER_ACTION_COLUMNS
        else len(_performance.USER_ACTION_COLUMNS)
    )
    _performance.USER_ACTION_COLUMNS.insert(_before, "pog_applicable")
for _field in ("matched_pog_item_id", "pog_match_code_type"):
    if _field not in _performance.USER_ACTION_COLUMNS:
        _before = (
            _performance.USER_ACTION_COLUMNS.index("store_id")
            if "store_id" in _performance.USER_ACTION_COLUMNS
            else len(_performance.USER_ACTION_COLUMNS)
        )
        _performance.USER_ACTION_COLUMNS.insert(_before, _field)
for _field in ("promotion_count_at_position", "has_multiple_promotions_at_position"):
    if _field not in _performance.USER_ACTION_COLUMNS:
        _before = (
            _performance.USER_ACTION_COLUMNS.index("location_completeness")
            if "location_completeness" in _performance.USER_ACTION_COLUMNS
            else len(_performance.USER_ACTION_COLUMNS)
        )
        _performance.USER_ACTION_COLUMNS.insert(_before, _field)

_core._prepare_action_sheet = _performance.prepare_action_sheet_user_first
_core._filter_selected_columns = _performance.filter_selected_columns_keep_channels
_core._add_work_tracking_columns = _performance.unique_work_tracking_rows


_USER_ACTION_SHEETS = {"Gắn tem", "Tháo tem", "Chờ gắn", "Cần review"}
_COLUMN_WIDTHS = {
    "key_channel": 18,
    "channel": 24,
    "item_id": 14,
    "item_name": 38,
    "promo_uom": 20,
    "new_item_id": 16,
    "item_code_transition_status": 22,
    "pog_code": 16,
    "location_id": 12,
    "facing": 10,
    "scheduled_action": 18,
    "action": 18,
    "ngay_gan_tem": 14,
    "ngay_thao_tem": 14,
    "so_ngay_con_lai": 14,
    "campaign_name": 28,
    "campaign_detail": 42,
    "promo_from": 14,
    "promo_to": 14,
    "normal_price": 14,
    "promo_price": 14,
    "program_source": 16,
    "reason": 36,
    "product_type": 16,
    "store_id": 14,
}
_HEADER_GROUPS = {
    "key_channel": "1F4E78",
    "channel": "1F4E78",
    "item_id": "2F75B5",
    "item_name": "2F75B5",
    "promo_uom": "2F75B5",
    "new_item_id": "2F75B5",
    "item_code_transition_status": "2F75B5",
    "pog_code": "5B9BD5",
    "location_id": "5B9BD5",
    "facing": "5B9BD5",
    "scheduled_action": "70AD47",
    "action": "70AD47",
    "ngay_gan_tem": "70AD47",
    "ngay_thao_tem": "70AD47",
    "so_ngay_con_lai": "70AD47",
    "campaign_name": "4472C4",
    "campaign_detail": "4472C4",
    "promo_from": "4472C4",
    "promo_to": "4472C4",
    "normal_price": "4472C4",
    "promo_price": "4472C4",
    "program_source": "7F8C8D",
    "reason": "C65911",
}


def _apply_runtime_header_labels() -> None:
    """Apply concise user labels immediately before each export.

    ctkm_performance also patches the shared header dictionary during startup, so
    these assignments run at export time to make the final workbook deterministic
    without changing any source values.
    """
    labels = {
        "key_channel": "KEY Channel",
        "channel": "Channel",
        "item_id": "Mã sản phẩm",
        "item_name": "Tên sản phẩm",
        "promo_uom": "Đơn vị sản phẩm (Promo UoM)",
        "pog_code": "POG",
        "location_id": "Vị trí",
        "facing": "Facing",
        "scheduled_action": "Action theo lịch",
        "action": "Action",
        "ngay_gan_tem": "Ngày gắn",
        "ngay_thao_tem": "Ngày tháo",
        "campaign_name": "Campaign",
        "campaign_detail": "Scheme detail",
        "promo_from": "From",
        "promo_to": "To",
        "normal_price": "Giá thường",
        "promo_price": "Giá KM",
        "program_source": "Nguồn",
        "reason": "Lý do / Cảnh báo",
        "new_item_id": "Mã mới (Item code 1 NEW / New P code)",
        "item_code_transition_status": "Trạng thái chuyển mã",
        "matched_pog_item_id": "Mã ITEMID thực tế trên POG",
        "pog_match_code_type": "POG khớp theo mã nào?",
        "pog_applicable": "Có áp dụng vị trí POG?",
        "promotion_count_at_position": "Số CTKM tại cùng vị trí",
        "has_multiple_promotions_at_position": "Nhiều CTKM cùng vị trí?",
    }
    _core._BILINGUAL_HEADERS.update(labels)


def _apply_user_output_style(ws, sheet_name: str, df=None):
    """Style user task sheets inside the existing ExcelWriter pass only."""
    _original_style(ws, sheet_name, df)
    if ws is None or sheet_name not in _USER_ACTION_SHEETS:
        return

    # HƯỚNG DẪN ordering remains owned by exporter_core. This function only
    # changes presentation of already-created task sheets and performs no IO.
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions if ws.max_row >= 1 and ws.max_column >= 1 else None
    ws.sheet_view.showGridLines = False

    raw_headers = [str(cell.value or "") for cell in ws[1]]
    for index, raw_header in enumerate(raw_headers, start=1):
        width = _COLUMN_WIDTHS.get(raw_header)
        if width:
            ws.column_dimensions[_core.get_column_letter(index)].width = width
        fill_color = _HEADER_GROUPS.get(raw_header)
        if fill_color:
            cell = ws.cell(row=1, column=index)
            cell.fill = _core.PatternFill(fill_type="solid", fgColor=fill_color)
            cell.font = _core.Font(bold=True, color="FFFFFF")


def _hide_technical_columns(ws, *, action_sheet=False):
    return _performance.hide_technical_columns(
        ws,
        get_column_letter=_core.get_column_letter,
        original_hide=_original_hide,
        action_sheet=action_sheet,
    )


def _truthy(value) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _apply_alternating_shelf_colors(ws, df):
    """Keep shelf grouping, then flag POG review and same-position promotions."""
    _original_shelf_colors(ws, df)
    if ws is None or df is None or df.empty:
        return

    headers = [ws.cell(row=1, column=i).value for i in range(1, ws.max_column + 1)]

    collision_fields = [
        field for field in (
            "promotion_count_at_position", "has_multiple_promotions_at_position",
        )
        if field in headers
    ]
    if collision_fields and "has_multiple_promotions_at_position" in df.columns:
        warning_fill = _core.PatternFill(fill_type="solid", fgColor="FFF2CC")
        warning_font = _core.Font(bold=True, color="7F6000")
        collision_columns = [headers.index(field) + 1 for field in collision_fields]
        for excel_row, (_, row) in enumerate(df.iterrows(), start=2):
            if not _truthy(row.get("has_multiple_promotions_at_position")):
                continue
            for column in collision_columns:
                cell = ws.cell(row=excel_row, column=column)
                cell.fill = warning_fill
                cell.font = warning_font

    if "location_needs_review" not in df.columns:
        return
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
        if not _truthy(row.get("location_needs_review")):
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


def _export_final_report_with_pog_metadata(*args, **kwargs):
    """Export once, then retain only the pre-existing hidden POG audit metadata."""
    _apply_runtime_header_labels()
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
_core._apply_professional_style = _apply_user_output_style
_core._apply_alternating_shelf_colors = _apply_alternating_shelf_colors
_apply_runtime_header_labels()

for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

export_final_report = _export_final_report_with_pog_metadata
_prepare_action_sheet = _core._prepare_action_sheet
_filter_selected_columns = _core._filter_selected_columns
_add_work_tracking_columns = _core._add_work_tracking_columns
_hide_technical_columns = _core._hide_technical_columns
_apply_professional_style = _core._apply_professional_style
_apply_alternating_shelf_colors = _core._apply_alternating_shelf_colors
_BILINGUAL_HEADERS = _core._BILINGUAL_HEADERS
