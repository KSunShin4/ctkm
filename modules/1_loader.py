# -*- coding: utf-8 -*-
"""Module 1: Loader — doc tho moi sheet, trich pog_snapshot_month tu file POG."""
from __future__ import annotations
import io, re, zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import openpyxl, pandas as pd
from .config_loader import GARBAGE_CONFIG

@dataclass
class LoadedSheet:
    sheet_name: str
    header_row_index: int
    df: pd.DataFrame
    source_file: str = ""

@dataclass
class LoadedWorkbook:
    sheets: dict = field(default_factory=dict)
    pog_snapshot_month: Optional[str] = None

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
    best, best_ratio = 0, -1.0
    max_row = ws.max_row or 1
    for r_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=min(scan_n, max_row), values_only=True), start=1):
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

def load_workbook_raw(filepath: str, is_pog_file: bool = False) -> LoadedWorkbook:
    safe = _strip_broken_defined_names(filepath)
    wb = openpyxl.load_workbook(io.BytesIO(safe), data_only=True, read_only=True)
    result = LoadedWorkbook()
    cfg = GARBAGE_CONFIG["header_row_detection"]
    scan_n, min_ratio = cfg["scan_first_n_rows"], cfg["min_non_null_ratio"]
    if is_pog_file:
        for sn in wb.sheetnames:
            sm = _extract_pog_snapshot_month(wb[sn])
            if sm: result.pog_snapshot_month = sm; break
    for sn in wb.sheetnames:
        ws = wb[sn]
        if not (ws.max_row or 0): continue
        hi = _detect_header_row(ws, scan_n, min_ratio)
        header_row = None
        for row in ws.iter_rows(min_row=hi + 1, max_row=hi + 1, values_only=True):
            header_row = list(row)
            break
        if header_row is None:
            header_row = []
        last_used = -1
        for idx, value in enumerate(header_row):
            if value not in (None, ""):
                last_used = idx
        headers = []
        for c in range(0, last_used + 1):
            h = header_row[c] if c < len(header_row) else None
            headers.append(str(h).strip() if h and str(h).strip() else f"__unnamed_col_{c}")
        headers = _make_unique_headers(headers)
        rows = []
        for row in ws.iter_rows(min_row=hi + 2, values_only=True):
            vals = list(row[:len(headers)]) if len(headers) else []
            if all(v is None or str(v).strip()=='' for v in vals): continue
            if _is_garbage(vals): continue
            rows.append(vals)
        df = pd.DataFrame(rows, columns=headers) if rows else pd.DataFrame(columns=headers)
        result.sheets[sn] = LoadedSheet(sn, hi, df, Path(filepath).name)
    return result
