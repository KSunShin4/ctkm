# -*- coding: utf-8 -*-
"""Business-date safety guard for the physical shelf-tag scanner.

CTKM action sheets are generated for one ``business_date``. Reusing yesterday's
result workbook can therefore change a correct Gắn/Tháo/Chờ verdict into a wrong
one even when OCR is perfect. Preserve the report date as technical scanner
metadata, expose it in context diagnostics, and refuse deterministic comparison
when a known report date is not today's Viet Nam business date.

The guard is deliberately conservative:
- it reads only the existing HƯỚNG DẪN labels written by the exporter;
- it never invents a date when the metadata is absent or invalid;
- missing metadata remains backward-compatible and does not block scanning;
- source business fields are not normalized or mutated.
"""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
import re
from zoneinfo import ZoneInfo

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel


_GUIDE_SHEET = "HƯỚNG DẪN"
_BUSINESS_DATE_KEY = "_report_business_date"
_REPORT_MONTH_KEY = "_report_month"
_VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _copyable_source(source):
    if isinstance(source, (bytes, bytearray)):
        return BytesIO(bytes(source))
    getvalue = getattr(source, "getvalue", None)
    if callable(getvalue):
        try:
            return BytesIO(getvalue())
        except Exception:
            pass
    return source


def _iso_date(value) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            converted = from_excel(value)
            if isinstance(converted, datetime):
                return converted.date().isoformat()
            if isinstance(converted, date):
                return converted.isoformat()
        except Exception:
            return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def read_report_metadata(source) -> dict:
    """Read exporter metadata without depending on fixed cell coordinates."""
    workbook = None
    try:
        workbook = load_workbook(_copyable_source(source), data_only=True, read_only=True)
        if _GUIDE_SHEET not in workbook.sheetnames:
            return {}
        ws = workbook[_GUIDE_SHEET]
        metadata: dict[str, str] = {}
        for label, value in ws.iter_rows(min_row=1, max_row=24, min_col=1, max_col=2, values_only=True):
            key = str(label or "").strip()
            if key == "Tháng báo cáo":
                month = str(value or "").strip()
                if re.fullmatch(r"\d{4}-\d{2}", month):
                    metadata["report_month"] = month
            elif key == "Ngày nghiệp vụ":
                parsed = _iso_date(value)
                if parsed:
                    metadata["business_date"] = parsed
        return metadata
    finally:
        if workbook is not None:
            workbook.close()


def current_vn_business_date() -> str:
    return datetime.now(_VN_TZ).date().isoformat()


def metadata_from_rows(rows: list[dict]) -> dict:
    for row in rows or []:
        business_date = str(row.get(_BUSINESS_DATE_KEY) or "").strip()
        report_month = str(row.get(_REPORT_MONTH_KEY) or "").strip()
        if business_date or report_month:
            return {
                "business_date": business_date or None,
                "report_month": report_month or None,
            }
    return {"business_date": None, "report_month": None}


def install_tag_audit_business_date_contract(tag_audit_module) -> None:
    if getattr(tag_audit_module, "_business_date_contract_v1", False):
        return

    original_parse = tag_audit_module._parse_action_workbook
    original_context_payload = tag_audit_module._context_payload
    original_compare = tag_audit_module.compare_observation

    def parse_with_report_metadata(source):
        metadata_source = _copyable_source(source)
        rows = original_parse(source)
        try:
            metadata = read_report_metadata(metadata_source)
        except Exception:
            # Metadata is a safety enhancement. A malformed/legacy guide must not
            # make an otherwise valid action workbook unreadable.
            metadata = {}
        business_date = metadata.get("business_date")
        report_month = metadata.get("report_month")
        if business_date or report_month:
            for row in rows:
                row[_BUSINESS_DATE_KEY] = business_date
                row[_REPORT_MONTH_KEY] = report_month
        return rows

    def context_payload_with_business_date(cache: dict) -> dict:
        payload = original_context_payload(cache)
        metadata = metadata_from_rows(cache.get("rows") or [])
        today = current_vn_business_date()
        business_date = metadata.get("business_date")
        payload["report_month"] = metadata.get("report_month")
        payload["business_date"] = business_date
        payload["scanner_business_date"] = today
        payload["business_date_stale"] = bool(business_date and business_date != today)
        return payload

    def compare_with_business_date_guard(rows, observed, manual_item_id=""):
        metadata = metadata_from_rows(rows)
        business_date = metadata.get("business_date")
        today = current_vn_business_date()
        if business_date and business_date != today:
            raise tag_audit_module.HTTPException(
                status_code=409,
                detail=(
                    f"Workbook kiểm tem đang theo ngày {business_date}; hôm nay là {today}. "
                    "Hãy chạy hoặc tải workbook CTKM mới trước khi kiểm tem."
                ),
            )
        return original_compare(rows, observed, manual_item_id=manual_item_id)

    tag_audit_module._parse_action_workbook = parse_with_report_metadata
    tag_audit_module._context_payload = context_payload_with_business_date
    tag_audit_module.compare_observation = compare_with_business_date_guard
    tag_audit_module.read_tag_audit_report_metadata = read_report_metadata
    tag_audit_module.tag_audit_current_business_date = current_vn_business_date
    tag_audit_module._business_date_contract_v1 = True
