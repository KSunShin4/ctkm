from backend.tag_audit_itemid_contract import (
    extract_itemid_candidates,
    recover_homoglyph_sku,
    resolve_context_aware_itemid,
)
from backend.tag_audit_rescue_ocr import is_complete_observation
from backend import tag_audit_contract


def _row(item_id="P03845", promo_price=57750):
    return {
        "item_id": item_id,
        "item_name": "NIVEA SON DUONG AM DAU TAY DO 4.8G/CAY",
        "campaign_name": "GIAM 25%",
        "campaign_detail": "",
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "normal_price": 77000,
        "promo_price": promo_price,
        "expected_action": "gan_tem",
        "source_sheet": "Gắn tem",
        "key_channel": "Offline",
        "channel": "OFFLINE",
    }


def test_extract_itemid_candidates_prefers_printed_p_number():
    assert extract_itemid_candidates("*P03845*", "8850029850726") == ["P03845"]


def test_extract_itemid_candidates_accepts_common_ocr_spacing_noise():
    assert extract_itemid_candidates("Mã: P 03845", "P-20383") == ["P03845", "P20383"]


def test_extract_itemid_candidates_homoglyph_recovery():
    assert extract_itemid_candidates("P3O766") == ["P30766"]
    assert extract_itemid_candidates("P1I2S8") == ["P11258"]
    assert extract_itemid_candidates("P-3O766") == ["P30766"]
    assert extract_itemid_candidates("Mã: P 3O766", "*P1I2S8*") == ["P30766", "P11258"]
    assert extract_itemid_candidates("PROMO", "PRICE", "BILL", "POSM", "POOLS") == []


def test_recover_homoglyph_sku_rules():
    assert recover_homoglyph_sku("P3O766") == "P30766"
    assert recover_homoglyph_sku("P1I2S8") == "P11258"
    assert recover_homoglyph_sku("p03845") == "P03845"
    assert recover_homoglyph_sku("PROMO") is None
    assert recover_homoglyph_sku("PRICE") is None
    assert recover_homoglyph_sku("BILL") is None
    assert recover_homoglyph_sku("POOLS") is None
    assert recover_homoglyph_sku("P12") is None  # too short
    assert recover_homoglyph_sku("P123456789") is None  # too long


def test_resolve_context_aware_itemid_success_single_hamming_and_price():
    resolved = resolve_context_aware_itemid(
        ["P30768"],
        ["P30766"],
        observed_price=57750,
        item_price_map={"P30766": 57750},
    )
    assert resolved == ["P30766"]


def test_resolve_context_aware_itemid_already_known_remains_unchanged():
    resolved = resolve_context_aware_itemid(
        ["P30766"],
        ["P30766", "P20383"],
        observed_price=57750,
        item_price_map={"P30766": 57750},
    )
    assert resolved == ["P30766"]


def test_resolve_context_aware_itemid_price_mismatch_rejected():
    resolved = resolve_context_aware_itemid(
        ["P30768"],
        ["P30766"],
        observed_price=40000,
        item_price_map={"P30766": 57750},
    )
    assert resolved == ["P30768"]


def test_resolve_context_aware_itemid_ambiguous_multiple_skus_rejected():
    resolved = resolve_context_aware_itemid(
        ["P30768"],
        ["P30766", "P30767"],
        observed_price=57750,
        item_price_map={"P30766": 57750, "P30767": 57750},
    )
    # Ambiguous: distance is 1 to both P30766 and P30767 -> never guess
    assert resolved == ["P30768"]


def test_resolve_context_aware_itemid_multiple_candidates_rejected():
    resolved = resolve_context_aware_itemid(
        ["P30768", "P20389"],
        ["P30766", "P20383"],
    )
    # Never guess when multiple observed candidates exist
    assert resolved == ["P30768", "P20389"]


def test_itemid_primary_contract_recovers_id_from_raw_text(monkeypatch):
    class Facade:
        _itemid_primary_contract_v1 = False

        @staticmethod
        def _extract_tag_with_gemini(image, mime_type, month):
            return {
                "item_id": "",
                "barcode": "8850029850726",
                "product_name": "NIVEA SON DUONG AM DAU TAY DO 4.8G/CAY",
                "promo_text": "GIAM 25%",
                "normal_price": 77000,
                "promo_price": 57750,
                "date_text": "KM:01/09-30/09",
                "promo_from": "2026-09-01",
                "promo_to": "2026-09-30",
                "raw_text": "KM:01/09-30/09 *P03845* 8850029850726",
                "confidence": 0.93,
            }

        @staticmethod
        def compare_observation(rows, observed, manual_item_id=""):
            return tag_audit_contract.compare_observation(rows, observed, manual_item_id=manual_item_id)

    from backend.tag_audit_itemid_contract import install_tag_audit_itemid_contract

    install_tag_audit_itemid_contract(Facade)
    observed = Facade._extract_tag_with_gemini(b"image", "image/jpeg", "2026-09")

    assert observed["item_id"] == "P03845"
    assert observed["item_id_candidates"] == ["P03845"]
    result = Facade.compare_observation([_row()], observed)
    assert result["identity_source"] == "ocr_item_id"
    assert result["verdict"]["code"] == "correct"


def test_itemid_primary_contract_resolves_hamming_ocr_error_in_compare():
    class Facade:
        _itemid_primary_contract_v1 = False

        @staticmethod
        def _extract_tag_with_gemini(image, mime_type, month):
            return {
                "item_id": "P30768",  # OCR read 8 instead of 6
                "item_id_candidates": ["P30768"],
                "barcode": "",
                "product_name": "NIVEA SON DUONG AM DAU TAY DO 4.8G/CAY",
                "promo_text": "GIAM 25%",
                "normal_price": 77000,
                "promo_price": 57750,
                "date_text": "KM:01/09-30/09",
                "promo_from": "2026-09-01",
                "promo_to": "2026-09-30",
                "raw_text": "KM:01/09-30/09 P30768",
                "confidence": 0.90,
            }

        @staticmethod
        def compare_observation(rows, observed, manual_item_id=""):
            return tag_audit_contract.compare_observation(rows, observed, manual_item_id=manual_item_id)

    from backend.tag_audit_itemid_contract import install_tag_audit_itemid_contract

    install_tag_audit_itemid_contract(Facade)
    observed = Facade._extract_tag_with_gemini(b"image", "image/jpeg", "2026-09")

    # The active CTKM row contains P30766 with price 57750
    result = Facade.compare_observation([_row(item_id="P30766", promo_price=57750)], observed)
    assert result["verdict"]["code"] == "correct"
    assert observed["item_id"] == "P30766"
    assert observed["item_id_resolved_from_context"] == "P30768"


def test_itemid_primary_contract_never_guesses_between_multiple_p_numbers():
    class Facade:
        _itemid_primary_contract_v1 = False

        @staticmethod
        def _extract_tag_with_gemini(image, mime_type, month):
            return {
                "item_id": "P03845",
                "barcode": "",
                "product_name": "",
                "promo_text": "",
                "normal_price": None,
                "promo_price": None,
                "date_text": "",
                "promo_from": None,
                "promo_to": None,
                "raw_text": "P03845 P20383",
                "confidence": 0.4,
            }

        @staticmethod
        def compare_observation(rows, observed, manual_item_id=""):
            return tag_audit_contract.compare_observation(rows, observed, manual_item_id=manual_item_id)

    from backend.tag_audit_itemid_contract import install_tag_audit_itemid_contract

    install_tag_audit_itemid_contract(Facade)
    observed = Facade._extract_tag_with_gemini(b"image", "image/jpeg", "2026-09")
    assert observed["item_id"] == ""
    assert observed["item_id_candidates"] == ["P03845", "P20383"]

    result = Facade.compare_observation([_row(), _row("P20383")], observed)
    assert result["verdict"]["code"] == "review_itemid_ambiguous"
    assert result["identity_source"] == "ocr_item_id_ambiguous"
    assert result["expected"] is None


def test_is_complete_observation_fast_path():
    assert is_complete_observation({
        "item_id": "P30766",
        "item_id_candidates": ["P30766"],
        "promo_price": 57750,
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
    }) is True

    # Missing promo_price
    assert is_complete_observation({
        "item_id": "P30766",
        "item_id_candidates": ["P30766"],
        "promo_price": None,
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
    }) is False

    # Missing dates
    assert is_complete_observation({
        "item_id": "P30766",
        "item_id_candidates": ["P30766"],
        "promo_price": 57750,
        "promo_from": None,
        "promo_to": None,
    }) is False

    # Multiple ambiguous itemids
    assert is_complete_observation({
        "item_id": "",
        "item_id_candidates": ["P30766", "P20383"],
        "promo_price": 57750,
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
    }) is False
