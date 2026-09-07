from types import SimpleNamespace

from backend import tag_audit_barcode_contract as barcode_contract


def _no_barcode(_image):
    return {
        "barcode": "",
        "barcode_candidates": [],
        "barcode_source": "zxingcpp_none",
    }


def test_local_itemid_and_price_skip_gemini_even_when_dates_are_partial(monkeypatch):
    remote_calls = []

    module = SimpleNamespace(
        _barcode_contract_v1=False,
        _extract_tag_with_gemini=lambda image, mime_type, month: remote_calls.append(
            (image, mime_type, month)
        ),
    )
    monkeypatch.setattr(
        barcode_contract,
        "_local_preflight",
        lambda image, month: {
            "item_id": "P25175",
            "item_id_candidates": ["P25175"],
            "barcode": "",
            "promo_price": 500000,
            "promo_from": None,
            "promo_to": None,
            "ocr_engine": "rapidocr",
        },
    )
    monkeypatch.setattr(barcode_contract, "extract_supporting_barcodes", _no_barcode)

    barcode_contract.install_tag_audit_barcode_contract(module)
    observed = module._extract_tag_with_gemini(b"image", "image/jpeg", "2026-09")

    assert remote_calls == []
    assert observed["item_id"] == "P25175"
    assert observed["promo_price"] == 500000
    assert observed["gemini_skipped"] is True
    assert observed["gemini_skip_reason"] == "local_itemid_price"


def test_gemini_runs_only_after_local_preflight_is_not_useful(monkeypatch):
    remote_calls = []

    def remote(image, mime_type, month):
        remote_calls.append((image, mime_type, month))
        return {
            "item_id": "P25175",
            "item_id_candidates": ["P25175"],
            "barcode": "",
            "promo_price": 500000,
            "promo_from": "2026-09-06",
            "promo_to": "2026-09-15",
            "ocr_engine": "gemini",
        }

    module = SimpleNamespace(
        _barcode_contract_v1=False,
        _extract_tag_with_gemini=remote,
    )
    monkeypatch.setattr(barcode_contract, "_local_preflight", lambda image, month: None)
    monkeypatch.setattr(barcode_contract, "_pace_optional_gemini", lambda: (True, ""))
    monkeypatch.setattr(barcode_contract, "extract_supporting_barcodes", _no_barcode)

    barcode_contract.install_tag_audit_barcode_contract(module)
    observed = module._extract_tag_with_gemini(b"image", "image/jpeg", "2026-09")

    assert len(remote_calls) == 1
    assert observed["ocr_engine"] == "gemini"
    assert observed["promo_to"] == "2026-09-15"


def test_gemini_cooldown_preserves_partial_local_result_without_remote_call(monkeypatch):
    def should_not_run(*args, **kwargs):
        raise AssertionError("Gemini must not run during cooldown")

    module = SimpleNamespace(
        _barcode_contract_v1=False,
        _extract_tag_with_gemini=should_not_run,
    )
    monkeypatch.setattr(
        barcode_contract,
        "_local_preflight",
        lambda image, month: {
            "item_id": "P25175",
            "item_id_candidates": ["P25175"],
            "barcode": "",
            "promo_price": None,
            "promo_from": "2026-09-06",
            "promo_to": "2026-09-15",
            "ocr_engine": "rapidocr",
        },
    )
    monkeypatch.setattr(
        barcode_contract,
        "_pace_optional_gemini",
        lambda: (False, "cooldown 45s"),
    )
    monkeypatch.setattr(barcode_contract, "extract_supporting_barcodes", _no_barcode)

    barcode_contract.install_tag_audit_barcode_contract(module)
    observed = module._extract_tag_with_gemini(b"image", "image/jpeg", "2026-09")

    assert observed["item_id"] == "P25175"
    assert observed["promo_price"] is None
    assert observed["gemini_skipped"] is True
    assert observed["gemini_skip_reason"] == "cooldown 45s"
    assert "tạm nghỉ" in observed["ocr_warning"]


def test_429_and_403_create_different_fallback_cooldowns(monkeypatch):
    monkeypatch.setenv("TAG_AUDIT_GEMINI_429_COOLDOWN_SECONDS", "7")
    monkeypatch.setenv("TAG_AUDIT_GEMINI_AUTH_COOLDOWN_SECONDS", "11")

    barcode_contract._GEMINI_BLOCK_UNTIL = 0.0
    barcode_contract._record_gemini_failure(RuntimeError("HTTP 429 rate limit"))
    after_429 = barcode_contract._GEMINI_BLOCK_UNTIL

    barcode_contract._GEMINI_BLOCK_UNTIL = 0.0
    barcode_contract._record_gemini_failure(RuntimeError("HTTP 403 forbidden"))
    after_403 = barcode_contract._GEMINI_BLOCK_UNTIL

    # Both failures block immediate retries; auth/access failures use the configured
    # longer window so every scan does not repeat a known-bad request.
    assert after_429 > 0
    assert after_403 > after_429
