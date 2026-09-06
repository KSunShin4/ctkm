# -*- coding: utf-8 -*-
"""Supporting-only barcode extraction for shelf-tag photos using ZXing-C++.

Barcode is deliberately NOT a product identity in this project. This module may
populate observed barcode text to help operators/debugging, but it never maps a
barcode to Pharmacity ITEMID and never changes CTKM PASS/FAIL decisions.
"""
from __future__ import annotations

import re


_NUMERIC_BARCODE_RE = re.compile(r"^\d{8,14}$")


def _decode_image(image_bytes: bytes):
    import cv2
    import numpy as np

    array = np.frombuffer(image_bytes, dtype=np.uint8)
    decoded = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if decoded is None or decoded.size == 0:
        raise RuntimeError("Không giải mã được ảnh để đọc barcode")
    return decoded


def _read_zxing_barcodes(image) -> list[str]:
    import zxingcpp

    values: list[str] = []
    seen: set[str] = set()
    for barcode in zxingcpp.read_barcodes(image):
        text = str(getattr(barcode, "text", "") or "").strip()
        if not _NUMERIC_BARCODE_RE.fullmatch(text):
            continue
        if text not in seen:
            seen.add(text)
            values.append(text)
    return values


def extract_supporting_barcodes(image_bytes: bytes) -> dict:
    """Return deterministic numeric candidates; never guess when >1 are present."""
    decoded = _decode_image(image_bytes)
    candidates = _read_zxing_barcodes(decoded)
    return {
        "barcode": candidates[0] if len(candidates) == 1 else "",
        "barcode_candidates": candidates,
        "barcode_source": (
            "zxingcpp" if len(candidates) == 1
            else "zxingcpp_ambiguous" if len(candidates) > 1
            else "zxingcpp_none"
        ),
    }


def install_tag_audit_barcode_contract(tag_audit_module) -> None:
    """Wrap OCR extraction and add barcode evidence only when it is still blank."""
    if getattr(tag_audit_module, "_barcode_contract_v1", False):
        return

    original_extract = tag_audit_module._extract_tag_with_gemini

    def extract_with_barcode(image: bytes, mime_type: str, month: str | None) -> dict:
        observed = original_extract(image, mime_type, month)
        existing = re.sub(r"\D", "", str(observed.get("barcode") or ""))
        if _NUMERIC_BARCODE_RE.fullmatch(existing):
            observed["barcode"] = existing
            observed.setdefault("barcode_candidates", [existing])
            observed.setdefault("barcode_source", "ocr")
            return observed

        try:
            barcode_result = extract_supporting_barcodes(image)
        except Exception as exc:
            observed.setdefault("barcode_candidates", [])
            observed.setdefault("barcode_source", "zxingcpp_error")
            observed["barcode_warning"] = str(exc)
            return observed

        observed["barcode_candidates"] = barcode_result["barcode_candidates"]
        observed["barcode_source"] = barcode_result["barcode_source"]
        if barcode_result["barcode"]:
            observed["barcode"] = barcode_result["barcode"]
        return observed

    tag_audit_module._extract_tag_with_gemini = extract_with_barcode
    tag_audit_module.extract_supporting_barcodes = extract_supporting_barcodes
    tag_audit_module._barcode_contract_v1 = True
