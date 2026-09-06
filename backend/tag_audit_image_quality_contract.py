# -*- coding: utf-8 -*-
"""OpenCV image-quality and conservative preprocessing for shelf-tag OCR.

This module has one responsibility: decode a submitted image, report objective
quality diagnostics, and produce a bounded OCR-ready image. It never identifies
an ITEMID and never decides whether a CTKM tag is correct.

Quality findings are advisory by default. The scanner must not convert a blurry,
dark, or low-contrast photo into a business PASS/FAIL; those signals are surfaced
to the operator and OCR/comparison keeps its existing review semantics.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


_MAX_OCR_LONG_EDGE = 2000
_MIN_OCR_LONG_EDGE = 1100
_MIN_SHORT_EDGE_WARNING = 420
_BLUR_WARNING_VARIANCE = 55.0
_DARK_WARNING_MEAN = 55.0
_BRIGHT_WARNING_MEAN = 225.0
_LOW_CONTRAST_STDDEV = 28.0


@dataclass(frozen=True)
class ImageQualityResult:
    image: object
    diagnostics: dict


def _round(value: float, digits: int = 2) -> float:
    if not math.isfinite(float(value)):
        return 0.0
    return round(float(value), digits)


def inspect_and_preprocess_image(image_bytes: bytes) -> ImageQualityResult:
    """Decode bytes once, collect diagnostics, and return a conservative OCR image."""
    import cv2
    import numpy as np

    array = np.frombuffer(image_bytes, dtype=np.uint8)
    decoded = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if decoded is None or decoded.size == 0:
        raise RuntimeError("Không giải mã được ảnh tem")

    height, width = decoded.shape[:2]
    gray = cv2.cvtColor(decoded, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    contrast = float(gray.std())
    blur_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    dark_ratio = float((gray <= 20).mean())
    bright_ratio = float((gray >= 245).mean())

    warnings: list[dict] = []
    if min(width, height) < _MIN_SHORT_EDGE_WARNING:
        warnings.append({
            "code": "image_too_small",
            "message": "Tem chiếm quá ít điểm ảnh; hãy chụp gần hơn.",
        })
    if blur_variance < _BLUR_WARNING_VARIANCE:
        warnings.append({
            "code": "image_blurry",
            "message": "Ảnh có dấu hiệu bị mờ/rung; giữ máy chắc và chụp lại gần hơn nếu OCR thiếu dữ liệu.",
        })
    if brightness < _DARK_WARNING_MEAN:
        warnings.append({
            "code": "image_too_dark",
            "message": "Ảnh khá tối; tăng ánh sáng hoặc đưa tem ra khỏi vùng bóng.",
        })
    elif brightness > _BRIGHT_WARNING_MEAN:
        warnings.append({
            "code": "image_too_bright",
            "message": "Ảnh quá sáng; tránh ánh đèn chiếu trực tiếp vào tem.",
        })
    if contrast < _LOW_CONTRAST_STDDEV:
        warnings.append({
            "code": "image_low_contrast",
            "message": "Chữ và nền có tương phản thấp; hãy chụp gần hơn hoặc đổi góc.",
        })
    if bright_ratio > 0.30:
        warnings.append({
            "code": "image_glare",
            "message": "Ảnh có vùng cháy sáng lớn; đổi góc để giảm phản sáng trên tem.",
        })

    long_edge = max(width, height)
    target = decoded
    scale = 1.0
    if long_edge > _MAX_OCR_LONG_EDGE:
        scale = _MAX_OCR_LONG_EDGE / float(long_edge)
    elif long_edge < _MIN_OCR_LONG_EDGE:
        scale = _MIN_OCR_LONG_EDGE / float(long_edge)
    if abs(scale - 1.0) > 0.01:
        interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
        target = cv2.resize(
            decoded,
            (max(1, int(round(width * scale))), max(1, int(round(height * scale)))),
            interpolation=interpolation,
        )

    lab = cv2.cvtColor(target, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8))
    enhanced_l = clahe.apply(l_channel)
    processed = cv2.cvtColor(
        cv2.merge((enhanced_l, a_channel, b_channel)), cv2.COLOR_LAB2BGR
    )

    diagnostics = {
        "width": int(width),
        "height": int(height),
        "ocr_width": int(processed.shape[1]),
        "ocr_height": int(processed.shape[0]),
        "brightness": _round(brightness),
        "contrast": _round(contrast),
        "blur_variance": _round(blur_variance),
        "dark_ratio": _round(dark_ratio, 4),
        "bright_ratio": _round(bright_ratio, 4),
        "preprocess_scale": _round(scale, 3),
        "warnings": warnings,
        "quality_ok": not warnings,
        "preprocessor": "opencv-clahe-v1",
    }
    return ImageQualityResult(image=processed, diagnostics=diagnostics)


def _encode_for_ocr(image) -> bytes:
    import cv2

    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        raise RuntimeError("Không chuẩn bị được ảnh cho OCR")
    return encoded.tobytes()


def install_tag_audit_image_quality_contract(local_ocr_module) -> None:
    """Wrap only the local OCR extractor; failures fall back to original bytes."""
    if getattr(local_ocr_module, "_image_quality_contract_v1", False):
        return

    original_extract = local_ocr_module.extract_tag_with_rapidocr

    def extract_with_quality(image: bytes, month: str | None) -> dict:
        diagnostics = None
        ocr_image = image
        quality_warning = None
        try:
            quality = inspect_and_preprocess_image(image)
            diagnostics = quality.diagnostics
            ocr_image = _encode_for_ocr(quality.image)
        except Exception as exc:
            quality_warning = str(exc)

        observed = original_extract(ocr_image, month)
        if diagnostics is not None:
            observed["image_quality"] = diagnostics
        if quality_warning:
            observed["image_quality_warning"] = quality_warning
        return observed

    local_ocr_module.extract_tag_with_rapidocr = extract_with_quality
    local_ocr_module.inspect_and_preprocess_image = inspect_and_preprocess_image
    local_ocr_module._image_quality_contract_v1 = True
