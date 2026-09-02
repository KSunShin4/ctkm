# -*- coding: utf-8 -*-
"""Module 1: Loader — doc tho moi sheet, trich pog_snapshot_month tu file POG."""
from __future__ import annotations
import io, re, zipfile
import itertools
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import openpyxl, pandas as pd
from openpyxl.utils.exceptions import InvalidFileException
from .config_loader import GARBAGE_CONFIG

@dataclass
class LoadedSheet:
    sheet_name: str
    header_row_index: int
    df: pd.DataFrame
    source_excel_rows: list[int] = field(default_factory=list)
    source_file: str = ""

@dataclass
class LoadedWorkbook:
    sheets: dict = field(default_factory=dict)
    pog_snapshot_month: Optional[str] = None

MAX_DATA_ROWS_PER_SHEET = 250_000
MAX_DATA_COLUMNS = 2_048
MAX_DATA_CELLS_PER_SHEET = 5_000_000

def _validate_xlsx_container(filepath: str) -> None:
    path = Path(filepath)
    if not path.exists() or not path.is_file():
        raise ValueError(f"Không tìm thấy file Excel: {path.name}")
    if path.stat().st_size == 0:
        raise ValueError(f"File Excel '{path.name}' đang rỗng.")
    if not zipfile.is_zipfile(path):
        raise ValueError(
            f"File '{path.name}' không phải XLSX hợp lệ. File có thể bị hỏng, "
            "đặt sai đuôi hoặc đang dùng định dạng XLS/XLSB."
        )

def _open_workbook_safely(filepath: str):
    _validate_xlsx_container(filepath)
    try:
        safe = _strip_broken_defined_names(filepath)
        # CTKM/POG processing never needs external workbook links. Some vendor
        # exports contain malformed externalLink XML even though worksheet data
        # itself is valid, so skip parsing those links just like the Tem R path.
        workbook = openpyxl.load_workbook(
            io.BytesIO(safe), data_only=True, read_only=True, keep_links=False
        )
    except (zipfile.BadZipFile, InvalidFileException, KeyError, OSError, ValueError) as exc:
        message = str(exc).lower()
        if "encrypt" in message or "password" in message or "agile" in message:
            raise ValueError(
                f"File Excel '{Path(filepath).name}' đang được mã hóa/đặt mật khẩu. "
                "Hãy bỏ mật khẩu rồi tải lại."
            ) from exc
        raise ValueError(
            f"Không thể mở file Excel '{Path(filepath).name}'. File có thể bị hỏng "
            "hoặc không đúng chuẩn XLSX: {exc}"
        ) from exc
    if not workbook.sheetnames:
        workbook.close()
        raise ValueError(f"File Excel '{Path(filepath).name}' không có sheet nào.")
    return workbook

def _strip_broken_defined_names(filepath: str) -> bytes:
    with open(filepath, "rb") as f:
        raw = f.read()
    buf = io.BytesIO(raw)
    try:
        zin = zipfile.ZipFile(buf, "r")
        data = {n: zin.read(n) for n in zin.namelist()}
        zin.close()
    except zipfile.BadZipFile:
        return raw
    if "xl/workbook.xml" not in data:
        return raw
    wb_xml = data["xl/workbook.xml"].decode("utf-8", errors="ignore")
    if "<definedNames>" not in wb_xml:
        return raw
    data["xl/workbook.xml"] = re.sub(r"<definedNames>.*?</definedNames>", "", wb_xml, flags=re.DOTALL).encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for n, c in data.items():
            zout.writestr(n, c)
    return out.getvalue()

def _detect_header_row(ws, scan_n, min_ratio) -> int:
    max_row = ws.max_row or scan_n
    rows = list(ws.iter_rows(min_row=1, max_row=min(scan_n, max_row), values_only=True))
    return _detect_header_from_rows(rows, min_ratio)

def _detect_header_from_rows(rows, min_ratio) -> int:
    best, best_ratio = 0, -1.0
    for r_idx, row in enumerate(rows, start=1):
        values = list(row)
        nn = sum(1 for v in values if v not in (None, ""))
        width = max(len(values), 1)
        ratio = nn / width
        if ratio > best_ratio:
            best_ratio, best = ratio, r_idx - 1
    return best if best_ratio >= min_ratio else 0

def _is_garbage(row_values) -> bool:
    cells = [str(v).strip().lower() for v in row_values if v is not None and str(v).strip()]
    if not cells:
        return GARBAGE_CONFIG.get("garbage_row_if_first_cell_empty_and_rest_empty", True)
    eq_set  = set(GARBAGE_CONFIG.get("garbage_row_if_any_cell_equals", []))
    contains = GARBAGE_CONFIG.get("garbage_row_if_any_cell_contains", [])
    for c in cells:
        if c in eq_set or any(p in c for p in contains):
            return True
    return False

def _make_unique_headers(headers):
    counts = {}
    unique = []
    for header in headers:
        base = header or "__unnamed_col"
        counts[base] = counts.get(base, 0) + 1
        if counts[base] == 1:
            unique.append(base)
        else:
            unique.append(f"{base}__{counts[base]}")
    return unique

def _extract_pog_snapshot_month(ws) -> Optional[str]:
    pat = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
    for row in ws.iter_rows():
        for cell in row:
            v = cell.value
            if v is None: continue
            text = str(v).lower()
            if "applied filter" in text or "dateid" in text:
                m = pat.search(str(v))
                if m:
                    mo, _d, yr = m.group(1), m.group(2), m.group(3)
                    try: return f"{int(yr):04d}-{int(mo):02d}"
                    except ValueError: pass
    return None

def _repair_read_only_dimensions(ws) -> None:
    """Ignore missing or obviously inflated worksheet dimensions.

    Some exports omit ``<dimension>`` entirely, while some Excel templates mark
    every column through XFD as used.  In read-only mode openpyxl trusts that
    metadata, which either leaves ``max_row`` as ``None`` or creates 16,384-cell
    tuples for every row.  Resetting dimensions makes the streaming reader use
    the actual cell records instead.
    """
    if ws.max_row is None or ws.max_column is None:
        ws.calculate_dimension(force=True)
    elif ws.max_column > 2048:
        ws.reset_dimensions()

def inspect_workbook_sheets(filepath: str) -> list[str]:
    """List workbook sheets without materializing their tables."""
    _validate_xlsx_container(filepath)
    try:
        with zipfile.ZipFile(filepath, "r") as archive:
            root = ET.fromstring(archive.read("xl/workbook.xml"))
        names = [
            node.attrib.get("name", "").strip()
            for node in root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")
            if node.attrib.get("name", "").strip()
        ]
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError(
            f"Không đọc được danh sách sheet của file '{Path(filepath).name}': {exc}"
        ) from exc
    if not names:
        raise ValueError(
            f"File Excel '{Path(filepath).name}' không có sheet nào."
        )
    return names

def load_workbook_raw(filepath: str, is_pog_file: bool = False,
                      selected_sheet_names: Optional[list[str]] = None) -> LoadedWorkbook:
    wb = _open_workbook_safely(filepath)
    result = LoadedWorkbook()
    cfg = GARBAGE_CONFIG["header_row_detection"]
    scan_n, min_ratio = cfg["scan_first_n_rows"], cfg["min_non_null_ratio"]
    selected = list(dict.fromkeys(selected_sheet_names or wb.sheetnames))
    missing = [name for name in selected if name not in wb.sheetnames]
    if missing:
        wb.close()
        raise ValueError(
            f"Không tìm thấy sheet đã chọn: {', '.join(missing)}. "
            f"Sheet có sẵn: {', '.join(wb.sheetnames)}"
        )
    for sn in selected:
        _repair_read_only_dimensions(wb[sn])
    if is_pog_file:
        for sn in selected:
            sm = _extract_pog_snapshot_month(wb[sn])
            if sm: result.pog_snapshot_month = sm; break
    for sn in selected:
        ws = wb[sn]
        row_iterator = ws.iter_rows(values_only=True)
        scanned_rows = list(itertools.islice(row_iterator, scan_n))
        hi = _detect_header_from_rows(scanned_rows, min_ratio)
        header_row = list(scanned_rows[hi]) if hi < len(scanned_rows) else []
        last_used = -1
        for idx, value in enumerate(header_row):
            if value not in (None, ""):
                last_used = idx
        headers = []
        for c in range(0, last_used + 1):
            h = header_row[c] if c < len(header_row) else None
            headers.append(str(h).strip() if h and str(h).strip() else f"__unnamed_col_{c}")
        headers = _make_unique_headers(headers)
        if len(headers) > MAX_DATA_COLUMNS:
            raise ValueError(
                f"Sheet '{sn}' có {len(headers):,} cột dữ liệu, vượt giới hạn "
                f"{MAX_DATA_COLUMNS:,}. Hãy xóa các cột định dạng dư trong Excel."
            )
        rows = []
        source_excel_rows = []
        scanned_data = enumerate(scanned_rows[hi + 1:], start=hi + 2)
        remaining_data = enumerate(row_iterator, start=len(scanned_rows) + 1)
        data_iterator = itertools.chain(scanned_data, remaining_data)
        for excel_row, row in data_iterator:
            vals = list(row[:len(headers)]) if len(headers) else []
            if all(v is None or str(v).strip()=='' for v in vals): continue
            if _is_garbage(vals): continue
            rows.append(vals)
            source_excel_rows.append(excel_row)
            if len(rows) > MAX_DATA_ROWS_PER_SHEET or len(rows) * max(len(headers), 1) > MAX_DATA_CELLS_PER_SHEET:
                raise ValueError(
                    f"Sheet '{sn}' quá lớn để xử lý an toàn "
                    f"(giới hạn {MAX_DATA_ROWS_PER_SHEET:,} dòng hoặc "
                    f"{MAX_DATA_CELLS_PER_SHEET:,} ô dữ liệu)."
                )
        df = pd.DataFrame(rows, columns=headers) if rows else pd.DataFrame(columns=headers)
        result.sheets[sn] = LoadedSheet(
            sn, hi, df, source_excel_rows=source_excel_rows, source_file=Path(filepath).name,
        )
    wb.close()
    if not any(not sheet.df.empty for sheet in result.sheets.values()):
        raise ValueError(
            f"File Excel '{Path(filepath).name}' không có sheet dữ liệu đọc được. "
            "Hãy kiểm tra dòng tiêu đề và dữ liệu trong file."
        )
    return result