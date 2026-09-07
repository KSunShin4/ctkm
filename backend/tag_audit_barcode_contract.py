# -*- coding: utf-8 -*-
"""Supporting-only barcode extraction for shelf-tag photos using ZXing-C++.

Barcode is deliberately NOT a product identity in this project. This module may
populate observed barcode text to help operators/debugging, but it never maps a
barcode to Pharmacity ITEMID and never changes CTKM PASS/FAIL decisions.

Gemini is intentionally last-resort. Before the optional remote fallback is
allowed, the wrapper reuses the local RapidOCR pipeline and the focused rescue
OCR. A locally identified ITEMID + price is considered useful enough to keep the
scan local; missing dates can remain REVIEW/manual instead of spending a Gemini
request on every imperfect photo.
"""
from __future__ import annotations

import os
import re
import threading
import time


_NUMERIC_BARCODE_RE = re.compile(r"^\d{8,14}$")

_GEMINI_GATE_LOCK = threading.Lock()
_GEMINI_LAST_FALLBACK = 0.0
_GEMINI_BLOCK_UNTIL = 0.0


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


def _local_candidate_key(observed: dict | None) -> tuple:
    if not observed:
        return (0, 0, 0, 0, 0.0)
    itemids = list(observed.get("item_id_candidates") or [])
    unique_item = len(itemids) == 1
    has_price = observed.get("promo_price") is not None
    has_dates = bool(observed.get("promo_from") and observed.get("promo_to"))
    try:
        confidence = float(observed.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    return (
        int(unique_item and has_price and has_dates),
        int(unique_item and has_price),
        int(unique_item),
        int(has_dates),
        confidence,
    )


def _local_good_enough(observed: dict | None) -> bool:
    """Keep useful scans local; dates may remain REVIEW/manual if OCR missed them."""
    if not observed:
        return False
    itemids = list(observed.get("item_id_candidates") or [])
    return len(itemids) == 1 and observed.get("promo_price") is not None


def _local_preflight(image: bytes, month: str | None) -> dict | None:
    """Try normal local OCR, then focused rescue, before any Gemini request."""
    from backend import tag_audit_local_ocr_contract as local_ocr
    from backend.tag_audit_rescue_ocr import rescue_with_focused_local_ocr

    candidates: list[dict] = []
    try:
        local = local_ocr.extract_tag_with_rapidocr(image, month)
    except Exception:
        local = None
    if local:
        candidates.append(dict(local))
        if _local_candidate_key(local)[0]:
            return dict(local)

    # The normal pass may miss a small Pxxxxx code or date in a multi-tag frame.
    # Focused rescue is still local/ONNX and therefore cheaper and more reliable
    # than spending a remote request first.
    try:
        rescue = rescue_with_focused_local_ocr(image, month)
    except Exception:
        rescue = None
    if rescue:
        candidates.append(dict(rescue))

    if not candidates:
        return None
    return max(candidates, key=_local_candidate_key)


def _blank_local_observation() -> dict:
    return {
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
        "ocr_engine": "local-unavailable",
    }


def _pace_optional_gemini() -> tuple[bool, str]:
    """Serialize rare Gemini fallbacks and honor cooldown after quota/auth errors."""
    global _GEMINI_LAST_FALLBACK
    minimum = max(
        0.0,
        float(os.getenv("TAG_AUDIT_GEMINI_MIN_SECONDS_BETWEEN_CALLS", "3.0")),
    )
    with _GEMINI_GATE_LOCK:
        now = time.monotonic()
        if now < _GEMINI_BLOCK_UNTIL:
            return False, f"cooldown {max(1, int(round(_GEMINI_BLOCK_UNTIL - now)))}s"
        wait = minimum - (now - _GEMINI_LAST_FALLBACK)
        if wait > 0:
            time.sleep(wait)
        _GEMINI_LAST_FALLBACK = time.monotonic()
        return True, ""


def _record_gemini_failure(exc: Exception) -> None:
    """Avoid repeatedly hammering free-tier/unauthorized Gemini endpoints."""
    global _GEMINI_BLOCK_UNTIL
    text = str(exc).lower()
    cooldown = 0.0
    if "429" in text or "giới hạn" in text or "rate" in text:
        cooldown = max(
            0.0,
            float(os.getenv("TAG_AUDIT_GEMINI_429_COOLDOWN_SECONDS", "60")),
        )
    elif "403" in text or "401" in text or "forbidden" in text or "unauthorized" in text:
        # 401/403 are normally access/auth problems rather than request pacing.
        # A longer cooldown prevents every scan from repeating the same failing call.
        cooldown = max(
            0.0,
            float(os.getenv("TAG_AUDIT_GEMINI_AUTH_COOLDOWN_SECONDS", "300")),
        )
    if cooldown <= 0:
        return
    with _GEMINI_GATE_LOCK:
        _GEMINI_BLOCK_UNTIL = max(_GEMINI_BLOCK_UNTIL, time.monotonic() + cooldown)


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
        observed = _blank_local_observation()
        observed["ocr_engine"] = "local-rescue-failed"

    observed = dict(observed)
    warning = f"Gemini fallback không dùng được: {type(exc).__name__}: {exc}"
    if rescue_message:
        warning += f"; rescue OCR: {rescue_message}"
    observed["ocr_warning"] = warning
    observed["gemini_fallback_failed"] = True
    observed["gemini_fallback_error"] = str(exc)
    return observed


def _mark_local_only(observed: dict, reason: str) -> dict:
    result = dict(observed)
    result["gemini_skipped"] = True
    result["gemini_skip_reason"] = reason
    return result


def install_tag_audit_barcode_contract(tag_audit_module) -> None:
    """Wrap OCR extraction, keep Gemini last-resort, then add barcode evidence."""
    if getattr(tag_audit_module, "_barcode_contract_v1", False):
        return

    original_extract = tag_audit_module._extract_tag_with_gemini

    def extract_with_barcode(image: bytes, mime_type: str, month: str | None) -> dict:
        local = _local_preflight(image, month)

        # No key means no remote fallback at all. Preserve the established local
        # warning contract instead of passing through the pacing/cooldown gate.
        if not os.getenv("GEMINI_API_KEY"):
            if local:
                observed = _mark_local_only(local, "gemini_not_configured")
                if not _local_candidate_key(local)[0]:
                    observed.setdefault(
                        "ocr_warning",
                        "RapidOCR chưa đọc đủ ITEMID + giá + ngày; Gemini fallback chưa cấu hình.",
                    )
            else:
                try:
                    observed = original_extract(image, mime_type, month)
                except Exception as exc:
                    observed = _recover_after_perception_failure(image, month, exc)

        # Most configured-key scans should stop here: deterministic local ITEMID
        # + price is enough to identify the target and continue comparison. If
        # dates are missing the business layer can REVIEW/manual-confirm them.
        elif _local_good_enough(local):
            observed = _mark_local_only(local, "local_itemid_price")

        else:
            allowed, gate_reason = _pace_optional_gemini()
            if not allowed:
                observed = _mark_local_only(
                    dict(local) if local else _blank_local_observation(),
                    gate_reason or "gemini_cooldown",
                )
                observed["ocr_warning"] = (
                    "Gemini đang tạm nghỉ để tránh gọi API quá dày; "
                    "giữ kết quả OCR local và cho phép REVIEW/nhập tay."
                )
            else:
                try:
                    observed = original_extract(image, mime_type, month)
                except Exception as exc:
                    _record_gemini_failure(exc)
                    # Keep the original three-argument recovery contract so tests
                    # and downstream monkeypatches remain compatible.
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
