# -*- coding: utf-8 -*-
"""Focused rescue OCR for store photos containing several shelf tags.

The operator aims the green scan line at one tag. Pharmacity labels place the
small Pxxxxx ITEMID near the lower-right area of the label, while the large
price is closer to the visual centre. A symmetric centre crop can therefore
read the price yet clip the ITEMID completely.

This rescue stage first tries small right/lower anchor crops that keep the
ITEMID near the middle of the OCR frame, then tries wider right-biased crops
that contain the whole target label, and finally falls back to the historical
symmetric centre crops. Compatible evidence from the right-biased target-cell
crops may be fused only when they expose one unambiguous ITEMID. Everything
remains local RapidOCR/ONNX: barcode is supporting-only and no CTKM business
decision is made here.
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


def _ratio_crop(
    image,
    *,
    center_x: float,
    center_y: float,
    width_ratio: float,
    height_ratio: float,
):
    """Crop around a normalized anchor while staying inside the image bounds."""
    height, width = image.shape[:2]
    crop_w = max(120, int(round(width * width_ratio)))
    crop_h = max(100, int(round(height * height_ratio)))
    crop_w = min(width, crop_w)
    crop_h = min(height, crop_h)

    cx = int(round(width * center_x))
    cy = int(round(height * center_y))
    x0 = cx - crop_w // 2
    y0 = cy - crop_h // 2
    x0 = max(0, min(width - crop_w, x0))
    y0 = max(0, min(height - crop_h, y0))
    x1 = x0 + crop_w
    y1 = y0 + crop_h
    crop = image[y0:y1, x0:x1]
    return crop if getattr(crop, "size", 0) else None


def _center_crop(image, width_ratio: float, height_ratio: float):
    return _ratio_crop(
        image,
        center_x=0.50,
        center_y=0.50,
        width_ratio=width_ratio,
        height_ratio=height_ratio,
    )


def _upscale_for_itemid(image, *, target_long_edge: int = 2000):
    import cv2

    height, width = image.shape[:2]
    long_edge = max(height, width)
    if long_edge >= target_long_edge:
        return image
    scale = min(4.0, float(target_long_edge) / max(1, long_edge))
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
        int(unique_item and has_price),
        int(unique_item),
        int(has_dates),
        int(has_price),
        int(has_promo),
        confidence,
    )


# The scan line is horizontally centred, but on the Pharmacity label the Pxxxxx
# identity is printed to the right and slightly below the large price. The first
# two profiles intentionally shift the OCR crop toward that anchor. The following
# profiles widen around the whole target cell, then preserve legacy symmetric
# fallbacks for unusual layouts.
_CROP_PROFILES = (
    ("itemid-anchor-34x22", 0.80, 0.59, 0.34, 0.22, 2200),
    ("itemid-anchor-42x28", 0.76, 0.60, 0.42, 0.28, 2200),
    ("cell-right-64x38", 0.57, 0.54, 0.64, 0.38, 2200),
    ("cell-right-72x44", 0.57, 0.54, 0.72, 0.44, 2200),
    ("focus-45x28", 0.50, 0.50, 0.45, 0.28, 2000),
    ("focus-55x34", 0.50, 0.50, 0.55, 0.34, 2000),
    ("focus-65x40", 0.50, 0.50, 0.65, 0.40, 2000),
)


def _is_target_cell_region(observed: dict) -> bool:
    label = str(observed.get("ocr_target_region") or "")
    return label.startswith("itemid-anchor-") or label.startswith("cell-right-")


def _fuse_target_cell_candidates(candidates: list[dict]) -> dict | None:
    """Fuse right-biased crops only when they all support one ITEMID identity.

    Small anchor crops are best for Pxxxxx; wider target-cell crops are better for
    price and KM dates. We combine them only when no right-biased crop exposes a
    competing ITEMID. Symmetric/broad fallback crops never donate fields here.
    """
    target = [candidate for candidate in candidates if _is_target_cell_region(candidate)]
    if not target:
        return None

    discovered: set[str] = set()
    for candidate in target:
        discovered.update(str(value) for value in (candidate.get("item_id_candidates") or []) if value)
    if len(discovered) != 1:
        return None
    item_id = next(iter(discovered))

    identity_candidates = [
        candidate for candidate in target
        if list(candidate.get("item_id_candidates") or []) == [item_id]
    ]
    if not identity_candidates:
        return None

    base = dict(max(identity_candidates, key=_score))
    base["item_id"] = item_id
    base["item_id_candidates"] = [item_id]

    compatible = [
        candidate for candidate in target
        if not candidate.get("item_id_candidates")
        or list(candidate.get("item_id_candidates") or []) == [item_id]
    ]
    providers = sorted(compatible, key=_score, reverse=True)
    used_regions = [str(base.get("ocr_target_region") or "")]

    for field in (
        "promo_price", "normal_price", "promo_from", "promo_to",
        "date_text", "promo_text", "raw_text", "image_quality",
        "image_quality_warning",
    ):
        if base.get(field) not in (None, "", [], ()):  # keep concrete anchor value
            continue
        for provider in providers:
            value = provider.get(field)
            if value in (None, "", [], ()):
                continue
            base[field] = value
            region = str(provider.get("ocr_target_region") or "")
            if region and region not in used_regions:
                used_regions.append(region)
            break

    base["confidence"] = max(float(candidate.get("confidence") or 0) for candidate in compatible)
    base["ocr_rescue"] = True
    if len(used_regions) > 1:
        base["ocr_rescue_fused"] = True
        base["ocr_fusion_regions"] = used_regions
        base["ocr_target_region"] = "fused:" + "+".join(used_regions)
    return base


def rescue_with_focused_local_ocr(image_bytes: bytes, month: str | None) -> dict | None:
    """Return the best local-only candidate from layout-aware focus crops."""
    from backend import tag_audit_local_ocr_contract as local_ocr

    image = _decode(image_bytes)
    candidates: list[dict] = []

    for label, center_x, center_y, width_ratio, height_ratio, target_long_edge in _CROP_PROFILES:
        crop = _ratio_crop(
            image,
            center_x=center_x,
            center_y=center_y,
            width_ratio=width_ratio,
            height_ratio=height_ratio,
        )
        if crop is None:
            continue
        crop = _upscale_for_itemid(crop, target_long_edge=target_long_edge)
        try:
            observed = local_ocr.extract_tag_with_rapidocr(_encode(crop), month)
        except Exception:
            continue

        observed = dict(observed)
        observed["ocr_target_region"] = label
        observed["ocr_rescue"] = True
        candidates.append(observed)

        # Only short-circuit when one crop independently contains the full
        # deterministic evidence. ITEMID-only candidates are retained so they can
        # later fuse with price/date from a compatible wider target-cell crop.
        if _score(observed)[0]:
            return observed

    fused = _fuse_target_cell_candidates(candidates)
    if fused is not None:
        return fused
    return max(candidates, key=_score) if candidates else None
