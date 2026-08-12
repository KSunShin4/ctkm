"""Phân bổ Tem R cho riêng các sản phẩm hết tồn trên cùng kệ."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import unicodedata

import math
import pandas as pd


REQUIRED_COLUMNS = ("STOREID", "POGCODE", "FIXELID", "LOCATIONID", "ITEMID", "ITEMNAME")


@dataclass(frozen=True)
class TemRPlan:
    rows: pd.DataFrame
    audit: pd.DataFrame
    exceptions: pd.DataFrame


def _as_stock(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        raw_stock = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(raw_stock) or raw_stock < 0:
        return None
    if raw_stock == 0:
        return 0
    # Tồn dương dạng quy đổi đơn vị (vd 0.166667 thùng) vẫn là còn hàng.
    return max(1, int(raw_stock))


def _as_location(value: Any) -> float | None:
    try:
        location = float(value)
    except (TypeError, ValueError):
        return None
    return location if math.isfinite(location) else None


def _clean_input(frame: pd.DataFrame, stock_column: str) -> pd.DataFrame:
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if stock_column not in frame.columns:
        missing.append(stock_column)
    if missing:
        raise ValueError("File Tem R thiếu cột bắt buộc: " + ", ".join(missing))

    df = frame.copy()
    # File mẫu có một dòng tiêu đề lặp lại; không coi đó là sản phẩm.
    df = df[df["ITEMID"].astype(str).str.strip().str.upper() != "ITEMID"].copy()
    df["_stock"] = df[stock_column].map(_as_stock)
    df["_location"] = df["LOCATIONID"].map(_as_location)
    df["_group"] = list(zip(
        df["STOREID"].fillna("").astype(str).str.strip(),
        df["POGCODE"].fillna("").astype(str).str.strip(),
        df["FIXELID"].fillna("").astype(str).str.strip(),
    ))
    return df.reset_index(drop=True)


def build_tem_r_plan(frame: pd.DataFrame, *, max_location_distance: float = 1, stock_column: str = "TỒN") -> TemRPlan:
    """Gán mã còn tồn cho vị trí tồn 0 và gom các mã thay giống nhau liền kề."""
    if max_location_distance <= 0:
        raise ValueError("max_location_distance phải lớn hơn 0")
    df = _clean_input(frame, stock_column)
    df["TEM R"] = pd.NA
    df["TEM_R_STATUS"] = pd.NA
    df["TEM_R_REPRESENTATIVE"] = pd.NA

    exceptions: list[dict[str, Any]] = []
    remaining: dict[int, int] = {}

    for _, group_frame in df.groupby("_group", sort=False):
        ordered = sorted(
            group_frame.index,
            key=lambda idx: (
                df.at[idx, "_location"] if not pd.isna(df.at[idx, "_location"]) else float("inf"),
                idx,
            ),
        )
        stock_by_item: dict[str, int] = {}
        source_by_item: dict[str, int] = {}
        source_locations: dict[str, list[float]] = {}
        own_positions_by_item: dict[str, int] = {}
        for source_idx in ordered:
            stock = df.at[source_idx, "_stock"]
            if pd.isna(stock):
                exceptions.append({"row": source_idx, "ITEMID": df.at[source_idx, "ITEMID"], "reason": "Thiếu hoặc sai tồn kho"})
                continue
            remaining[source_idx] = int(stock)
            if stock > 0:
                item = str(df.at[source_idx, "ITEMID"])
                # Tồn là tồn cấp cửa hàng và thường lặp lại trên nhiều dòng POG
                # của cùng mã; lấy giá trị lớn nhất, tuyệt đối không cộng lặp.
                stock_by_item[item] = max(stock_by_item.get(item, 0), int(stock))
                source_by_item.setdefault(item, source_idx)
                source_locations.setdefault(item, []).append(df.at[source_idx, "_location"])
                own_positions_by_item[item] = own_positions_by_item.get(item, 0) + 1
                df.at[source_idx, "TEM_R_STATUS"] = "Còn tồn - không cần Tem R"

        targets = [idx for idx in ordered if df.at[idx, "_stock"] == 0]
        invalid = [idx for idx in ordered if pd.isna(df.at[idx, "_stock"])]
        for idx in invalid:
            df.at[idx, "TEM_R_STATUS"] = "Thiếu hoặc sai tồn kho"

        if not targets:
            continue

        # Bước 1: chỉ điền các vị trí tồn 0, ưu tiên mã còn tồn gần nhất. Tồn là
        # tổng số vị trí nên phải trừ vị trí vốn có của chính mã trước khi thay.
        capacity = {
            item: max(0, stock - own_positions_by_item.get(item, 0))
            for item, stock in stock_by_item.items()
        }
        # Phân bổ theo khoảng cách trên toàn kệ. Không duyệt target từ trái sang
        # phải vì vị trí xa có thể chiếm mất đơn vị tồn cuối cùng trước vị trí
        # nằm sát sản phẩm nguồn.
        proposed: dict[int, str | None] = {idx: None for idx in targets}
        unassigned = set(targets)
        target_order = {idx: position for position, idx in enumerate(targets)}
        item_order = {item: position for position, item in enumerate(stock_by_item)}
        while unassigned:
            candidates = [
                (
                    min(
                        (abs(location - df.at[target_idx, "_location"])
                         for location in source_locations[item]
                         if not pd.isna(location) and not pd.isna(df.at[target_idx, "_location"])),
                        default=float("inf"),
                    ),
                    target_order[target_idx],
                    item_order[item],
                    target_idx,
                    item,
                )
                for target_idx in unassigned
                for item, count in capacity.items()
                if count > 0
            ]
            if not candidates:
                break
            _, _, _, target_idx, item = min(candidates)
            proposed[target_idx] = item
            capacity[item] -= 1
            unassigned.remove(target_idx)

        final_codes = [
            proposed.get(idx) if df.at[idx, "_stock"] == 0 else str(df.at[idx, "ITEMID"])
            for idx in ordered
        ]

        def is_contiguous(code: str) -> bool:
            positions = [position for position, value in enumerate(final_codes) if value == code]
            return not positions or positions == list(range(positions[0], positions[-1] + 1))

        needs_rearrangement = any(
            not is_contiguous(code) for code in {code for code in final_codes if code is not None}
        )

        if not needs_rearrangement:
            for source_idx in ordered:
                if df.at[source_idx, "_stock"] > 0:
                    remaining[source_idx] = max(0, int(df.at[source_idx, "_stock"]) - 1)
            for target_idx in targets:
                representative = proposed[target_idx]
                if representative is None:
                    df.at[target_idx, "TEM R"] = "KHÔNG CÓ SẢN PHẨM THAY THẾ"
                    df.at[target_idx, "TEM_R_STATUS"] = "Kệ không còn đủ tồn để thay"
                    exceptions.append({"row": target_idx, "ITEMID": df.at[target_idx, "ITEMID"], "reason": "Kệ không còn đủ tồn để thay"})
                    continue
                source_idx = source_by_item[representative]
                remaining[source_idx] = max(0, remaining[source_idx] - 1)
                df.at[target_idx, "TEM R"] = representative
                df.at[target_idx, "TEM_R_REPRESENTATIVE"] = representative
                df.at[target_idx, "TEM_R_STATUS"] = "Tồn 0 - mã thay đã nằm liền nhóm"
            continue

        # Bước 2: chỉ khi một mã bị tách thành nhiều cụm mới sắp xếp toàn kệ.
        # Chỉ gom lại các mã của bố cục đề xuất: mọi mã còn tồn vẫn giữ đủ vị
        # trí vốn có, không cho mã đầu tiên dùng tồn để lấp hết cả kệ.
        arranged_items: list[str] = []
        for item in stock_by_item:
            arranged_items.extend([item] * final_codes.count(item))
        arranged_items.extend(
            ["KHÔNG CÓ SẢN PHẨM THAY THẾ"] * final_codes.count(None)
        )

        for source_idx in ordered:
            if df.at[source_idx, "_stock"] > 0:
                remaining[source_idx] = int(df.at[source_idx, "_stock"])

        for position, target_idx in enumerate(ordered):
            if position >= len(arranged_items):
                df.at[target_idx, "TEM R"] = "KHÔNG CÓ SẢN PHẨM THAY THẾ"
                df.at[target_idx, "TEM_R_STATUS"] = "Kệ không còn đủ tồn để sắp xếp"
                exceptions.append({"row": target_idx, "ITEMID": df.at[target_idx, "ITEMID"], "reason": "Kệ không còn đủ tồn để sắp xếp"})
                continue
            representative = arranged_items[position]
            df.at[target_idx, "TEM R"] = representative
            if representative == "KHÔNG CÓ SẢN PHẨM THAY THẾ":
                df.at[target_idx, "TEM_R_STATUS"] = "Kệ không còn đủ tồn để sắp xếp"
                exceptions.append({"row": target_idx, "ITEMID": df.at[target_idx, "ITEMID"], "reason": "Kệ không còn đủ tồn để sắp xếp"})
            else:
                source_idx = source_by_item[representative]
                remaining[source_idx] -= 1
                df.at[target_idx, "TEM_R_REPRESENTATIVE"] = representative
                df.at[target_idx, "TEM_R_STATUS"] = "Sắp xếp lại toàn kệ - gom mã P liền nhau"

    audit_columns = ["ITEMID", "ITEMNAME", "STOREID", "POGCODE", "FIXELID", "LOCATIONID", stock_column, "TEM R", "TEM_R_STATUS"]
    audit = df.loc[:, audit_columns].copy()
    audit["NĂNG_LỰC_CÒN_LẠI"] = [
        remaining.get(idx, pd.NA)
        if not pd.isna(df.at[idx, "_stock"]) and df.at[idx, "_stock"] != 0
        else pd.NA
        for idx in df.index
    ]
    exception_frame = pd.DataFrame(exceptions, columns=["row", "ITEMID", "reason"])
    return TemRPlan(rows=df, audit=audit, exceptions=exception_frame)


def _find_export_sheet_and_header(workbook, itemid_column: str = "ITEMID", *, allow_fallback: bool = False):
    preferred = workbook["Export"] if "Export" in workbook.sheetnames else workbook.active
    worksheets = [preferred, *(sheet for sheet in workbook.worksheets if sheet != preferred)]
    worksheet = preferred
    header_row = None
    wanted = itemid_column.strip().upper()
    for candidate_sheet in worksheets:
        found = next(
            (row for row in range(1, min(50, candidate_sheet.max_row) + 1)
             if any(str(candidate_sheet.cell(row, col).value).strip().upper() == wanted
                    for col in range(1, candidate_sheet.max_column + 1))),
            None,
        )
        if found is not None:
            worksheet, header_row = candidate_sheet, found
            break
    if header_row is None and allow_fallback:
        scored_rows = []
        for candidate_sheet in worksheets:
            for row in range(1, min(50, candidate_sheet.max_row) + 1):
                values = [candidate_sheet.cell(row, col).value for col in range(1, candidate_sheet.max_column + 1)]
                nonempty = [value for value in values if value not in (None, "")]
                text_cells = sum(isinstance(value, str) for value in nonempty)
                # A header normally has several populated text cells. Prefer that over title/data rows.
                scored_rows.append(((text_cells, len(nonempty)), candidate_sheet, row))
        if scored_rows:
            score, worksheet, header_row = max(scored_rows, key=lambda item: item[0])
            if score[1] < 2:
                header_row = None
    if header_row is None:
        raise ValueError(
            f"Không tìm thấy dòng tiêu đề/cột {itemid_column} trong 50 dòng đầu của các sheet file Tem R"
        )
    headers = [worksheet.cell(header_row, col).value for col in range(1, worksheet.max_column + 1)]
    return worksheet, header_row, headers


def inspect_tem_r_workbook(input_path: str | Path) -> dict:
    """List columns and suggest, but never silently choose, a stock column."""
    from openpyxl import load_workbook

    workbook = load_workbook(input_path, read_only=True, data_only=True)
    def normalized(value: str) -> str:
        value = unicodedata.normalize("NFD", value.lower())
        return "".join(char for char in value if unicodedata.category(char) != "Mn").replace(" ", "")

    preferred = ("ton", "tonkho", "stock", "onhand", "inventory", "quantity", "qty")
    sheet_options = []
    for worksheet in workbook.worksheets:
        exact_row = next(
            (row for row in range(1, min(50, worksheet.max_row) + 1)
             if any(str(worksheet.cell(row, col).value).strip().upper() == "ITEMID"
                    for col in range(1, worksheet.max_column + 1))), None,
        )
        if exact_row is None:
            rows = range(1, min(50, worksheet.max_row) + 1)
            exact_row = max(rows, key=lambda row: sum(
                isinstance(worksheet.cell(row, col).value, str) and bool(str(worksheet.cell(row, col).value).strip())
                for col in range(1, worksheet.max_column + 1)
            ), default=None)
        headers = [worksheet.cell(exact_row, col).value for col in range(1, worksheet.max_column + 1)] if exact_row else []
        columns = [str(value).strip() for value in headers if value is not None and str(value).strip()]
        stock = next((column for column in columns if normalized(column) in preferred), None)
        if stock is None:
            stock = next((column for column in columns if any(word in normalized(column) for word in preferred)), None)
        item = next((column for column in columns if normalized(column) in ("itemid", "map", "masanpham", "mahang")), None)
        exact_required = sum(column in columns for column in REQUIRED_COLUMNS)
        sheet_options.append({
            "sheet_name": worksheet.title, "header_row": exact_row, "columns": columns,
            "suggested_item_column": item, "suggested_stock_column": stock,
            "_score": (100 if item else 0) + (100 if stock else 0) + exact_required,
        })
    usable = [option for option in sheet_options if option["columns"]]
    if not usable:
        workbook.close()
        raise ValueError("Không tìm thấy dòng tiêu đề có dữ liệu trong 50 dòng đầu của các sheet")
    selected = max(usable, key=lambda option: option["_score"])
    for option in sheet_options:
        option.pop("_score", None)
    workbook.close()
    return {**selected, "sheet_options": sheet_options}


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
    """Điền cột ``TEM R`` của file mẫu và thêm sheet audit, giữ nguyên layout gốc."""
    from openpyxl import load_workbook
    from openpyxl.styles import PatternFill

    input_path, output_path = Path(input_path), Path(output_path)
    # Keep the original workbook for output, but read cached results for formula-based stock columns.
    workbook = load_workbook(input_path)
    value_workbook = load_workbook(input_path, data_only=True)
    itemid_column = (column_mapping or {}).get("ITEMID", "ITEMID")
    if sheet_name:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Không tìm thấy sheet đã chọn: {sheet_name}")
        worksheet = workbook[sheet_name]
        value_worksheet = value_workbook[sheet_name]
        if not header_row:
            _, header_row, headers = _find_export_sheet_and_header(workbook, itemid_column=itemid_column)
        else:
            headers = [worksheet.cell(header_row, col).value for col in range(1, worksheet.max_column + 1)]
    else:
        worksheet, header_row, headers = _find_export_sheet_and_header(workbook, itemid_column=itemid_column)
        value_worksheet = value_workbook[worksheet.title]
    records = []
    for excel_row in range(header_row + 1, worksheet.max_row + 1):
        values = [value_worksheet.cell(excel_row, col).value for col in range(1, worksheet.max_column + 1)]
        if all(value is None for value in values):
            continue
        record = dict(zip(headers, values))
        record["_excel_row"] = excel_row
        records.append(record)
    frame = pd.DataFrame(records)
    mapping = {
        canonical: source
        for canonical, source in (column_mapping or {}).items()
        if canonical in REQUIRED_COLUMNS and source
    }
    missing_sources = sorted({source for source in mapping.values() if source not in frame.columns})
    if missing_sources:
        raise ValueError("Không tìm thấy cột đã chọn: " + ", ".join(missing_sources))
    duplicate_sources = sorted({source for source in mapping.values() if list(mapping.values()).count(source) > 1})
    if duplicate_sources:
        raise ValueError("Mỗi cột nguồn chỉ được chọn một lần: " + ", ".join(duplicate_sources))
    for canonical, source in mapping.items():
        if canonical != source:
            frame[canonical] = frame[source]
    plan = build_tem_r_plan(frame, max_location_distance=max_location_distance, stock_column=stock_column)

    tem_r_col = headers.index("TEM R") + 1 if "TEM R" in headers else worksheet.max_column + 1
    if "TEM R" not in headers:
        worksheet.cell(header_row, tem_r_col, "TEM R")
    for _, row in plan.rows.iterrows():
        value = row["TEM R"]
        # Gán qua thuộc tính để xóa được Tem R cũ ở các dòng nay không còn thay đổi.
        worksheet.cell(int(row["_excel_row"]), tem_r_col).value = None if pd.isna(value) else str(value)

    # Tô cùng màu cho toàn bộ dòng trong một kệ, đổi màu luân phiên khi sang kệ.
    shelf_colors = ("EAF3FF", "FFF4E5")
    shelf_color_index: dict[tuple, int] = {}
    for _, row in plan.rows.iterrows():
        group = row["_group"]
        if group not in shelf_color_index:
            shelf_color_index[group] = len(shelf_color_index) % len(shelf_colors)
        fill = PatternFill(fill_type="solid", fgColor=shelf_colors[shelf_color_index[group]])
        excel_row = int(row["_excel_row"])
        for column in range(1, max(worksheet.max_column, tem_r_col) + 1):
            worksheet.cell(excel_row, column).fill = fill

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
    value_workbook.close()
    return plan
