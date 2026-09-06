import cv2
import numpy as np

from backend import tag_audit_image_quality_contract as quality


def _jpeg(image) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def _codes(diagnostics):
    return {item["code"] for item in diagnostics["warnings"]}


def test_small_dark_low_contrast_image_is_diagnosed_and_upscaled():
    image = np.full((180, 320, 3), 25, dtype=np.uint8)
    result = quality.inspect_and_preprocess_image(_jpeg(image))

    codes = _codes(result.diagnostics)
    assert "image_too_small" in codes
    assert "image_too_dark" in codes
    assert "image_low_contrast" in codes
    assert result.diagnostics["ocr_width"] > 320
    assert result.diagnostics["ocr_height"] > 180
    assert result.diagnostics["quality_ok"] is False


def test_large_image_is_bounded_for_ocr_cost():
    image = np.zeros((1800, 3200, 3), dtype=np.uint8)
    cv2.putText(image, "P03845 57,750", (200, 900), cv2.FONT_HERSHEY_SIMPLEX, 4, (255, 255, 255), 10)
    result = quality.inspect_and_preprocess_image(_jpeg(image))

    assert max(result.diagnostics["ocr_width"], result.diagnostics["ocr_height"]) == 2000
    assert result.diagnostics["preprocess_scale"] < 1


def test_sharp_normal_exposure_image_keeps_advisory_quality_clear():
    image = np.full((900, 1400, 3), 180, dtype=np.uint8)
    cv2.rectangle(image, (100, 150), (1300, 750), (40, 40, 40), 5)
    cv2.putText(image, "P03845", (180, 420), cv2.FONT_HERSHEY_SIMPLEX, 4, (20, 20, 20), 10)
    cv2.putText(image, "57,750 VND", (180, 620), cv2.FONT_HERSHEY_SIMPLEX, 3, (20, 20, 20), 8)
    result = quality.inspect_and_preprocess_image(_jpeg(image))

    assert result.diagnostics["width"] == 1400
    assert result.diagnostics["height"] == 900
    assert result.diagnostics["preprocessor"] == "opencv-clahe-v1"
    assert "image_too_small" not in _codes(result.diagnostics)
    assert "image_too_dark" not in _codes(result.diagnostics)
    assert "image_too_bright" not in _codes(result.diagnostics)


def test_invalid_image_fails_before_ocr():
    try:
        quality.inspect_and_preprocess_image(b"not-an-image")
    except RuntimeError as exc:
        assert "Không giải mã được ảnh tem" in str(exc)
    else:
        raise AssertionError("invalid image must be rejected")


def test_wrapper_is_fail_open_and_preserves_original_ocr_result(monkeypatch):
    class FakeLocalOCR:
        _image_quality_contract_v1 = False

        @staticmethod
        def extract_tag_with_rapidocr(image, month):
            return {"item_id": "P03845", "received": image, "month": month}

    module = FakeLocalOCR()
    quality.install_tag_audit_image_quality_contract(module)

    monkeypatch.setattr(
        quality,
        "inspect_and_preprocess_image",
        lambda image: (_ for _ in ()).throw(RuntimeError("quality unavailable")),
    )
    observed = module.extract_tag_with_rapidocr(b"original", "2026-09")

    assert observed["item_id"] == "P03845"
    assert observed["received"] == b"original"
    assert observed["image_quality_warning"] == "quality unavailable"
