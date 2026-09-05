from io import BytesIO

from openpyxl import Workbook

from backend.tag_audit_contract import _parse_action_workbook, compare_observation


def _row(**overrides):
    row = {
        "item_id": "P30766",
        "item_name": "Sản phẩm thử nghiệm",
        "campaign_name": "FULL MONTH",
        "campaign_detail": "GIẢM 25%",
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "normal_price": 225000,
        "promo_price": 168750,
        "expected_action": "gan_tem",
        "source_sheet": "Gắn tem",
        "key_channel": "All channel",
        "channel": "ALL CHANNEL",
    }
    row.update(overrides)
    return row


def _observed(**overrides):
    data = {
        "item_id": "P30766",
        "barcode": "8936071090607",
        "product_name": "SAN PHAM THU NGHIEM",
        "promo_text": "GIAM 25%",
        "normal_price": 225000,
        "promo_price": 168750,
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "raw_text": "",
        "confidence": 0.95,
    }
    data.update(overrides)
    return data


def test_matching_attach_tag_is_correct():
    result = compare_observation([_row()], _observed())
    assert result["verdict"]["code"] == "correct"
    assert result["expected"]["item_id"] == "P30766"
    assert result["mismatches"] == []


def test_wrong_price_is_error_even_when_barcode_and_dates_match():
    result = compare_observation([_row()], _observed(promo_price=180000))
    assert result["verdict"]["code"] == "wrong_price"
    assert "promo_price" in result["mismatches"]


def test_remove_action_wins_before_field_matching():
    result = compare_observation(
        [_row(expected_action="thao_tem", source_sheet="Tháo tem")],
        _observed(),
    )
    assert result["verdict"]["code"] == "remove_tag"
    assert result["verdict"]["severity"] == "error"


def test_wait_action_reports_early_physical_tag():
    result = compare_observation(
        [_row(expected_action="cho_gan", source_sheet="Chờ gắn")],
        _observed(),
    )
    assert result["verdict"]["code"] == "early_tag"


def test_barcode_never_becomes_item_identity():
    observed = _observed(item_id="", product_name="", barcode="8936071090607")
    result = compare_observation([_row()], observed)
    assert result["verdict"]["code"] == "review_identity"
    assert result["identity_source"] == "none"
    assert result["expected"] is None


def test_name_only_match_is_review_not_final_verdict():
    observed = _observed(item_id="", product_name="Sản phẩm thử nghiệm")
    result = compare_observation([_row()], observed)
    assert result["verdict"]["code"] == "review_identity"
    assert result["identity_source"] == "name_candidate"
    assert result["expected"]["item_id"] == "P30766"


def test_manual_item_id_can_confirm_identity_when_ocr_misses_code():
    observed = _observed(item_id="")
    result = compare_observation([_row()], observed, manual_item_id=" p30766 ")
    assert result["verdict"]["code"] == "correct"
    assert result["identity_source"] == "manual_item_id"


def test_production_slim_workbook_is_valid_tag_context():
    workbook = Workbook()
    workbook.remove(workbook.active)
    headers = [
        "KEY Channel", "Channel", "Mã sản phẩm", "Tên sản phẩm",
        "Đơn vị sản phẩm (Promo UoM)", "POG", "Vị trí", "Facing",
        "Công việc", "Ngày gắn", "Ngày tháo", "Campaign", "Scheme detail",
        "From", "To", "Giá thường", "Giá KM", "Nguồn", "Lý do / Cảnh báo",
        "Product type", "Cửa hàng",
    ]
    for name in ("Gắn tem", "Tháo tem", "Chờ gắn"):
        ws = workbook.create_sheet(name)
        ws.append(headers)
    workbook["Gắn tem"].append([
        "All channel", "ALL CHANNEL", "P30766", "Sản phẩm thử nghiệm", "Hộp",
        "POG-A", "1", 1, "Gắn tem", "2026-09-01", "2026-10-01",
        "FULL MONTH", "GIẢM 25%", "2026-09-01", "2026-09-30",
        225000, 168750, "CTKM", "", "NORMAL", "S1",
    ])
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    rows = _parse_action_workbook(buffer)
    assert len(rows) == 1
    assert rows[0]["item_id"] == "P30766"
    assert rows[0]["expected_action"] == "gan_tem"
    assert rows[0]["promo_price"] == 168750
