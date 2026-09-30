"""Tem R facade with store-level inventory capacity fixes.

Workbook IO/hardening stays in ``tem_r_core.py``. This facade replaces the
allocation step so a store-level stock value cannot be spent again on each shelf.
Rows with missing/error stock remain visible for audit but are excluded from the
allocation problem entirely.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any

import pandas as pd


_CORE_MODULE_NAME = "_ctkm_tem_r_core"
_CORE_PATH = Path(__file__).with_name("tem_r_core.py")

if _CORE_MODULE_NAME in sys.modules:
    _core = sys.modules[_CORE_MODULE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(_CORE_MODULE_NAME, _CORE_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Không nạp được Tem R core: {_CORE_PATH}")
    _core = importlib.util.module_from_spec(_spec)
    sys.modules[_CORE_MODULE_NAME] = _core
    _spec.loader.exec_module(_core)

# Preserve the existing public/helper surface for backend code and tests.
for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)


def _excel_row_for_index(df: pd.DataFrame, idx: int) -> int:
    """Return the real source Excel row when lineage is available."""
    if "_excel_row" in df.columns:
        value = df.at[idx, "_excel_row"]
        try:
            if not pd.isna(value):
                return int(value)
        except (TypeError, ValueError):
            pass
    return int(idx) + 2


def build_tem_r_plan(
    frame: pd.DataFrame,
    *,
    max_location_distance: float = 1,
    stock_column: str = "TỒN",
) -> TemRPlan:
    """Use the single hardened Tem R allocator from tem_r_core."""
    return _core.build_tem_r_plan(
        frame,
        max_location_distance=max_location_distance,
        stock_column=stock_column,
    )


# create_tem_r_workbook calls the hardened core allocator through this facade.


def create_tem_r_workbook(
    input_path: str | Path,
    output_path: str | Path,
    *,
    max_location_distance: float = 1,
    stock_column: str = "TỒN",
    column_mapping: dict[str, str] | None = None,
    sheet_name: str | None = None,
    header_row: int | None = None,
) -> TemRPlan:
    """Create Tem R from cached/displayed Excel values only.

    Formula expressions and external-link formulas are intentionally ignored.
    The workbook is opened once with ``data_only=True`` so mapped fields use the
    same values a user sees in Excel. When a formula has no cached result, the
    existing Tem R validation treats it as missing data instead of guessing.
    """
    from openpyxl import load_workbook
    from openpyxl.styles import PatternFill

    input_path, output_path = _validate_xlsx_file(input_path), Path(output_path)
    workbook = load_workbook(input_path, data_only=True, keep_links=False)
    itemid_column = (column_mapping or {}).get("ITEMID", "ITEMID")

    if sheet_name:
        if sheet_name not in workbook.sheetnames:
            workbook.close()
            raise ValueError(f"Không tìm thấy sheet đã chọn: {sheet_name}")
        worksheet = workbook[sheet_name]
        max_row, _ = _sheet_bounds(worksheet)
        if header_row is not None and not (1 <= header_row <= max_row):
            workbook.close()
            raise ValueError(
                f"Dòng tiêu đề {header_row} không hợp lệ cho sheet '{sheet_name}' "
                f"(sheet có {max_row} dòng)."
            )
        if not header_row:
            header_row = _find_header_row(
                worksheet,
                itemid_column=itemid_column,
                allow_fallback=False,
            )
            if header_row is None:
                workbook.close()
                raise ValueError(
                    f"Không tìm thấy dòng tiêu đề/cột {itemid_column} trong {HEADER_SCAN_ROWS} "
                    f"dòng đầu của sheet '{sheet_name}'"
                )
        headers = _header_values(worksheet, header_row)
    else:
        worksheet, header_row, headers = _find_export_sheet_and_header(
            workbook, itemid_column=itemid_column
        )

    _validate_headers(headers, worksheet.title)
    headers = [
        _clean_header(value) or f"__unnamed_col_{index}"
        for index, value in enumerate(headers)
    ]
    data_column_count = len(headers)
    records = []
    for excel_row in range(header_row + 1, worksheet.max_row + 1):
        values = [
            worksheet.cell(excel_row, col).value
            for col in range(1, data_column_count + 1)
        ]
        if all(value is None for value in values):
            continue
        record = dict(zip(headers, values))
        record["_excel_row"] = excel_row
        records.append(record)

    frame = pd.DataFrame(records)
    if frame.empty:
        workbook.close()
        raise ValueError(f"Sheet '{worksheet.title}' không có dòng dữ liệu nào dưới tiêu đề.")

    mapping = {
        canonical: source
        for canonical, source in (column_mapping or {}).items()
        if canonical in REQUIRED_COLUMNS and source
    }
    missing_sources = sorted({source for source in mapping.values() if source not in frame.columns})
    if missing_sources:
        workbook.close()
        raise ValueError("Không tìm thấy cột đã chọn: " + ", ".join(missing_sources))
    duplicate_sources = sorted({
        source for source in mapping.values()
        if list(mapping.values()).count(source) > 1
    })
    if duplicate_sources:
        workbook.close()
        raise ValueError("Mỗi cột nguồn chỉ được chọn một lần: " + ", ".join(duplicate_sources))
    if stock_column in mapping.values():
        canonical = next(name for name, source in mapping.items() if source == stock_column)
        workbook.close()
        raise ValueError(
            f"Cột tồn kho '{stock_column}' đang đồng thời được dùng cho {canonical}. "
            "Hãy chọn hai cột khác nhau."
        )
    for canonical, source in mapping.items():
        if canonical != source:
            frame[canonical] = frame[source]
    missing_required = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_required:
        workbook.close()
        raise ValueError(
            "Chưa ánh xạ đủ cột bắt buộc cho Tem R: " + ", ".join(missing_required)
        )

    stock_col_index = headers.index(stock_column) + 1 if stock_column in headers else None
    plan = build_tem_r_plan(
        frame,
        max_location_distance=max_location_distance,
        stock_column=stock_column,
    )

    tem_r_col = headers.index("TEM R") + 1 if "TEM R" in headers else data_column_count + 1
    if "TEM R" not in headers:
        worksheet.cell(header_row, tem_r_col, "TEM R")
    for _, row in plan.rows.iterrows():
        value = row["TEM R"]
        worksheet.cell(int(row["_excel_row"]), tem_r_col).value = (
            None if pd.isna(value) else str(value)
        )

    # Chỉ tô cột TEM R để không ghi đè màu cảnh báo/định dạng gốc của file.
    shelf_colors = ("EAF3FF", "FFF4E5")
    shelf_color_index: dict[tuple, int] = {}
    for _, row in plan.rows.iterrows():
        group = row["_group"]
        if group not in shelf_color_index:
            shelf_color_index[group] = len(shelf_color_index) % len(shelf_colors)
        stock_is_unusable = pd.isna(row["_stock"])
        fill = PatternFill(
            fill_type="solid",
            fgColor="FCE4D6" if stock_is_unusable else shelf_colors[shelf_color_index[group]],
        )
        excel_row = int(row["_excel_row"])
        worksheet.cell(excel_row, tem_r_col).fill = fill
        if stock_is_unusable and stock_col_index:
            worksheet.cell(excel_row, stock_col_index).fill = fill

    for name in ("Tem R phân bổ", "Tem R theo kệ", "Tem R ngoại lệ"):
        if name in workbook.sheetnames:
            del workbook[name]
    audit_sheet = workbook.create_sheet("Tem R phân bổ")
    for row in [list(plan.audit.columns), *plan.audit.fillna("").values.tolist()]:
        audit_sheet.append(row)
    exception_sheet = workbook.create_sheet("Tem R ngoại lệ")
    for row in [list(plan.exceptions.columns), *plan.exceptions.fillna("").values.tolist()]:
        exception_sheet.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
    workbook.close()
    return plan


inspect_tem_r_workbook = _core.inspect_tem_r_workbook
