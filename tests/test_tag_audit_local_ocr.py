from backend import tag_audit_local_ocr_contract as local_ocr


def _line(text, score=0.95, height=12):
    return {"text": text, "score": score, "height": height}


def test_rapidocr_parser_prefers_printed_itemid_large_current_price_and_ctkm_year(monkeypatch):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("NIVEA SON DUONG AM DAU TAY DO 4.8G/CAY"),
            _line("GIAM 25%", height=11),
            _line("77,000VND", height=9),
            _line("57,750VND", height=31),
            _line("KM:01/09-30/09 Cay", height=8),
            _line("*P03845*", height=8),
            _line("8850029850726", height=7),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    assert observed["ocr_engine"] == "rapidocr"
    assert observed["item_id"] == "P03845"
    assert observed["item_id_candidates"] == ["P03845"]
    assert observed["promo_price"] == 57750
    assert observed["normal_price"] == 77000
    assert observed["promo_from"] == "2026-09-01"
    assert observed["promo_to"] == "2026-09-30"
    assert "GIAM 25%" in observed["promo_text"]
    assert local_ocr._minimum_complete(observed) is True


def test_rapidocr_parser_accepts_spaced_itemid(monkeypatch):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("P 20383"),
            _line("175,500VND", height=30),
            _line("195,000VND", height=10),
            _line("KM:01/09-30/09"),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")
    assert observed["item_id"] == "P20383"
    assert observed["promo_price"] == 175500
    assert observed["normal_price"] == 195000


def test_rapidocr_parser_does_not_choose_between_multiple_itemids(monkeypatch):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("P03845"),
            _line("P20383"),
            _line("57,750VND", height=30),
            _line("KM:01/09-30/09"),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")
    assert observed["item_id"] == ""
    assert observed["item_id_candidates"] == ["P03845", "P20383"]
    assert local_ocr._minimum_complete(observed) is False


def test_local_first_returns_partial_local_result_without_gemini(monkeypatch):
    class FakeTagAudit:
        _local_ocr_contract_v1 = False

        @staticmethod
        def _extract_tag_with_gemini(image, mime_type, month):
            raise AssertionError("Gemini must not be called without a key")

        @staticmethod
        def _context_payload(cache):
            return {"ready": True}

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        local_ocr,
        "extract_tag_with_rapidocr",
        lambda image, month: {
            "item_id": "P03845",
            "item_id_candidates": ["P03845"],
            "promo_price": None,
            "promo_from": None,
            "promo_to": None,
            "ocr_engine": "rapidocr",
        },
    )

    module = FakeTagAudit()
    local_ocr.install_tag_audit_local_ocr_contract(module)
    observed = module._extract_tag_with_gemini(b"image", "image/jpeg", "2026-09")

    assert observed["item_id"] == "P03845"
    assert observed["ocr_engine"] == "rapidocr"
    assert "Gemini fallback chưa cấu hình" in observed["ocr_warning"]


def test_local_first_keeps_partial_rapidocr_when_gemini_returns_403(monkeypatch):
    class FakeTagAudit:
        _local_ocr_contract_v1 = False

        @staticmethod
        def _extract_tag_with_gemini(image, mime_type, month):
            raise RuntimeError("OCR Gemini thất bại: HTTP 403")

        @staticmethod
        def _context_payload(cache):
            return {"ready": True}

    monkeypatch.setenv("GEMINI_API_KEY", "configured-but-forbidden")
    monkeypatch.setattr(
        local_ocr,
        "extract_tag_with_rapidocr",
        lambda image, month: {
            "item_id": "P25175",
            "item_id_candidates": ["P25175"],
            "promo_text": "MUA 1 TANG 1",
            "promo_price": 500000,
            "promo_from": "2026-09-06",
            "promo_to": None,
            "raw_text": "P25175 MUA 1 TANG 1 500,000 KM:06/09-15/09",
            "confidence": 0.82,
            "ocr_engine": "rapidocr",
        },
    )

    module = FakeTagAudit()
    local_ocr.install_tag_audit_local_ocr_contract(module)
    observed = module._extract_tag_with_gemini(b"image", "image/jpeg", "2026-09")

    assert observed["item_id"] == "P25175"
    assert observed["promo_price"] == 500000
    assert observed["ocr_engine"] == "rapidocr"
    assert observed["gemini_fallback_error"] == "OCR Gemini thất bại: HTTP 403"
    assert "giữ kết quả RapidOCR" in observed["ocr_warning"]