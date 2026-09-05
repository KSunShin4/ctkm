# -*- coding: utf-8 -*-
"""Local-first OCR for Pharmacity shelf labels using RapidOCR/ONNX.

RapidOCR is the primary text reader. Gemini remains an optional fallback only
when local OCR cannot recover the minimum fields required for a deterministic
comparison. Neither OCR engine decides CTKM correctness.
"""
from __future__ import annotations

from datetime import date
import os
import re
import threading

_ENGINE = None
_ENGINE_LOCK = threading.Lock()

_ITEM_RE = re.compile(r"(?<![A-Z0-9])P\s*[-_.:]?\s*(\d{3,8})(?!\d)", re.IGNORECASE)
_DATE_RANGE_RE = re.compile(
    r"(?:KM\s*[:：]?\s*)?(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s*[/-]\s*(\d{2,4}))?"
    r"\s*(?:-|–|—|~|TO|ĐẾN|DEN)\s*"
    r"(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s*[/-]\s*(\d{2,4}))?",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.,]\d{3})+|\d{4,9})\s*(?:VND|VNĐ|Đ|D)?\b", re.IGNORECASE)
_PROMO_RE = re.compile(r"\b(?:GI[ẢA]M|MUA|T[ẶA]NG|TANG|SALE|KM)\b", re.IGNORECASE)


def _get_engine():
    global _ENGINE
    if _ENGINE is not None:
        return _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            from rapidocr import RapidOCR

            _ENGINE = RapidOCR()
    return _ENGINE


def _canonical_itemids(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _ITEM_RE.finditer(str(text or "").upper()):
        item = f"P{match.group(1)}"
        if item not in seen:
            seen.add(item)
            found.append(item)
    return found


def _year(value: str | None) -> int:
    text = str(value or "").strip()
    match = re.match(r"^(\d{4})-(\d{2})$", text)
    if match:
        return int(match.group(1))
    return date.today().year


def _iso(day: str, month: str, year: str | None, fallback_year: int) -> str | None:
    try:
        y = int(year) if year else fallback_year
        if y < 100:
            y += 2000
        return date(y, int(month), int(day)).isoformat()
    except (TypeError, ValueError):
        return None


def _box_height(box) -> float:
    try:
        ys = [float(point[1]) for point in box]
        return max(ys) - min(ys)
    except Exception:
        return 0.0


def _parse_money(text: str) -> list[int]:
    values: list[int] = []
    for match in _MONEY_RE.finditer(str(text or "")):
        digits = re.sub(r"\D", "", match.group(1))
        if not digits:
            continue
        value = int(digits)
        if 1000 <= value <= 100_000_000:
            values.append(value)
    return values


def _rapidocr_lines(image: bytes) -> list[dict]:
    import cv2
    import numpy as np

    array = np.frombuffer(image, dtype=np.uint8)
    decoded = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if decoded is None:
        raise RuntimeError("Không giải mã được ảnh tem")

    result = _get_engine()(decoded)
    texts = list(getattr(result, "txts", None) or [])
    scores = list(getattr(result, "scores", None) or [])
    boxes = list(getattr(result, "boxes", None) or [])
    lines: list[dict] = []
    for index, text in enumerate(texts):
        clean = str(text or "").strip()
        if not clean:
            continue
        try:
            score = float(scores[index]) if index < len(scores) else 0.0
        except (TypeError, ValueError):
            score = 0.0
        box = boxes[index] if index < len(boxes) else None
        lines.append({"text": clean, "score": score, "height": _box_height(box)})
    return lines


def extract_tag_with_rapidocr(image: bytes, month: str | None) -> dict:
    lines = _rapidocr_lines(image)
    if not lines:
        raise RuntimeError("RapidOCR không đọc được chữ trên ảnh")

    raw_text = "\n".join(line["text"] for line in lines)[:1200]
    itemids = _canonical_itemids(raw_text)
    item_id = itemids[0] if len(itemids) == 1 else ""

    promo_from = None
    promo_to = None
    date_text = ""
    fallback_year = _year(month)
    for line in lines:
        match = _DATE_RANGE_RE.search(line["text"])
        if not match:
            continue
        date_text = line["text"]
        promo_from = _iso(match.group(1), match.group(2), match.group(3), fallback_year)
        promo_to = _iso(match.group(4), match.group(5), match.group(6), fallback_year)
        if promo_from and promo_to:
            break

    promo_text = ""
    for line in lines:
        text = line["text"]
        if _PROMO_RE.search(text) and not _DATE_RANGE_RE.search(text):
            promo_text = text
            break

    # Shelf-tag current price is deliberately printed much larger than the old
    # price. Use OCR box height as the deterministic primary ranking signal.
    # Never treat the numeric part of ITEMID (P20383) as a money candidate.
    price_candidates: list[tuple[float, float, int]] = []
    for line in lines:
        if _ITEM_RE.search(line["text"]):
            continue
        for value in _parse_money(line["text"]):
            price_candidates.append((line["height"], line["score"], value))
    price_candidates.sort(key=lambda value: (value[0], value[1]), reverse=True)
    promo_price = price_candidates[0][2] if price_candidates else None
    normal_price = None
    if promo_price is not None:
        for _, _, value in price_candidates[1:]:
            if value != promo_price:
                normal_price = value
                break

    scores = [line["score"] for line in lines if line["score"] > 0]
    confidence = sum(scores) / len(scores) if scores else 0.0
    return {
        "item_id": item_id,
        "item_id_candidates": itemids,
        "barcode": "",
        "product_name": "",
        "promo_text": promo_text,
        "normal_price": normal_price,
        "promo_price": promo_price,
        "date_text": date_text,
        "promo_from": promo_from,
        "promo_to": promo_to,
        "raw_text": raw_text,
        "confidence": round(confidence, 4),
        "ocr_engine": "rapidocr",
    }


def _minimum_complete(observed: dict) -> bool:
    return bool(
        len(observed.get("item_id_candidates") or []) == 1
        and observed.get("promo_price") is not None
        and observed.get("promo_from")
        and observed.get("promo_to")
    )


def _merge_local_with_gemini(local: dict, gemini: dict) -> dict:
    merged = dict(gemini)
    # Deterministic local ITEMID has priority when unique. For other fields keep
    # a concrete local value and let Gemini only fill blanks.
    for key in (
        "item_id", "item_id_candidates", "promo_price", "normal_price",
        "promo_from", "promo_to", "date_text", "promo_text", "raw_text",
    ):
        value = local.get(key)
        if value not in (None, "", [], ()):  # preserve zero only if ever valid
            merged[key] = value
    merged["confidence"] = max(float(local.get("confidence") or 0), float(gemini.get("confidence") or 0))
    merged["ocr_engine"] = "rapidocr+gemini"
    return merged


def install_tag_audit_local_ocr_contract(tag_audit_module) -> None:
    if getattr(tag_audit_module, "_local_ocr_contract_v1", False):
        return

    original_gemini = tag_audit_module._extract_tag_with_gemini
    original_context_payload = getattr(tag_audit_module, "_context_payload", None)

    def local_first_extract(image: bytes, mime_type: str, month: str | None) -> dict:
        local_error = None
        try:
            local = extract_tag_with_rapidocr(image, month)
            if _minimum_complete(local):
                return local
        except Exception as exc:
            local = None
            local_error = str(exc)

        if os.getenv("GEMINI_API_KEY"):
            gemini = original_gemini(image, mime_type, month)
            if local:
                return _merge_local_with_gemini(local, gemini)
            gemini["ocr_engine"] = "gemini"
            return gemini

        if local:
            local["ocr_warning"] = "RapidOCR chưa đọc đủ ITEMID + giá + ngày; Gemini fallback chưa cấu hình."
            return local
        raise RuntimeError(local_error or "RapidOCR không khả dụng và Gemini fallback chưa cấu hình")

    tag_audit_module._extract_tag_with_gemini = local_first_extract

    # Lightweight facades used by unit tests may expose only extractor/comparator.
    # Production tag_audit_contract has _context_payload, so enrich it there only.
    if callable(original_context_payload):
        def context_payload_with_local(cache: dict) -> dict:
            payload = original_context_payload(cache)
            payload["local_ocr_available"] = True
            payload["ocr_primary"] = "rapidocr"
            payload["gemini_fallback_available"] = bool(os.getenv("GEMINI_API_KEY"))
            return payload

        tag_audit_module._context_payload = context_payload_with_local

    tag_audit_module.extract_tag_with_rapidocr = extract_tag_with_rapidocr
    tag_audit_module._local_ocr_contract_v1 = True
