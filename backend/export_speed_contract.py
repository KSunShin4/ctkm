# -*- coding: utf-8 -*-
"""Bound the CPU cost of CTKM workbook presentation on very small runtimes.

The production workbook can contain the same operational rows in several audit /
action views. Styling every populated cell in every view is therefore much more
expensive than writing the business data itself on a 0.1 CPU Render instance.

This contract keeps workbook/business semantics intact while making presentation
cost proportional to columns plus a few editable/diagnostic ranges instead of
rows * columns:

* style only header cells directly;
* use worksheet default row height instead of touching every row dimension;
* size columns from headers plus a small dataframe sample;
* use conditional-formatting ranges for action/review/collision emphasis instead
  of assigning fills/fonts to every data cell;
* retain validation/protection for pharmacist-editable fields;
* make the historical second shelf-colour pass a no-op.

No dataframe values, sheet names, row counts, mappings, task identities, summary
metrics, audit fields or source values are modified here.
"""
from __future__ import annotations

import pandas as pd
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter


_ACTION_SHEETS = {"Gắn tem", "Tháo tem", "Chờ gắn", "Cần review"}
_COLOR_MAP = {
    "Tong hop": "4F81BD",
    "CTKM thieu vi tri ke": "C0504D",
    "Gắn tem": "2E7D32",
    "Tháo tem": "F28C00",
    "Chờ gắn": "C79B00",
    "Cần review": "7030A0",
    "Audit hành động": "5B5EA6",
    "POG không có CTKM": "9BBB59",
    "POG cần review": "C65911",
    "POG cần kiểm tra": "C0504D",
    "Canh bao trung thoi gian": "C79B00",
    "Xác nhận CTKM Clearance": "00A6A6",
    "Mapping log": "5B5EA6",
    "Tom tat": "6F42C1",
}
_COLLISION_FIELDS = (
    "promotion_count_at_position", "has_multiple_promotions_at_position",
)
_SAMPLE_ROWS_FOR_WIDTH = 80


def _column_widths(headers: list[str], df: pd.DataFrame | None) -> list[int]:
    widths = [max(10, len(header)) for header in headers]
    if df is None or getattr(df, "empty", True):
        return widths
    sample = df.head(_SAMPLE_ROWS_FOR_WIDTH)
    for index, _header in enumerate(headers):
        if index >= len(sample.columns):
            break
        try:
            lengths = sample.iloc[:, index].dropna().astype(str).str.len()
            if not lengths.empty:
                widths[index] = max(widths[index], int(lengths.max()))
        except Exception:
            pass
    return widths


def _add_formula_rule(ws, cell_range: str, formula: str, *, fill: str, font: str | None = None):
    kwargs = {"fill": PatternFill(fill_type="solid", fgColor=fill)}
    if font:
        kwargs["font"] = Font(bold=True, color=font)
    ws.conditional_formatting.add(cell_range, FormulaRule(formula=[formula], **kwargs))


def _optimized_professional_style(ws, sheet_name: str, df: pd.DataFrame | None = None):
    """Apply bounded-cost presentation; never iterate the full cell matrix."""
    if ws is None:
        return

    max_row = ws.max_row or 0
    max_col = ws.max_column or 0
    if max_col <= 0:
        return

    thin = Side(border_style="thin", color="D0D7DE")
    header_border = Border(bottom=thin)
    header_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    ws.freeze_panes = "C2" if sheet_name in _ACTION_SHEETS else "A2"
    ws.auto_filter.ref = ws.dimensions if max_row >= 1 else None
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "1:1"
    ws.sheet_properties.outlinePr.summaryBelow = True
    ws.sheet_properties.tabColor = _COLOR_MAP.get(sheet_name, "4F81BD")
    ws.sheet_format.defaultRowHeight = 22

    headers = ["" if cell.value is None else str(cell.value) for cell in ws[1]]
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = header_border

    widths = _column_widths(headers, df)
    for col_idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = min(60, max(12, width + 2))

    if max_row < 2:
        return

    last_col = get_column_letter(max_col)
    full_range = f"A2:{last_col}{max_row}"

    if sheet_name in _ACTION_SHEETS and "action" in headers:
        action_letter = get_column_letter(headers.index("action") + 1)
        _add_formula_rule(
            ws, full_range, f'ISNUMBER(SEARCH("gắn",${action_letter}2))', fill="E8F5E9"
        )
        _add_formula_rule(
            ws, full_range, f'ISNUMBER(SEARCH("tháo",${action_letter}2))', fill="FFF3E0"
        )

    completeness_header = (
        "location_completeness" if "location_completeness" in headers
        else "location_status" if "location_status" in headers else None
    )
    if completeness_header:
        letter = get_column_letter(headers.index(completeness_header) + 1)
        _add_formula_rule(
            ws, f"{letter}2:{letter}{max_row}",
            f'AND({letter}2<>"",{letter}2<>"Đủ vị trí",{letter}2<>"Không áp dụng POG")',
            fill="FFC7CE", font="9C0006",
        )

    if "pog_month_status" in headers:
        letter = get_column_letter(headers.index("pog_month_status") + 1)
        _add_formula_rule(
            ws, f"{letter}2:{letter}{max_row}",
            f'AND({letter}2<>"",{letter}2<>"POG đúng tháng",{letter}2<>"Không áp dụng POG")',
            fill="FFC7CE", font="9C0006",
        )

    if "location_needs_review" in headers:
        letter = get_column_letter(headers.index("location_needs_review") + 1)
        _add_formula_rule(
            ws, f"{letter}2:{letter}{max_row}", f"{letter}2=TRUE",
            fill="FFC7CE", font="9C0006",
        )

    for field in _COLLISION_FIELDS:
        if field not in headers:
            continue
        letter = get_column_letter(headers.index(field) + 1)
        formula = f"{letter}2=TRUE" if field.startswith("has_") else f"{letter}2>1"
        _add_formula_rule(
            ws, f"{letter}2:{letter}{max_row}", formula,
            fill="FFF2CC", font="7F6000",
        )


def _shelf_pass_already_applied(_ws, _df) -> None:
    return None


def _optimized_action_inputs(ws) -> None:
    headers = [str(cell.value or "") for cell in ws[1]]
    if "processing_status" not in headers:
        return
    status_col = headers.index("processing_status") + 1
    editable = [
        name for name in ("processing_status", "processed_by", "processed_at", "staff_note")
        if name in headers
    ]
    validation = DataValidation(
        type="list",
        formula1='"Chưa xử lý,Đã xong,Không tìm thấy,Không thực hiện được"',
        allow_blank=False,
    )
    validation.error = "Hãy chọn một trạng thái trong danh sách."
    validation.errorTitle = "Trạng thái không hợp lệ"
    ws.add_data_validation(validation)

    yellow_fill = PatternFill(fill_type="solid", fgColor="FFF2CC")
    unlocked = Protection(locked=False)
    if ws.max_row >= 2:
        status_letter = get_column_letter(status_col)
        validation.add(f"{status_letter}2:{status_letter}{ws.max_row}")
        full_range = f"A2:{get_column_letter(ws.max_column)}{ws.max_row}"
        _add_formula_rule(ws, full_range, f'${status_letter}2="Đã xong"', fill="E2F0D9")
        _add_formula_rule(ws, full_range, f'${status_letter}2="Không tìm thấy"', fill="FFC7CE")

    editable_indexes = [(name, headers.index(name) + 1) for name in editable]
    for row_idx in range(2, ws.max_row + 1):
        for name, col_idx in editable_indexes:
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.protection = unlocked
            cell.fill = yellow_fill
            if name == "processed_at":
                cell.number_format = "dd/mm/yyyy hh:mm"
    ws.protection.autoFilter = True
    ws.protection.sort = True
    ws.protection.sheet = True


def _optimized_confirmation_inputs(ws) -> None:
    headers = [str(cell.value or "") for cell in ws[1]]
    if "xac_nhan_ap_dung" not in headers:
        return
    confirm_col = headers.index("xac_nhan_ap_dung") + 1
    note_col = headers.index("ghi_chu_xac_nhan") + 1 if "ghi_chu_xac_nhan" in headers else None
    validation = DataValidation(
        type="list",
        formula1='"Chưa xác nhận,Áp dụng CTKM,Áp dụng Clearance,Áp dụng cả hai,Không áp dụng"',
        allow_blank=False,
    )
    validation.error = "Hãy chọn một trạng thái xác nhận trong danh sách."
    validation.errorTitle = "Trạng thái không hợp lệ"
    ws.add_data_validation(validation)

    yellow_fill = PatternFill(fill_type="solid", fgColor="FFF2CC")
    unlocked = Protection(locked=False)
    if ws.max_row >= 2:
        letter = get_column_letter(confirm_col)
        validation.add(f"{letter}2:{letter}{ws.max_row}")
        for row_idx in range(2, ws.max_row + 1):
            for col_idx in (confirm_col, note_col):
                if col_idx is None:
                    continue
                cell = ws.cell(row_idx, col_idx)
                cell.fill = yellow_fill
                cell.protection = unlocked
    ws.protection.autoFilter = True
    ws.protection.sort = True
    ws.protection.sheet = True


def install_export_speed_contract(core_module) -> None:
    if getattr(core_module.app.state, "export_speed_contract_v1", False):
        return
    main_core = getattr(core_module._main_mod, "_core", None)
    exporter = getattr(main_core, "EX", None) if main_core is not None else None
    exporter_core = getattr(exporter, "_core", None) if exporter is not None else None
    if exporter_core is None:
        raise RuntimeError("Export-speed contract không tìm thấy exporter core")

    _optimized_professional_style._ctkm_export_speed_contract_v1 = True
    _shelf_pass_already_applied._ctkm_export_speed_contract_v1 = True
    exporter_core._apply_professional_style = _optimized_professional_style
    exporter_core._apply_alternating_shelf_colors = _shelf_pass_already_applied
    exporter_core._configure_action_inputs = _optimized_action_inputs
    exporter_core._configure_confirmation_inputs = _optimized_confirmation_inputs

    exporter._apply_professional_style = _optimized_professional_style
    exporter._apply_alternating_shelf_colors = _shelf_pass_already_applied
    exporter._configure_action_inputs = _optimized_action_inputs
    exporter._configure_confirmation_inputs = _optimized_confirmation_inputs
    core_module.app.state.export_speed_contract_v1 = True
