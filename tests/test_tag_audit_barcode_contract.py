from types import SimpleNamespace

import numpy as np

from backend import tag_audit_barcode_contract as barcode_contract


def test_zxing_dependency_is_importable():
    import zxingcpp

    assert hasattr(zxingcpp, "read_barcodes")


def test_single_numeric_candidate_is_supporting_barcode(monkeypatch):
    monkeypatch.setattr(barcode_contract, "_decode_image", lambda image: np.zeros((4, 4, 3), dtype=np.uint8))
    monkeypatch.setattr(barcode_contract, "_read_zxing_barcodes", lambda image: ["8850029850726"])

    result = barcode_contract.extract_supporting_barcodes(b"image")

    assert result == {
        "barcode": "8850029850726",
        "barcode_candidates": ["8850029850726"],
        "barcode_source": "zxingcpp",
    }


def test_multiple_numeric_candidates_are_ambiguous_not_guessed(monkeypatch):
    monkeypatch.setattr(barcode_contract, "_decode_image", lambda image: object())
    monkeypatch.setattr(
        barcode_contract,
        "_read_zxing_barcodes",
        lambda image: ["8850029850726", "3546895533263"],
    )

    result = barcode_contract.extract_supporting_barcodes(b"image")

    assert result["barcode"] == ""
    assert result["barcode_candidates"] == ["8850029850726", "3546895533263"]
    assert result["barcode_source"] == "zxingcpp_ambiguous"


def test_wrapper_does_not_override_existing_ocr_barcode(monkeypatch):
    module = SimpleNamespace(
        _barcode_contract_v1=False,
        _extract_tag_with_gemini=lambda image, mime_type, month: {
            "item_id": "P03845",
            "barcode": "8850029850726",
        },
    )
    monkeypatch.setattr(
        barcode_contract,
        "extract_supporting_barcodes",
        lambda image: (_ for _ in ()).throw(AssertionError("ZXing must not run")),
    )

    barcode_contract.install_tag_audit_barcode_contract(module)
    observed = module._extract_tag_with_gemini(b"image", "image/jpeg", "2026-09")

    assert observed["barcode"] == "8850029850726"
    assert observed["barcode_source"] == "ocr"
    assert observed["barcode_candidates"] == ["8850029850726"]


def test_wrapper_fills_blank_barcode_but_keeps_itemid_unchanged(monkeypatch):
    module = SimpleNamespace(
        _barcode_contract_v1=False,
        _extract_tag_with_gemini=lambda image, mime_type, month: {
            "item_id": "P03845",
            "barcode": "",
            "promo_price": 57750,
        },
    )
    monkeypatch.setattr(
        barcode_contract,
        "extract_supporting_barcodes",
        lambda image: {
            "barcode": "8850029850726",
            "barcode_candidates": ["8850029850726"],
            "barcode_source": "zxingcpp",
        },
    )

    barcode_contract.install_tag_audit_barcode_contract(module)
    observed = module._extract_tag_with_gemini(b"image", "image/jpeg", "2026-09")

    assert observed["item_id"] == "P03845"
    assert observed["promo_price"] == 57750
    assert observed["barcode"] == "8850029850726"
    assert observed["barcode_source"] == "zxingcpp"


def test_wrapper_is_fail_open_when_zxing_errors(monkeypatch):
    module = SimpleNamespace(
        _barcode_contract_v1=False,
        _extract_tag_with_gemini=lambda image, mime_type, month: {
            "item_id": "P03845",
            "barcode": "",
        },
    )
    monkeypatch.setattr(
        barcode_contract,
        "extract_supporting_barcodes",
        lambda image: (_ for _ in ()).throw(RuntimeError("decoder unavailable")),
    )

    barcode_contract.install_tag_audit_barcode_contract(module)
    observed = module._extract_tag_with_gemini(b"image", "image/jpeg", "2026-09")

    assert observed["item_id"] == "P03845"
    assert observed["barcode"] == ""
    assert observed["barcode_source"] == "zxingcpp_error"
    assert observed["barcode_warning"] == "decoder unavailable"


def test_gemini_403_does_not_discard_local_rescue_observation(monkeypatch):
    def failing_extract(image, mime_type, month):
        raise RuntimeError("OCR Gemini thất bại: HTTP 403")

    module = SimpleNamespace(
        _barcode_contract_v1=False,
        _extract_tag_with_gemini=failing_extract,
    )
    monkeypatch.setattr(
        barcode_contract,
        "_recover_after_perception_failure",
        lambda image, month, exc: {
            "item_id": "P25175",
            "item_id_candidates": ["P25175"],
            "barcode": "",
            "promo_price": 500000,
            "promo_from": "2026-09-06",
            "promo_to": "2026-09-15",
            "ocr_engine": "rapidocr",
            "ocr_rescue": True,
            "ocr_warning": str(exc),
        },
    )
    monkeypatch.setattr(
        barcode_contract,
        "extract_supporting_barcodes",
        lambda image: {
            "barcode": "",
            "barcode_candidates": [],
            "barcode_source": "zxingcpp_none",
        },
    )

    barcode_contract.install_tag_audit_barcode_contract(module)
    observed = module._extract_tag_with_gemini(b"image", "image/jpeg", "2026-09")

    assert observed["item_id"] == "P25175"
    assert observed["promo_price"] == 500000
    assert observed["ocr_rescue"] is True
    assert observed["barcode_source"] == "zxingcpp_none"
