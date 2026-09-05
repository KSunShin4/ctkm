from backend.tag_audit_itemid_contract import extract_itemid_candidates
from backend import tag_audit_contract


def _row(item_id="P03845"):
    return {
        "item_id": item_id,
        "item_name": "NIVEA SON DUONG AM DAU TAY DO 4.8G/CAY",
        "campaign_name": "GIAM 25%",
        "campaign_detail": "",
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "normal_price": 77000,
        "promo_price": 57750,
        "expected_action": "gan_tem",
        "source_sheet": "Gắn tem",
        "key_channel": "Offline",
        "channel": "OFFLINE",
    }


def test_extract_itemid_candidates_prefers_printed_p_number():
    assert extract_itemid_candidates("*P03845*", "8850029850726") == ["P03845"]


def test_extract_itemid_candidates_accepts_common_ocr_spacing_noise():
    assert extract_itemid_candidates("Mã: P 03845", "P-20383") == ["P03845", "P20383"]


def test_itemid_primary_contract_recovers_id_from_raw_text(monkeypatch):
    # Reinstall on an isolated lightweight facade so this test does not mutate the
    # globally installed production module for later tests.
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
