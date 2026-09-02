"""Phân bổ Tem R cho riêng các sản phẩm hết tồn trên cùng kệ."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import unicodedata
import zipfile

import math
import pandas as pd


REQUIRED_COLUMNS = ("STOREID", "POGCODE", "FIXELID", "LOCATIONID", "ITEMID", "ITEMNAME")
HEADER_SCAN_ROWS = 100
EXCEL_ERROR_VALUES = {"#N/A", "#VALUE!", "#REF!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!"}
STOCK_SKIP_NO_DATA = "BỎ QUA - KHÔNG CÓ DỮ LIỆU TỒN KHO"
STOCK_SKIP_INVALID = "BỎ QUA - TỒN KHO KHÔNG HỢP LỆ"


def _validate_xlsx_file(input_path: str | Path) -> Path:
    path = Path(input_path)
    if not path.exists() or not path.is_file():
        raise ValueError(f"Không tìm thấy file Tem R: {path.name}")
    if path.stat().st_size == 0:
        raise ValueError("File Tem R đang rỗng.")
    if not zipfile.is_zipfile(path):
        raise ValueError(
            "File Tem R không phải XLSX hợp lệ; file có thể bị hỏng, "
            "đặt sai đuôi hoặc đang dùng định dạng XLS/XLSB."
        )
    return path


def _clean_header(value: Any) -> str:
    return " ".join(str(value).replace("\xa0", " ").split()) if value is not None else ""


def _validate_headers(headers: list[Any], sheet_name: str) -> None:
    cleaned = [_clean_header(value) for value in headers if _clean_header(value)]
    duplicates = sorted({value for value in cleaned if cleaned.count(value) > 1})
    if duplicates:
        raise ValueError(
            f"Sheet '{sheet_name}' có tên cột bị trùng: {', '.join(duplicates)}. "
            "Hãy đổi thành các tên cột khác nhau trước khi chạy Tem R."
        )


@dataclass(frozen=True)
class TemRPlan:
    rows: pd.DataFrame
    audit: pd.DataFrame
    exceptions: pd.DataFrame


def _as_stock(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            raw_stock = float(value)
        else:
            text = str(value).strip().replace("\xa0", "").replace(" ", "")
            if not text or text.upper() in EXCEL_ERROR_VALUES | {"NA", "N/A", "NULL", "NONE", "<NA>"}:
                return None
            if "," in text and "." in text:
                decimal_mark = "," if text.rfind(",") > text.rfind(".") else "."
                thousands_mark = "." if decimal_mark == "," else ","
                text = text.replace(thousands_mark, "").replace(decimal_mark, ".")
            elif "," in text or "." in text:
                mark = "," if "," in text else "."
                parts = text.split(mark)
                if len(parts) > 2:
                    if not all(part.isdigit() and (index == 0 or len(part) == 3)
                               for index, part in enumerate(parts)):
                        return None
                    text = "".join(parts)
                elif len(parts) == 2:
                    left, right = parts
                    # 1,000 / 1.000 are thousands; 0.166 and 2,5 are decimals.
                    if len(right) == 3 and left not in ("0", "+0", "-0"):
                        text = left + right
                    else:
                        text = left + "." + right
            raw_stock = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(raw_stock) or raw_stock < 0:
        return None
    if raw_stock == 0:
        return 0
    # Tồn dương dạng quy đổi đơn vị (vd 0.166667 thùng) vẫn là còn hàng.
    return max(1, int(raw_stock))


def _stock_skip_details(value: Any) -> tuple[str, str]:
    """Return the visible marker and audit reason for an unusable stock value."""
    if value is None:
        return STOCK_SKIP_NO_DATA, "Bỏ qua - không có dữ liệu tồn kho"
    try:
        if pd.isna(value):
            return STOCK_SKIP_NO_DATA, "Bỏ qua - không có dữ liệu tồn kho"
    except (TypeError, ValueError):
        pass

    text = str(value).strip().upper()
    if text in EXCEL_ERROR_VALUES:
        marker = f"BỎ QUA - TỒN KHO LỖI {text}"
        return marker, f"Bỏ qua - tồn kho lỗi {text}"
    if not text or text in {"NA", "N/A", "NULL", "NONE", "<NA>", "NAN"}:
        return STOCK_SKIP_NO_DATA, "Bỏ qua - không có dữ liệu tồn kho"
    return STOCK_SKIP_INVALID, "Bỏ qua - tồn kho không hợp lệ"


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
    df["ITEMID"] = df["ITEMID"].map(
        lambda value: str(value).strip().upper()
        if value is not None and not pd.isna(value) and str(value).strip()
        and str(value).strip().upper() not in ("NAN", "NONE", "#N/A", "#REF!", "#VALUE!")
        else None
    )
    df["_stock"] = df[stock_column].map(_as_stock)
    stock_skip_details = df[stock_column].map(_stock_skip_details)
    df["_stock_skip_marker"] = stock_skip_details.map(lambda details: details[0])
    df["_stock_skip_reason"] = stock_skip_details.map(lambda details: details[1])
    df["_location"] = df["LOCATIONID"].map(_as_location)
    df["_group"] = list(zip(
        df["STOREID"].fillna("").astype(str).str.strip(),
        df["POGCODE"].fillna("").astype(str).str.strip(),
        df["FIXELID"].fillna("").astype(str).str.strip(),
    ))
    df["_input_error"] = pd.NA
    required_checks = (
        ("STOREID", "Thiếu mã cửa hàng"),
        ("POGCODE", "Thiếu mã POG"),
        ("FIXELID", "Thiếu mã kệ"),
        ("ITEMID", "Thiếu hoặc sai mã sản phẩm"),
    )
    for column, reason in required_checks:
        invalid = df[column].isna() | df[column].astype(str).str.strip().isin(("", "nan", "None"))
        df.loc[invalid & df["_input_error"].isna(), "_input_error"] = reason
    df.loc[df["_location"].isna() & df["_input_error"].isna(), "_input_error"] = "Thiếu hoặc sai vị trí kệ"
    invalid_stock = df["_stock"].isna() & df["_input_error"].isna()
    df.loc[invalid_stock, "_input_error"] = df.loc[invalid_stock, "_stock_skip_reason"]
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

    invalid_rows = df.index[df["_input_error"].notna()].tolist()
    for idx in invalid_rows:
        reason = str(df.at[idx, "_input_error"])
        df.at[idx, "TEM_R_STATUS"] = reason
        if pd.isna(df.at[idx, "_stock"]):
            df.at[idx, "TEM R"] = df.at[idx, "_stock_skip_marker"]
        excel_row = df.at[idx, "_excel_row"] if "_excel_row" in df.columns else idx + 2
        exceptions.append({"row": int(excel_row), "ITEMID": df.at[idx, "ITEMID"], "reason": reason})

    valid_df = df[df["_input_error"].isna()]
    for _, group_frame in valid_df.groupby("_group", sort=False):
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
                and min(
                    (abs(location - df.at[target_idx, "_location"])
                     for location in source_locations[item]),
                    default=float("inf"),
                ) <= max_location_distance
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

        if needs_rearrangement:
            arranged_preview: list[str] = []
            for item in stock_by_item:
                arranged_preview.extend([item] * final_codes.count(item))
            arranged_preview.extend(
                ["KHÔNG CÓ SẢN PHẨM THAY THẾ"] * final_codes.count(None)
            )
            # Sắp xếp toàn kệ không được biến thành cách lách giới hạn khoảng
            # cách. Nếu bất kỳ vị trí mới nào quá xa mã nguồn, giữ phương án
            # thay từng vị trí đã được kiểm tra khoảng cách ở trên.
            rearrangement_within_distance = all(
                representative == "KHÔNG CÓ SẢN PHẨM THAY THẾ"
                or min(
                    abs(location - df.at[target_idx, "_location"])
                    for location in source_locations[representative]
                ) <= max_location_distance
                for target_idx, representative in zip(ordered, arranged_preview)
            )
            if not rearrangement_within_distance:
                needs_rearrangement = False

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
            (row for row in range(1, min(HEADER_SCAN_ROWS, candidate_sheet.max_row) + 1)
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
            for row in range(1, min(HEADER_SCAN_ROWS, candidate_sheet.max_row) + 1):
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
            f"Không tìm thấy dòng tiêu đề/cột {itemid_column} trong {HEADER_SCAN_ROWS} dòng đầu của các sheet file Tem R"
        )
    headers = [worksheet.cell(header_row, col).value for col in range(1, worksheet.max_column + 1)]
    _validate_headers(headers, worksheet.title)
    return worksheet, header_row, headers


def inspect_tem_r_workbook(input_path: str | Path) -> dict:
    """List columns and suggest, but never silently choose, a stock column."""
    from openpyxl import load_workbook

    input_path = _validate_xlsx_file(input_path)
    try:
        # Tem R never needs external workbook links. Some vendor exports contain
        # malformed externalLink XML, so do not parse or preserve those links.
        workbook = load_workbook(input_path, read_only=True, data_only=True, keep_links=False)
    except Exception as exc:
        message = str(exc).lower()
        if "encrypt" in message or "password" in message:
            raise ValueError("File Tem R đang được mã hóa/đặt mật khẩu. Hãy bỏ mật khẩu rồi tải lại.") from exc
        raise ValueError(f"Không thể mở file Tem R; file có thể bị hỏng: {exc}") from exc
    def normalized(value: str) -> str:
        value = unicodedata.normalize("NFD", value.lower())
        return "".join(char for char in value if unicodedata.category(char) != "Mn").replace(" ", "")

    preferred = ("ton", "tonkho", "stock", "onhand", "inventory", "quantity", "qty")
    sheet_options = []
    for worksheet in workbook.worksheets:
        # A number of POG exports omit the worksheet dimension element.  The
        # cells are valid, but read-only openpyxl then reports max_row/max_column
        # as None until it calculates the real bounds.
        if worksheet.max_row is None or worksheet.max_column is None:
            worksheet.calculate_dimension(force=True)
        max_row = worksheet.max_row or 0
        max_column = worksheet.max_column or 0
        exact_row = next(
            (row for row in range(1, min(HEADER_SCAN_ROWS, max_row) + 1)
             if any(str(worksheet.cell(row, col).value).strip().upper() == "ITEMID"
                    for col in range(1, max_column + 1))), None,
        )
        if exact_row is None:
            rows = range(1, min(HEADER_SCAN_ROWS, max_row) + 1)
            exact_row = max(rows, key=lambda row: sum(
                isinstance(worksheet.cell(row, col).value, str) and bool(str(worksheet.cell(row, col).value).strip())
                for col in range(1, max_column + 1)
            ), default=None)
        headers = [worksheet.cell(exact_row, col).value for col in range(1, max_column + 1)] if exact_row else []
        try:
            _validate_headers(headers, worksheet.title)
        except ValueError as exc:
            sheet_options.append({
                "sheet_name": worksheet.title, "header_row": exact_row, "columns": [],
                "suggested_item_column": None, "suggested_stock_column": None,
                "error": str(exc), "_score": -1,
            })
            continue
        columns = [_clean_header(value) for value in headers if _clean_header(value)]
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
        errors = [option.get("error") for option in sheet_options if option.get("error")]
        if errors:
            raise ValueError(errors[0])
        raise ValueError(
            f"Không tìm thấy dòng tiêu đề có dữ liệu trong {HEADER_SCAN_ROWS} dòng đầu của các sheet"
        )
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

    input_path, output_path = _validate_xlsx_file(input_path), Path(output_path)
    # Keep the original workbook for output, but read cached results for formula-based stock columns.
    # External workbook links are not needed by Tem R and may contain malformed XML
    # in exports from third-party systems, so explicitly skip them in both loads.
    workbook = load_workbook(input_path, keep_links=False)
    value_workbook = load_workbook(input_path, data_only=True, keep_links=False)
    itemid_column = (column_mapping or {}).get("ITEMID", "ITEMID")
    if sheet_name:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Không tìm thấy sheet đã chọn: {sheet_name}")
        worksheet = workbook[sheet_name]
        value_worksheet = value_workbook[sheet_name]
        if header_row is not None and not (1 <= header_row <= worksheet.max_row):
            raise ValueError(
                f"Dòng tiêu đề {header_row} không hợp lệ cho sheet '{sheet_name}' "
                f"(sheet có {worksheet.max_row} dòng)."
            )
        if not header_row:
            _, header_row, headers = _find_export_sheet_and_header(workbook, itemid_column=itemid_column)
        else:
            headers = [worksheet.cell(header_row, col).value for col in range(1, worksheet.max_column + 1)]
    else:
        worksheet, header_row, headers = _find_export_sheet_and_header(workbook, itemid_column=itemid_column)
        value_worksheet = value_workbook[worksheet.title]
    _validate_headers(headers, worksheet.title)
    headers = [
        _clean_header(value) or f"__unnamed_col_{index}"
        for index, value in enumerate(headers)
    ]
    records = []
    for excel_row in range(header_row + 1, worksheet.max_row + 1):
        values = [value_worksheet.cell(excel_row, col).value for col in range(1, worksheet.max_column + 1)]
        if all(value is None for value in values):
            continue
        record = dict(zip(headers, values))
        record["_excel_row"] = excel_row
        records.append(record)
    frame = pd.DataFrame(records)
    if frame.empty:
        raise ValueError(f"Sheet '{worksheet.title}' không có dòng dữ liệu nào dưới tiêu đề.")
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
    if stock_column in mapping.values():
        canonical = next(name for name, source in mapping.items() if source == stock_column)
        raise ValueError(
            f"Cột tồn kho '{stock_column}' đang đồng thời được dùng cho {canonical}. "
            "Hãy chọn hai cột khác nhau."
        )
    for canonical, source in mapping.items():
        if canonical != source:
            frame[canonical] = frame[source]
    missing_required = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_required:
        raise ValueError(
            "Chưa ánh xạ đủ cột bắt buộc cho Tem R: " + ", ".join(missing_required)
        )
    # Công thức chưa có cache hoặc trả về lỗi không được xem là tồn 0. Các dòng
    # này sẽ được cách ly, đánh dấu rõ trong cột TEM R và ghi vào sheet ngoại lệ;
    # những dòng có tồn hợp lệ vẫn tiếp tục được phân bổ bình thường.
    stock_col_index = headers.index(stock_column) + 1 if stock_column in headers else None
    plan = build_tem_r_plan(frame, max_location_distance=max_location_distance, stock_column=stock_column)

    tem_r_col = headers.index("TEM R") + 1 if "TEM R" in headers else worksheet.max_column + 1
    if "TEM R" not in headers:
        worksheet.cell(header_row, tem_r_col, "TEM R")
    for _, row in plan.rows.iterrows():
        value = row["TEM R"]
        # Gán qua thuộc tính để xóa được Tem R cũ ở các dòng nay không còn thay đổi.
        worksheet.cell(int(row["_excel_row"]), tem_r_col).value = None if pd.isna(value) else str(value)

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
    value_workbook.close()
    return plan
