# -*- coding: utf-8 -*-
"""Focused rescue OCR for store photos containing several shelf tags.

The operator aims the green scan line at one tag. This module retries local OCR
on progressively tighter crops around the frame centre so tiny ITEMID text gets
more pixels and neighbouring tags are excluded. It never maps barcode to ITEMID
and never decides CTKM correctness.
"""
from __future__ import annotations


def _encode(image) -> bytes:
    import cv2

    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 96])
    if not ok:
        raise RuntimeError("Không mã hoá được ảnh rescue OCR")
    return encoded.tobytes()


def _decode(image_bytes: bytes):
    import cv2
    import numpy as np

    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise RuntimeError("Không giải mã được ảnh rescue OCR")
    return image


def _center_crop(image, width_ratio: float, height_ratio: float):
    height, width = image.shape[:2]
    crop_w = max(220, int(round(width * width_ratio)))
    crop_h = max(180, int(round(height * height_ratio)))
    crop_w = min(width, crop_w)
    crop_h = min(height, crop_h)
    cx, cy = width // 2, height // 2
    x0 = max(0, cx - crop_w // 2)
    y0 = max(0, cy - crop_h // 2)
    x1 = min(width, x0 + crop_w)
    y1 = min(height, y0 + crop_h)
    return image[y0:y1, x0:x1]


def _upscale_for_itemid(image):
    import cv2

    height, width = image.shape[:2]
    long_edge = max(height, width)
    if long_edge >= 1800:
        return image
    scale = min(3.0, 1800.0 / max(1, long_edge))
    if scale <= 1.05:
        return image
    return cv2.resize(
        image,
        (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
        interpolation=cv2.INTER_CUBIC,
    )


def _score(observed: dict) -> tuple:
    itemids = list(observed.get("item_id_candidates") or [])
    unique_item = len(itemids) == 1
    has_price = observed.get("promo_price") is not None
    has_dates = bool(observed.get("promo_from") and observed.get("promo_to"))
    has_promo = bool(observed.get("promo_text"))
    confidence = float(observed.get("confidence") or 0)
    return (
        int(unique_item and has_price and has_dates),
        int(unique_item),
        int(has_dates),
        int(has_price),
        int(has_promo),
        confidence,
    )


def rescue_with_focused_local_ocr(image_bytes: bytes, month: str | None) -> dict | None:
    """Return the best local-only candidate from tight centre crops."""
    from backend import tag_audit_local_ocr_contract as local_ocr

    image = _decode(image_bytes)
    candidates: list[dict] = []
    # First crop roughly one Pharmacity shelf-label cell around the scan-line
    # centre, then widen slightly in case the operator is not perfectly centred.
    for label, width_ratio, height_ratio in (
        ("focus-45x28", 0.45, 0.28),
        ("focus-55x34", 0.55, 0.34),
        ("focus-65x40", 0.65, 0.40),
    ):
        crop = _upscale_for_itemid(_center_crop(image, width_ratio, height_ratio))
        try:
            observed = local_ocr.extract_tag_with_rapidocr(_encode(crop), month)
        except Exception:
            continue
        observed = dict(observed)
        observed["ocr_target_region"] = label
        observed["ocr_rescue"] = True
        candidates.append(observed)
        if _score(observed)[0]:
            return observed

    return max(candidates, key=_score) if candidates else None
