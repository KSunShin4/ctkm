import numpy as np

from backend import tag_audit_local_ocr_contract as local_ocr
from backend import tag_audit_rescue_ocr as rescue


def test_itemid_anchor_keeps_lower_right_code_that_legacy_symmetric_crop_clips():
    image = np.zeros((1000, 800, 3), dtype=np.uint8)

    # Real Pharmacity layout seen in store: the Pxxxxx code is right/below the
    # centred large price. Put a bright marker at the same normalized anchor.
    marker_x = int(round(800 * 0.82))
    marker_y = int(round(1000 * 0.59))
    image[marker_y - 2:marker_y + 3, marker_x - 2:marker_x + 3] = 255

    legacy = rescue._center_crop(image, 0.55, 0.34)
    anchored = rescue._ratio_crop(
        image,
        center_x=0.80,
        center_y=0.59,
        width_ratio=0.34,
        height_ratio=0.22,
    )

    assert legacy is not None
    assert anchored is not None
    assert int(legacy.max()) == 0
    assert int(anchored.max()) == 255


def test_itemid_anchor_is_centered_inside_its_ocr_crop():
    image = np.zeros((1000, 800, 3), dtype=np.uint8)
    marker_x = int(round(800 * 0.80))
    marker_y = int(round(1000 * 0.59))
    image[marker_y, marker_x] = 255

    crop = rescue._ratio_crop(
        image,
        center_x=0.80,
        center_y=0.59,
        width_ratio=0.34,
        height_ratio=0.22,
    )

    ys, xs = np.where(crop[:, :, 0] == 255)
    assert len(xs) == 1
    assert abs(int(xs[0]) - crop.shape[1] // 2) <= 1
    assert abs(int(ys[0]) - crop.shape[0] // 2) <= 1


def test_rescue_retains_unique_itemid_from_anchor_when_other_crops_only_read_price(monkeypatch):
    image = np.zeros((1000, 800, 3), dtype=np.uint8)
    monkeypatch.setattr(rescue, "_decode", lambda image_bytes: image)
    monkeypatch.setattr(rescue, "_upscale_for_itemid", lambda crop, target_long_edge=2000: crop)
    monkeypatch.setattr(
        rescue,
        "_encode",
        lambda crop: f"{crop.shape[1]}x{crop.shape[0]}".encode("ascii"),
    )

    calls = []

    def fake_local_extract(encoded, month):
        calls.append(encoded)
        if encoded == b"272x220":
            return {
                "item_id": "P25175",
                "item_id_candidates": ["P25175"],
                "promo_price": None,
                "promo_from": None,
                "promo_to": None,
                "promo_text": "",
                "confidence": 0.80,
                "ocr_engine": "rapidocr",
            }
        return {
            "item_id": "",
            "item_id_candidates": [],
            "promo_price": 500000,
            "promo_from": "2026-09-06",
            "promo_to": "2026-09-15",
            "promo_text": "MUA 1 TANG 1",
            "confidence": 0.95,
            "ocr_engine": "rapidocr",
        }

    monkeypatch.setattr(local_ocr, "extract_tag_with_rapidocr", fake_local_extract)

    observed = rescue.rescue_with_focused_local_ocr(b"image", "2026-09")

    assert calls[0] == b"272x220"
    assert observed["item_id"] == "P25175"
    assert observed["item_id_candidates"] == ["P25175"]
    assert observed["ocr_target_region"] == "itemid-anchor-34x22"
    assert observed["ocr_rescue"] is True


def test_complete_itemid_anchor_short_circuits_before_wider_rescue_passes(monkeypatch):
    image = np.zeros((1000, 800, 3), dtype=np.uint8)
    monkeypatch.setattr(rescue, "_decode", lambda image_bytes: image)
    monkeypatch.setattr(rescue, "_upscale_for_itemid", lambda crop, target_long_edge=2000: crop)
    monkeypatch.setattr(rescue, "_encode", lambda crop: b"anchor")

    calls = []

    def fake_local_extract(encoded, month):
        calls.append(encoded)
        return {
            "item_id": "P25175",
            "item_id_candidates": ["P25175"],
            "promo_price": 500000,
            "promo_from": "2026-09-06",
            "promo_to": "2026-09-15",
            "promo_text": "MUA 1 TANG 1",
            "confidence": 0.90,
            "ocr_engine": "rapidocr",
        }

    monkeypatch.setattr(local_ocr, "extract_tag_with_rapidocr", fake_local_extract)

    observed = rescue.rescue_with_focused_local_ocr(b"image", "2026-09")

    assert len(calls) == 1
    assert observed["item_id"] == "P25175"
    assert observed["promo_price"] == 500000
    assert observed["ocr_target_region"] == "itemid-anchor-34x22"
