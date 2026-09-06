# -*- coding: utf-8 -*-
"""Safe OCR year hint for uploaded CTKM workbooks.

Uploaded result workbooks do not carry ``target_month`` in scanner process memory.
Pharmacity shelf tags may print only DD/MM-DD/MM, so OCR still needs a year to
construct ISO dates. Derive a hint only when all valid promotion dates in the
current workbook agree on one year. Never infer a month and never guess across
mixed-year data.
"""
from __future__ import annotations

import re

from backend.tag_audit_business_date_contract import install_tag_audit_business_date_contract


def infer_unique_promotion_year(tag_audit_module, rows: list[dict]) -> str | None:
    years: set[str] = set()
    for row in rows or []:
        for key in ("promo_from", "promo_to"):
            value = tag_audit_module._parse_iso_date(row.get(key))
            if value:
                years.add(value[:4])
                if len(years) > 1:
                    return None
    return next(iter(years)) if len(years) == 1 else None


def install_tag_audit_temporal_hint_contract(tag_audit_module, local_ocr_module) -> None:
    if getattr(tag_audit_module, "_temporal_hint_contract_v1", False):
        return

    original_context_payload = tag_audit_module._context_payload
    original_extract = tag_audit_module._extract_tag_with_gemini
    original_year = local_ocr_module._year

    def year_accepting_safe_hint(value: str | None) -> int:
        text = str(value or "").strip()
        if re.fullmatch(r"\d{4}", text):
            return int(text)
        return original_year(value)

    def context_payload_with_year_hint(cache: dict) -> dict:
        payload = original_context_payload(cache)
        payload["ocr_year_hint"] = infer_unique_promotion_year(
            tag_audit_module, cache.get("rows") or []
        )
        return payload

    def extract_with_uploaded_year_hint(image: bytes, mime_type: str, month: str | None) -> dict:
        temporal_hint = month
        if not str(month or "").strip():
            lock = getattr(tag_audit_module, "_CONTEXT_LOCK", None)
            if lock is not None:
                with lock:
                    rows = list((getattr(tag_audit_module, "_CONTEXT_CACHE", {}) or {}).get("rows") or [])
            else:
                rows = list((getattr(tag_audit_module, "_CONTEXT_CACHE", {}) or {}).get("rows") or [])
            temporal_hint = infer_unique_promotion_year(tag_audit_module, rows)
        return original_extract(image, mime_type, temporal_hint)

    local_ocr_module._year = year_accepting_safe_hint
    tag_audit_module._context_payload = context_payload_with_year_hint
    tag_audit_module._extract_tag_with_gemini = extract_with_uploaded_year_hint
    tag_audit_module.infer_unique_promotion_year = lambda rows: infer_unique_promotion_year(tag_audit_module, rows)
    tag_audit_module._temporal_hint_contract_v1 = True

    # Install the report-business-date guard after temporal payload wrapping so
    # both diagnostics coexist, and before progress wraps the comparator.
    install_tag_audit_business_date_contract(tag_audit_module)
