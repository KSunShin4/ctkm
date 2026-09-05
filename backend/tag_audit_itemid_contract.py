# -*- coding: utf-8 -*-
"""ITEMID-first recognition hardening for physical Pharmacity tags.

Company shelf tags visibly print an ITEMID such as ``P03845``. Treat that printed
identifier as the primary identity signal. Barcode remains supporting evidence.
This layer never changes CTKM business rules; it only hardens OCR observations
before deterministic comparison.
"""
from __future__ import annotations

import re

_ITEMID_PATTERN = re.compile(r"(?<![A-Z0-9])P\s*[-_.:]?\s*(\d{3,8})(?!\d)", re.IGNORECASE)


def extract_itemid_candidates(*values) -> list[str]:
    """Return unique canonical P-number candidates in first-seen order."""
    found: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).upper()
        for match in _ITEMID_PATTERN.finditer(text):
            candidate = f"P{match.group(1)}"
            if candidate not in seen:
                seen.add(candidate)
                found.append(candidate)
    return found


def install_tag_audit_itemid_contract(tag_audit_module) -> None:
    if getattr(tag_audit_module, "_itemid_primary_contract_v1", False):
        return

    original_extract = tag_audit_module._extract_tag_with_gemini
    original_compare = tag_audit_module.compare_observation

    def extract_with_itemid_primary(image: bytes, mime_type: str, month: str | None) -> dict:
        observed = original_extract(image, mime_type, month)
        candidates = extract_itemid_candidates(
            observed.get("item_id"),
            observed.get("raw_text"),
            observed.get("date_text"),
            observed.get("product_name"),
            observed.get("promo_text"),
        )
        observed["item_id_candidates"] = candidates
        if len(candidates) == 1:
            observed["item_id"] = candidates[0]
        elif len(candidates) > 1:
            # Never let an OCR guess choose among multiple printed P-numbers.
            observed["item_id"] = ""
        return observed

    def compare_with_itemid_primary(rows: list[dict], observed: dict, manual_item_id: str = "") -> dict:
        if not str(manual_item_id or "").strip():
            candidates = list(observed.get("item_id_candidates") or [])
            if len(candidates) > 1:
                return {
                    "verdict": {
                        "code": "review_itemid_ambiguous",
                        "title": "Cần xác nhận mã sản phẩm",
                        "detail": "Ảnh đọc được nhiều mã Pxxxxx khác nhau; hệ thống không tự chọn một mã.",
                        "severity": "warning",
                    },
                    "identity_source": "ocr_item_id_ambiguous",
                    "observed": observed,
                    "expected": None,
                    "mismatches": ["item_id"],
                }
        return original_compare(rows, observed, manual_item_id=manual_item_id)

    tag_audit_module._extract_tag_with_gemini = extract_with_itemid_primary
    tag_audit_module.compare_observation = compare_with_itemid_primary
    tag_audit_module.extract_itemid_candidates = extract_itemid_candidates
    tag_audit_module._itemid_primary_contract_v1 = True
