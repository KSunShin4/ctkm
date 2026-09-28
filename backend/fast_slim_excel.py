# -*- coding: utf-8 -*-
"""Fast XlsxWriter backend for the production-slim CTKM workbook.

The full exporter remains openpyxl-based. Production-slim writes the same
source-faithful frames with XlsxWriter so large real-store workbooks do not pay
openpyxl's per-cell write/style cost.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


_USER_SHEETS = {"TỔNG HỢP - TEM", "Gắn tem", "Tháo tem", "Chờ gắn", "Cần review"}
_TECHNICAL_EXACT = {"target_month", "source_sheet", "pog_snapshot_month"}
_CHANNEL_NAMES = {"channel", "key channel", "kenh ap dung", "kenh ban", "sales channel"}


def _display_label(exporter, raw_header: object) -> str:
    raw = str(raw_header or "")
    base = raw.split("__", 1)[0]
    labels = getattr(exporter, "_BILINGUAL_HEADERS", {})
    exact = labels.get(raw)
    base_label = labels.get(base)
    if exact:
        return exact
    if base_label:
        return base_label if raw == base else f"{base_label.split(' (', 1)[0]} ({raw})"
    return raw


def _safe(frame: pd.DataFrame | None, note: str) -> pd.DataFrame:
    if frame is not None and not frame.empty:
        return frame
    return pd.DataFrame({"Ghi chu": [note]})


def _with_remaining_days(frame: pd.DataFrame, business_date) -> pd.DataFrame:
    if frame is None or frame.empty or "so_ngay_con_lai" not in frame.columns:
        return frame
    report_date = pd.to_datetime(business_date, errors="coerce")
    if pd.isna(report_date) or "promo_to" not in frame.columns:
        return frame
    result = frame.copy()
    promo_to = pd.to_datetime(result["promo_to"], errors="coerce")
    remaining = (promo_to.dt.normalize() - report_date.normalize()).dt.days
    remaining = remaining.clip(lower=0)
    result["so_ngay_con_lai"] = remaining.where(remaining.notna(), "")
    return result


def _make_formats(workbook):
    cache = {}

    def header(color="1F4E78"):
        if color not in cache:
            cache[color] = workbook.add_format({
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": f"#{color}",
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
                "border": 1,
                "border_color": "#D0D7DE",
            })
        return cache[color]

    return {
        "header": header,
        "date": workbook.add_format({"num_format": "dd/mm/yyyy", "valign": "vcenter"}),
        "price": workbook.add_format({"num_format": "#,##0", "valign": "vcenter"}),
        "unlocked": workbook.add_format({"locked": False, "bg_color": "#FFF2CC"}),
        "unlocked_date": workbook.add_format({
            "locked": False, "bg_color": "#FFF2CC", "num_format": "dd/mm/yyyy hh:mm"
        }),
        "done": workbook.add_format({"bg_color": "#E2F0D9"}),
        "missing": workbook.add_format({"bg_color": "#FFC7CE"}),
        "guide_title": workbook.add_format({
            "bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78",
            "font_size": 18, "align": "center", "valign": "vcenter",
        }),
        "guide_label": workbook.add_format({"bold": True, "font_color": "#1F4E78"}),
        "guide_card": workbook.add_format({"bold": True, "bg_color": "#DDEBF7"}),
        "guide_count": workbook.add_format({"bold": True, "font_size": 14, "bg_color": "#DDEBF7"}),
        "guide_date": workbook.add_format({"num_format": "dd/mm/yyyy"}),
    }


def _column_hidden(exporter, raw: str, *, action_sheet: bool, selected: set[str], sheet_name: str) -> bool:
    normalized = exporter._normalize_action_text(raw)
    while normalized.startswith("extra__"):
        normalized = normalized[len("extra__"):]
    if normalized in _CHANNEL_NAMES:
        hidden = False
    else:
        hidden = raw.startswith("extra__") or raw.startswith("source_sheet__") or (
            action_sheet and raw in _TECHNICAL_EXACT
        )
    if action_sheet and raw in getattr(exporter, "_DEFAULT_HIDDEN_ACTION_FIELDS", set()):
        hidden = True

    if selected and sheet_name in _USER_SHEETS:
        selectable = {
            "item_id", "item_name", "promo_uom", "key_channel", "channel",
            "campaign_name", "campaign_detail", "promo_from", "promo_to",
            "normal_price", "promo_price", "product_type", "store_id",
            "pog_code", "location_id", "facing",
        }
        pinned = {"key_channel", "channel", "item_id", "item_name", "promo_uom"}
        if raw in selectable and raw not in pinned and raw.lower() not in selected:
            hidden = True
    return hidden


def _write_frame(
    writer,
    exporter,
    formats,
    sheet_name: str,
    frame: pd.DataFrame | None,
    note: str,
    *,
    action_sheet: bool = False,
    selected: set[str] | None = None,
    hidden_sheet: bool = False,
    bilingual: bool = True,
):
    selected = selected or set()
    data = _safe(frame, note)
    data.to_excel(writer, sheet_name=sheet_name, index=False)
    ws = writer.sheets[sheet_name]
    raw_headers = [str(column) for column in data.columns]
    header_groups = getattr(exporter, "_HEADER_GROUPS", {})
    widths = getattr(exporter, "_COLUMN_WIDTHS", {})

    for index, raw in enumerate(raw_headers):
        label = _display_label(exporter, raw) if bilingual else raw
        ws.write(0, index, label, formats["header"](header_groups.get(raw, "1F4E78")))
        width = widths.get(raw, min(30, max(12, len(label) + 2)))
        cell_format = None
        if raw in {"promo_from", "promo_to", "ngay_gan_tem", "ngay_thao_tem"}:
            cell_format = formats["date"]
        elif raw in {"normal_price", "promo_price"}:
            cell_format = formats["price"]
        if action_sheet and raw in {"processing_status", "processed_by", "staff_note"}:
            cell_format = formats["unlocked"]
        elif action_sheet and raw == "processed_at":
            cell_format = formats["unlocked_date"]
        hidden = _column_hidden(
            exporter, raw, action_sheet=action_sheet, selected=selected, sheet_name=sheet_name
        )
        ws.set_column(index, index, width, cell_format, {"hidden": hidden})

    ws.hide_gridlines(2)
    ws.freeze_panes(1, 2 if sheet_name in _USER_SHEETS else 0)
    if len(data) > 0 and raw_headers:
        ws.autofilter(0, 0, len(data), len(raw_headers) - 1)
    if sheet_name == "TỔNG HỢP - TEM":
        ws.set_tab_color("#1F4E78")

    if action_sheet and "processing_status" in raw_headers:
        status_col = raw_headers.index("processing_status")
        if len(data) > 0:
            ws.data_validation(1, status_col, len(data), status_col, {
                "validate": "list",
                "source": ["Chưa xử lý", "Đã xong", "Không tìm thấy", "Không thực hiện được"],
                "error_title": "Trạng thái không hợp lệ",
                "error_message": "Hãy chọn một trạng thái trong danh sách.",
            })
            from xlsxwriter.utility import xl_col_to_name
            status_letter = xl_col_to_name(status_col)
            ws.conditional_format(1, 0, len(data), len(raw_headers) - 1, {
                "type": "formula",
                "criteria": f'=${status_letter}2="Đã xong"',
                "format": formats["done"],
            })
            ws.conditional_format(1, 0, len(data), len(raw_headers) - 1, {
                "type": "formula",
                "criteria": f'=${status_letter}2="Không tìm thấy"',
                "format": formats["missing"],
            })
        ws.protect("", {"autofilter": True, "sort": True})
        ws.set_tab_color("#2E7D32")

    if hidden_sheet:
        ws.hide()
    return ws


def _write_metadata(writer, sheet_name: str, frame: pd.DataFrame | None):
    if frame is None or frame.empty:
        return
    frame.to_excel(writer, sheet_name=sheet_name, index=False)
    ws = writer.sheets[sheet_name]
    ws.freeze_panes(1, 0)
    if len(frame) > 0 and len(frame.columns) > 0:
        ws.autofilter(0, 0, len(frame), len(frame.columns) - 1)
    ws.hide()


def _write_guide(writer, formats, counts: dict[str, int], summary: dict | None):
    wb = writer.book
    ws = wb.add_worksheet("HƯỚNG DẪN")
    writer.sheets["HƯỚNG DẪN"] = ws
    ws.hide_gridlines(2)
    ws.set_tab_color("#1F4E78")
    ws.merge_range("A1:F2", "DANH SÁCH THAO TÁC TEM KHUYẾN MÃI", formats["guide_title"])
    ws.write("A4", "Tháng báo cáo", formats["guide_label"])
    ws.write("B4", (summary or {}).get("Thang bao cao", ""))
    ws.write("A5", "Ngày nghiệp vụ", formats["guide_label"])
    business_date = pd.to_datetime((summary or {}).get("Ngay nghiep vu"), errors="coerce")
    if pd.notna(business_date):
        ws.write_datetime("B5", business_date.to_pydatetime(), formats["guide_date"])
    else:
        ws.write("B5", (summary or {}).get("Ngay nghiep vu", ""))
    ws.write("D4", "Cách sử dụng", formats["guide_label"])
    instructions = [
        "1. Mở TỔNG HỢP - TEM để xem toàn bộ công việc hoặc vào từng sheet thao tác.",
        "2. Lọc KEY Channel trước, sau đó lọc Channel theo đúng value gốc từ file công ty.",
        "3. Lọc tiếp Cửa hàng → POG → Vị trí để đi thao tác tại quầy.",
        "4. POG chỉ cung cấp vị trí; không phản ánh tem đã gắn thực tế hay chưa.",
        "5. Cập nhật các ô màu vàng ở sheet thao tác; không sửa dữ liệu nguồn.",
    ]
    for row, instruction in enumerate(instructions, start=4):
        ws.write(row, 3, instruction)
    cards = [
        ("Gắn tem", "Gắn tem"),
        ("Tháo tem", "Tháo tem"),
        ("Chờ gắn", "Chờ gắn"),
        ("Cần review", "Cần review"),
        ("Thiếu vị trí", "CTKM thieu vi tri ke"),
        ("Review vị trí", "POG cần kiểm tra"),
        ("POG cần review", "POG cần review"),
    ]
    for row, (label, target) in enumerate(cards, start=5):
        ws.write_url(row, 0, f"internal:'{target}'!A1", formats["guide_card"], label)
        ws.write(row, 1, int(counts.get(target, 0)), formats["guide_count"])
    ws.write("D10", (
        "Bản production slim: tối ưu ghi/đọc workbook nhưng vẫn giữ reconciliation "
        "và source audit để không mất dữ liệu nguồn."
    ))
    ws.write("A14", "Chú giải", formats["guide_label"])
    for row, (label, meaning) in enumerate([
        ("Xanh", "Cần gắn tem"),
        ("Cam", "Cần tháo tem"),
        ("Đỏ", "Cần kiểm tra vị trí"),
        ("Vàng", "Ô dược sĩ được nhập"),
    ], start=14):
        ws.write(row, 0, label)
        ws.write(row, 1, meaning)
    ws.set_column("A:A", 24)
    ws.set_column("B:B", 22)
    ws.set_column("C:C", 4)
    ws.set_column("D:D", 48)
    ws.set_column("E:F", 16)
    ws.freeze_panes(3, 0)


def write_slim_workbook(
    *,
    output_path,
    exporter,
    total,
    gan,
    thao,
    wait,
    review,
    location_issues,
    location_review,
    matched_all,
    missing_all_km,
    monthly_pog_only,
    pog_review,
    audit,
    mapping_log,
    reconciliation_summary,
    selected,
    pog_metadata=None,
    km_metadata=None,
):
    """Write the production-slim workbook in one fast XlsxWriter pass."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    business_date = (
        reconciliation_summary.get("Ngay nghiep vu")
        if isinstance(reconciliation_summary, dict) else None
    )
    gan = _with_remaining_days(gan, business_date)
    thao = _with_remaining_days(thao, business_date)
    wait = _with_remaining_days(wait, business_date)
    review = _with_remaining_days(review, business_date)

    counts = {
        "Gắn tem": 0 if gan is None else len(gan),
        "Tháo tem": 0 if thao is None else len(thao),
        "Chờ gắn": 0 if wait is None else len(wait),
        "Cần review": 0 if review is None else len(review),
        "CTKM thieu vi tri ke": 0 if location_issues is None else len(location_issues),
        "POG cần kiểm tra": 0 if location_review is None else len(location_review),
        "POG cần review": 0 if pog_review is None else len(pog_review),
    }

    with pd.ExcelWriter(
        output_path,
        engine="xlsxwriter",
        date_format="dd/mm/yyyy",
        datetime_format="dd/mm/yyyy hh:mm",
    ) as writer:
        formats = _make_formats(writer.book)
        _write_guide(writer, formats, counts, reconciliation_summary)
        _write_frame(writer, exporter, formats, "TỔNG HỢP - TEM", total, "Không có dữ liệu công việc.", selected=selected)
        _write_frame(writer, exporter, formats, "Gắn tem", gan, "Không có CTKM cần gắn tem.", action_sheet=True, selected=selected)
        _write_frame(writer, exporter, formats, "Tháo tem", thao, "Không có CTKM cần tháo tem.", action_sheet=True, selected=selected)
        _write_frame(writer, exporter, formats, "Chờ gắn", wait, "Không có CTKM đang chờ đến ngày gắn.", action_sheet=True, selected=selected)
        _write_frame(writer, exporter, formats, "Cần review", review, "Không có CTKM cần review.", action_sheet=True, selected=selected)
        _write_frame(writer, exporter, formats, "CTKM thieu vi tri ke", location_issues, "Không có công việc nào cần kiểm tra vị trí POG.")
        _write_frame(writer, exporter, formats, "POG cần kiểm tra", location_review, "Không có vị trí POG nào cần review.")
        _write_frame(writer, exporter, formats, "Tong hop", matched_all, "Không có KM nào khớp POG.")
        _write_frame(writer, exporter, formats, "POG không có KM", missing_all_km, "Không có POG nào thiếu KM.")
        _write_frame(writer, exporter, formats, "POG không có Monthly CTKM", monthly_pog_only, "Không có POG nào thiếu Monthly CTKM.")
        _write_frame(writer, exporter, formats, "POG cần review", pog_review, "Không có dòng POG business nào cần review.")
        _write_frame(writer, exporter, formats, "Audit hành động", audit, "Không có dữ liệu hành động để audit.")
        _write_frame(writer, exporter, formats, "Mapping log", mapping_log, "Chưa có mapping log.", bilingual=False)
        _write_frame(writer, exporter, formats, "POG không có CTKM", missing_all_km, "Không có POG nào thiếu KM.", hidden_sheet=True)
        _write_metadata(writer, "POG metadata", pog_metadata)
        _write_metadata(writer, "KM metadata", km_metadata)
    return str(output_path)
