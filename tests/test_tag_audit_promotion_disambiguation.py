from backend import main_api  # installs the production scanner layers
from backend import tag_audit_contract


def _row(normal_price):
    return {
        "item_id": "P30766",
        "item_name": "Sản phẩm thử nghiệm",
        "campaign_name": "FULL MONTH",
        "campaign_detail": "GIẢM 25%",
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "normal_price": normal_price,
        "promo_price": 168750,
        "expected_action": "gan_tem",
        "source_sheet": "Gắn tem",
        "key_channel": "All channel",
        "channel": "ALL CHANNEL",
    }


def _observed(normal_price):
    return {
        "item_id": "P30766",
        "item_id_candidates": ["P30766"],
        "barcode": "",
        "product_name": "SAN PHAM THU NGHIEM",
        "promo_text": "GIAM 25%",
        "normal_price": normal_price,
        "promo_price": 168750,
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "raw_text": "P30766",
        "confidence": 0.95,
    }


def test_production_installs_normal_price_disambiguation_contract():
    assert tag_audit_contract._promotion_disambiguation_contract_v1 is True


def test_printed_normal_price_selects_matching_promotion_independent_of_row_order():
    low = _row(225000)
    high = _row(230000)

    first = tag_audit_contract.compare_observation([low, high], _observed(230000))
    second = tag_audit_contract.compare_observation([high, low], _observed(230000))

    for result in (first, second):
        assert result["verdict"]["code"] == "correct"
        assert result["expected"]["normal_price"] == 230000
        assert result["progress_eligible"] is True


def test_missing_normal_price_keeps_otherwise_identical_promotions_in_review():
    rows = [_row(225000), _row(230000)]

    first = tag_audit_contract.compare_observation(rows, _observed(None))
    second = tag_audit_contract.compare_observation(list(reversed(rows)), _observed(None))

    for result in (first, second):
        assert result["verdict"]["code"] == "review_ambiguous"
        assert result["progress_eligible"] is False
        assert result["check_key"] is None


def test_unique_promotion_still_reports_wrong_normal_price_as_failure():
    result = tag_audit_contract.compare_observation([_row(225000)], _observed(230000))

    assert result["verdict"]["code"] == "wrong_fields"
    assert result["mismatches"] == ["normal_price"]
    assert result["progress_eligible"] is True
    assert result["progress_state"] == "fail"
