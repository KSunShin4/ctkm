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


def _recover_after_perception_failure(image: bytes, month: str | None, exc: Exception) -> dict:
    """Keep the scan usable when optional Gemini fallback is unauthorized/down."""
    from backend.tag_audit_rescue_ocr import rescue_with_focused_local_ocr

    try:
        observed = rescue_with_focused_local_ocr(image, month)
    except Exception as rescue_exc:
        observed = None
        rescue_message = str(rescue_exc)
    else:
        rescue_message = ""

    if observed is None:
        observed = {
            "item_id": "",
            "item_id_candidates": [],
            "barcode": "",
            "product_name": "",
            "promo_text": "",
            "normal_price": None,
            "promo_price": None,
            "promo_from": None,
            "promo_to": None,
            "raw_text": "",
            "confidence": 0.0,
            "ocr_engine": "local-rescue-failed",
        }
    observed = dict(observed)
    warning = f"Gemini fallback không dùng được: {type(exc).__name__}: {exc}"
    if rescue_message:
        warning += f"; rescue OCR: {rescue_message}"
    observed["ocr_warning"] = warning
    observed["gemini_fallback_failed"] = True
    return observed


def install_tag_audit_barcode_contract(tag_audit_module) -> None:
    """Wrap OCR extraction and add barcode evidence only when it is still blank."""
    if getattr(tag_audit_module, "_barcode_contract_v1", False):
        return

    original_extract = tag_audit_module._extract_tag_with_gemini

    def extract_with_barcode(image: bytes, mime_type: str, month: str | None) -> dict:
        try:
            observed = original_extract(image, mime_type, month)
        except Exception as exc:
            # The local-first extractor may already have read useful text before
            # optional Gemini fallback returns 401/403/429. Do a tighter local-only
            # retry instead of discarding the whole observation and returning blanks.
            observed = _recover_after_perception_failure(image, month, exc)

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
