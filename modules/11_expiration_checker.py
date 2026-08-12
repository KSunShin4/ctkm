# -*- coding: utf-8 -*-
"""Validate manually entered item/batch/expiration triples against an Excel export."""
from __future__ import annotations

from io import BytesIO
from typing import BinaryIO

import pandas as pd

REQUIRED_COLUMNS = ("ITEMID", "BATCHNUMER", "EXPDATE")
OPTIONAL_COLUMNS = ("ITEMNAME", "INVENTUNIT", "ONHANDNEAREXPIRATION")


def _text(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _date_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    return "" if pd.isna(parsed) else parsed.strftime("%d/%m/%Y")


def load_expiration_export(source: bytes | BinaryIO) -> tuple[pd.DataFrame, str]:
    """Return the first sheet containing the three expected export columns."""
    content = BytesIO(source) if isinstance(source, bytes) else source
    workbook = pd.ExcelFile(content)
    for sheet_name in workbook.sheet_names:
        frame = pd.read_excel(workbook, sheet_name=sheet_name, dtype=object)
        lookup = {str(column).strip().upper(): column for column in frame.columns}
        if all(column in lookup for column in REQUIRED_COLUMNS):
            selected_names = list(REQUIRED_COLUMNS) + [column for column in OPTIONAL_COLUMNS if column in lookup]
            selected = frame[[lookup[column] for column in selected_names]].copy()
            selected.columns = selected_names
            selected["ITEMID"] = selected["ITEMID"].map(_text).str.upper()
            selected["BATCHNUMER"] = selected["BATCHNUMER"].map(_text)
            selected["EXPDATE"] = selected["EXPDATE"].map(_date_text)
            for column in ("ITEMNAME", "INVENTUNIT"):
                if column in selected:
                    selected[column] = selected[column].map(_text)
            return selected, sheet_name
    raise ValueError(
        "Không tìm thấy sheet có đủ các cột ITEMID, BATCHNUMER và EXPDATE."
    )


def check_entries(frame: pd.DataFrame, raw_entries: str) -> list[dict]:
    rows = [line.strip() for line in raw_entries.splitlines() if line.strip()]
    if not rows:
        raise ValueError("Hãy nhập ít nhất một dòng theo mẫu MÃ_P;SỐ_LÔ;DD/MM/YYYY.")

    results = []
    for line_number, raw in enumerate(rows, start=1):
        parts = [part.strip() for part in raw.split(";")]
        base = {"line": line_number, "input": raw}
        if len(parts) != 3 or not all(parts):
            results.append({**base, "status": "invalid", "message": "Cần đúng 3 phần, ngăn cách bằng dấu ;"})
            continue

        item_id, batch_number, raw_date = parts
        item_id = item_id.upper()
        exp_date = _date_text(raw_date)
        normalized = f"{item_id};{batch_number};{exp_date or raw_date}"
        detail = {**base, "item_id": item_id, "batch_number": batch_number,
                  "exp_date": exp_date or raw_date, "normalized": normalized}
        if not item_id.startswith("P"):
            results.append({**detail, "status": "invalid", "message": "Mã sản phẩm phải bắt đầu bằng P"})
            continue
        if not exp_date:
            results.append({**detail, "status": "invalid", "message": "Hạn dùng phải có dạng DD/MM/YYYY"})
            continue

        item_rows = frame[frame["ITEMID"] == item_id]
        if item_rows.empty:
            results.append({**detail, "status": "not_found", "message": "Không tìm thấy mã sản phẩm trong file"})
            continue
        first_item = item_rows.iloc[0]
        related_rows = []
        for _, record in item_rows.drop_duplicates(["BATCHNUMER", "EXPDATE"]).iterrows():
            related_rows.append({
                "batch_number": _text(record["BATCHNUMER"]),
                "exp_date": _text(record["EXPDATE"]),
                "on_hand": _text(record.get("ONHANDNEAREXPIRATION", "")),
            })
        related_rows.sort(
            key=lambda row: pd.to_datetime(row["exp_date"], format="%d/%m/%Y", errors="coerce"),
            reverse=True,
        )
        product_info = {
            "item_name": _text(first_item.get("ITEMNAME", "")),
            "inventory_unit": _text(first_item.get("INVENTUNIT", "")),
        }
        batch_rows = item_rows[item_rows["BATCHNUMER"] == batch_number]
        if batch_rows.empty:
            results.append({**detail, **product_info, "status": "batch_mismatch",
                            "message": "Số lô không có trong file", "related_rows": related_rows})
            continue
        if not (batch_rows["EXPDATE"] == exp_date).any():
            dates = sorted({value for value in batch_rows["EXPDATE"] if value})
            suffix = f" (trong file: {', '.join(dates)})" if dates else ""
            results.append({**detail, **product_info, "status": "date_mismatch",
                            "message": "Hạn dùng không khớp" + suffix,
                            "related_rows": related_rows})
            continue
        matched_record = batch_rows[batch_rows["EXPDATE"] == exp_date].iloc[0]
        results.append({
            **detail, **product_info,
            "on_hand": _text(matched_record.get("ONHANDNEAREXPIRATION", "")),
            "status": "matched", "message": "Khớp dữ liệu", "related_rows": related_rows,
        })
    return results
