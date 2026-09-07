# -*- coding: utf-8 -*-
"""Local-first OCR for Pharmacity shelf labels using RapidOCR/ONNX.

RapidOCR is the primary text reader. Gemini remains an optional fallback only
when local OCR cannot recover the minimum fields required for a deterministic
comparison. Neither OCR engine decides CTKM correctness.

Targeting v1 adds a conservative center-ROI + right-angle orientation search.
The full frame is always retained as a candidate, so targeting cannot make an
otherwise readable off-center tag disappear. Extra OCR passes run only when the
initial candidates do not already contain one ITEMID + price + date range.
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

_CENTER_X_INSET = 0.08
_CENTER_Y_INSET = 0.15
_ROTATIONS = (90, 270, 180)


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


def _ocr_lines_from_array(decoded, *, variant: str, rotation: int) -> list[dict]:
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
        lines.append({
            "text": clean,
            "score": score,
            "height": _box_height(box),
            "ocr_variant": variant,
            "ocr_rotation_degrees": int(rotation),
        })
    return lines


def _center_crop(decoded):
    height, width = decoded.shape[:2]
    x0 = int(round(width * _CENTER_X_INSET))
    x1 = int(round(width * (1.0 - _CENTER_X_INSET)))
    y0 = int(round(height * _CENTER_Y_INSET))
    y1 = int(round(height * (1.0 - _CENTER_Y_INSET)))
    if x1 - x0 < 180 or y1 - y0 < 180:
        return None
    crop = decoded[y0:y1, x0:x1]
    return crop if getattr(crop, "size", 0) else None


def _rotate_image(decoded, degrees: int):
    import cv2

    if degrees == 90:
        return cv2.rotate(decoded, cv2.ROTATE_90_CLOCKWISE)
    if degrees == 180:
        return cv2.rotate(decoded, cv2.ROTATE_180)
    if degrees == 270:
        return cv2.rotate(decoded, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return decoded


def _line_evidence(lines: list[dict]) -> dict:
    raw_text = "\n".join(str(line.get("text") or "") for line in lines)
    itemids = _canonical_itemids(raw_text)
    has_date = any(_DATE_RANGE_RE.search(str(line.get("text") or "")) for line in lines)
    money_count = 0
    promo_hint = False
    valid_scores: list[float] = []
    for line in lines:
        text = str(line.get("text") or "")
        if not _ITEM_RE.search(text):
            money_count += len(_parse_money(text))
        if _PROMO_RE.search(text):
            promo_hint = True
        try:
            score = float(line.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        if score > 0:
            valid_scores.append(score)

    average_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
    unique_item = len(itemids) == 1
    complete = bool(unique_item and has_date and money_count >= 1)
    # Structured shelf-tag evidence dominates generic OCR confidence. Multiple
    # ITEMIDs are deliberately penalized so a busy multi-tag frame does not beat
    # a coherent center crop merely because it contains more readable text.
    structure_score = 0.0
    if unique_item:
        structure_score += 10.0
    elif itemids:
        structure_score += max(0.0, 3.0 - float(len(itemids) - 1))
    if has_date:
        structure_score += 5.0
    structure_score += min(2, money_count) * 2.0
    if promo_hint:
        structure_score += 1.0
    structure_score += min(1.0, average_score)
    return {
        "itemids": itemids,
        "unique_item": unique_item,
        "has_date": has_date,
        "money_count": money_count,
        "promo_hint": promo_hint,
        "average_score": average_score,
        "complete": complete,
        "structure_score": structure_score,
    }


def _candidate_key(candidate: dict) -> tuple:
    evidence = candidate["evidence"]
    # If two candidates have equivalent structured evidence, prefer the center
    # ROI because the UI explicitly asks the operator to put one tag in the frame.
    center_bonus = 1 if candidate.get("variant") == "center" else 0
    rotation_bonus = 1 if int(candidate.get("rotation") or 0) == 0 else 0
    return (
        int(bool(evidence["complete"])),
        int(bool(evidence["unique_item"])),
        int(bool(evidence["has_date"])),
        min(2, int(evidence["money_count"])),
        float(evidence["structure_score"]),
        center_bonus,
        rotation_bonus,
        float(evidence["average_score"]),
    )


def _choose_best_ocr_candidate(candidates: list[dict]) -> dict | None:
    usable = [candidate for candidate in candidates if candidate.get("lines")]
    if not usable:
        return None
    return max(usable, key=_candidate_key)


def _rapidocr_lines(image: bytes) -> list[dict]:
    import cv2
    import numpy as np

    array = np.frombuffer(image, dtype=np.uint8)
    decoded = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if decoded is None:
        raise RuntimeError("Không giải mã được ảnh tem")

    center = _center_crop(decoded)
    candidates: list[dict] = []

    def add_candidate(frame, variant: str, rotation: int) -> None:
        if frame is None:
            return
        rotated = _rotate_image(frame, rotation)
        lines = _ocr_lines_from_array(rotated, variant=variant, rotation=rotation)
        candidates.append({
            "variant": variant,
            "rotation": rotation,
            "lines": lines,
            "evidence": _line_evidence(lines),
        })

    # Always compare the full frame with the operator-guided center region first.
    add_candidate(decoded, "full", 0)
    add_candidate(center, "center", 0)
    best = _choose_best_ocr_candidate(candidates)
    if best and best["evidence"]["complete"]:
        return best["lines"]

    # A sideways phone photo is common in store use. Search only right-angle
    # rotations, and stop as soon as a complete candidate exists for that angle.
    for rotation in _ROTATIONS:
        add_candidate(center, "center", rotation)
        add_candidate(decoded, "full", rotation)
        best = _choose_best_ocr_candidate(candidates)
        if best and best["evidence"]["complete"]:
            return best["lines"]

    best = _choose_best_ocr_candidate(candidates)
    if best:
        return best["lines"]
    return []


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
    first_line = lines[0] if lines else {}
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
        "ocr_target_region": str(first_line.get("ocr_variant") or "full"),
        "ocr_rotation_degrees": int(first_line.get("ocr_rotation_degrees") or 0),
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
        "image_quality", "image_quality_warning", "ocr_target_region",
        "ocr_rotation_degrees",
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

    # Install the image-quality wrapper on this module itself. It is fail-open:
    # if preprocessing cannot run, the original RapidOCR extractor still receives
    # the original bytes and remains responsible only for OCR.
    from backend.tag_audit_image_quality_contract import install_tag_audit_image_quality_contract
    import backend.tag_audit_local_ocr_contract as local_ocr_module

    install_tag_audit_image_quality_contract(local_ocr_module)

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

    # Barcode is another supporting perception module. Install it only after the
    # local-first OCR wrapper exists so ZXing augments that observation instead of
    # being overwritten by this installer. It never maps barcode -> ITEMID.
    from backend.tag_audit_barcode_contract import install_tag_audit_barcode_contract
    install_tag_audit_barcode_contract(tag_audit_module)

    # Lightweight facades used by unit tests may expose only extractor/comparator.
    # Production tag_audit_contract has _context_payload, so enrich it there only.
    if callable(original_context_payload):
        def context_payload_with_local(cache: dict) -> dict:
            payload = original_context_payload(cache)
            payload["local_ocr_available"] = True
            payload["ocr_primary"] = "rapidocr"
            payload["gemini_fallback_available"] = bool(os.getenv("GEMINI_API_KEY"))
            payload["image_preprocessor"] = "opencv-clahe-v1"
            payload["ocr_targeting"] = "center-roi-orientation-v1"
            payload["barcode_fallback"] = "zxingcpp"
            return payload

        tag_audit_module._context_payload = context_payload_with_local

    tag_audit_module.extract_tag_with_rapidocr = extract_tag_with_rapidocr
    tag_audit_module._local_ocr_contract_v1 = True
