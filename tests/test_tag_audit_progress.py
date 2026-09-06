from backend import main_api  # installs production scanner/progress contracts
from backend import tag_audit_contract
from backend.tag_audit_progress_contract import checklist_rows, context_id


def _row(**overrides):
    row = {
        "item_id": "P03845",
        "item_name": "NIVEA",
        "key_channel": "All channel",
        "channel": "Offline",
        "campaign_name": "FULL MONTH",
        "campaign_detail": "GIẢM 25%",
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "normal_price": 77000,
        "promo_price": 57750,
        "expected_action": "gan_tem",
        "source_sheet": "Gắn tem",
        "pog_code": "A",
        "location_id": "1",
        "facing": 1,
    }
    row.update(overrides)
    return row


def _observed(**overrides):
    value = {
        "item_id": "P03845",
        "barcode": "8850029850726",
        "product_name": "NIVEA",
        "promo_text": "GIAM 25%",
        "normal_price": 77000,
        "promo_price": 57750,
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "raw_text": "*P03845*",
        "confidence": 0.95,
    }
    value.update(overrides)
    return value


def test_checklist_counts_only_tags_expected_to_be_present():
    items = checklist_rows(tag_audit_contract, [
        _row(),
        _row(item_id="P2", expected_action="thao_tem", source_sheet="Tháo tem"),
        _row(item_id="P3", expected_action="cho_gan", source_sheet="Chờ gắn"),
    ])

    assert [item["item_id"] for item in items] == ["P03845"]
    assert items[0]["expected_action"] == "gan_tem"


def test_same_promotion_is_not_counted_twice_for_pog_position_variants():
    first = _row(pog_code="A", location_id="1", facing=1)
    second = _row(pog_code="B", location_id="9", facing=3)

    items = checklist_rows(tag_audit_contract, [first, second])

    assert len(items) == 1
    assert items[0]["item_id"] == "P03845"


def test_context_id_is_stable_under_input_reordering():
    rows = [_row(), _row(item_id="P20383", promo_price=175500)]

    assert context_id(tag_audit_contract, rows) == context_id(tag_audit_contract, list(reversed(rows)))


def test_direct_itemid_success_is_progress_eligible():
    result = tag_audit_contract.compare_observation([_row()], _observed())

    assert result["verdict"]["code"] == "correct"
    assert result["progress_eligible"] is True
    assert result["progress_state"] == "pass"
    assert result["check_key"].startswith("tag_")


def test_direct_itemid_wrong_price_still_counts_as_checked_but_failed():
    result = tag_audit_contract.compare_observation([_row()], _observed(promo_price=60000))

    assert result["verdict"]["code"] == "wrong_price"
    assert result["progress_eligible"] is True
    assert result["progress_state"] == "fail"


def test_name_only_candidate_does_not_advance_progress():
    result = tag_audit_contract.compare_observation(
        [_row()],
        _observed(item_id="", product_name="NIVEA"),
    )

    assert result["identity_source"] == "name_candidate"
    assert result["progress_eligible"] is False
    assert result["check_key"] is None


def test_remove_or_wait_tag_never_advances_required_tag_progress():
    remove = tag_audit_contract.compare_observation(
        [_row(expected_action="thao_tem", source_sheet="Tháo tem")],
        _observed(),
    )
    wait = tag_audit_contract.compare_observation(
        [_row(expected_action="cho_gan", source_sheet="Chờ gắn")],
        _observed(),
    )

    assert remove["verdict"]["code"] == "remove_tag"
    assert wait["verdict"]["code"] == "early_tag"
    assert remove["progress_eligible"] is False
    assert wait["progress_eligible"] is False


def test_context_payload_exposes_progress_scope_and_checklist_count():
    payload = tag_audit_contract._context_payload({
        "source": "uploaded-workbook",
        "job_id": None,
        "month": "2026-09",
        "rows": [_row(), _row(item_id="P2", expected_action="thao_tem")],
    })

    assert payload["checklist_count"] == 1
    assert payload["progress_scope"] == "gan_tem_only"
    assert payload["context_id"].startswith("ctx_")
