from io import BytesIO

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from backend import main_api  # installs production scanner layers
from backend import tag_audit_business_date_contract as business_date
from backend import tag_audit_contract


HEADERS = [
    "Phạm vi áp dụng (KEY Channel)", "Kênh chương trình (Channel)",
    "Mã sản phẩm", "Tên sản phẩm", "Đơn vị sản phẩm (Promo UoM)",
    "POG", "Vị trí", "Facing", "Công việc", "Ngày gắn", "Ngày tháo",
    "Campaign", "Scheme detail", "From", "To", "Giá thường", "Giá KM",
    "Nguồn", "Lý do / Cảnh báo", "Product type", "Cửa hàng",
]


def _workbook_bytes(*, report_date="2026-09-05", include_guide=True):
    workbook = Workbook()
    workbook.remove(workbook.active)
    if include_guide:
        guide = workbook.create_sheet("HƯỚNG DẪN")
        guide.append(["DANH SÁCH THAO TÁC TEM KHUYẾN MÃI"])
        guide.append(["Tháng báo cáo", "2026-09"])
        guide.append(["Ngày nghiệp vụ", report_date])
    for name in ("Gắn tem", "Tháo tem", "Chờ gắn"):
        ws = workbook.create_sheet(name)
        ws.append(HEADERS)
    workbook["Gắn tem"].append([
        "All channel", "ALL CHANNEL", "P30766", "Sản phẩm thử nghiệm", "Hộp",
        "POG-A", "1", 1, "gắn tem", "2026-09-01", "2026-10-01",
        "FULL MONTH", "GIẢM 25%", "2026-09-01", "2026-09-30",
        225000, 168750, "CTKM", "", "NORMAL", "S1",
    ])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _observed():
    return {
        "item_id": "P30766",
        "item_id_candidates": ["P30766"],
        "barcode": "",
        "product_name": "SAN PHAM THU NGHIEM",
        "promo_text": "GIAM 25%",
        "normal_price": 225000,
        "promo_price": 168750,
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "raw_text": "P30766",
        "confidence": 0.95,
    }


def test_production_installs_business_date_contract():
    assert tag_audit_contract._business_date_contract_v1 is True


def test_parser_preserves_exported_report_business_date_as_technical_metadata():
    rows = tag_audit_contract._parse_action_workbook(BytesIO(_workbook_bytes()))

    assert len(rows) == 1
    assert rows[0]["_report_business_date"] == "2026-09-05"
    assert rows[0]["_report_month"] == "2026-09"
    assert rows[0]["item_id"] == "P30766"
    assert rows[0]["channel"] == "ALL CHANNEL"


def test_context_explicitly_marks_known_stale_business_date(monkeypatch):
    monkeypatch.setattr(business_date, "current_vn_business_date", lambda: "2026-09-06")
    rows = tag_audit_contract._parse_action_workbook(BytesIO(_workbook_bytes()))

    payload = tag_audit_contract._context_payload({
        "source": "uploaded-workbook",
        "job_id": None,
        "month": None,
        "rows": rows,
    })

    assert payload["business_date"] == "2026-09-05"
    assert payload["scanner_business_date"] == "2026-09-06"
    assert payload["business_date_stale"] is True
    assert payload["report_month"] == "2026-09"


def test_stale_business_date_blocks_verdict_and_progress(monkeypatch):
    monkeypatch.setattr(business_date, "current_vn_business_date", lambda: "2026-09-06")
    rows = tag_audit_contract._parse_action_workbook(BytesIO(_workbook_bytes()))

    with pytest.raises(HTTPException) as exc_info:
        tag_audit_contract.compare_observation(rows, _observed())

    assert exc_info.value.status_code == 409
    assert "2026-09-05" in str(exc_info.value.detail)
    assert "2026-09-06" in str(exc_info.value.detail)


def test_current_business_date_keeps_existing_deterministic_verdict(monkeypatch):
    monkeypatch.setattr(business_date, "current_vn_business_date", lambda: "2026-09-05")
    rows = tag_audit_contract._parse_action_workbook(BytesIO(_workbook_bytes()))

    result = tag_audit_contract.compare_observation(rows, _observed())

    assert result["verdict"]["code"] == "correct"
    assert result["progress_eligible"] is True
    assert result["progress_state"] == "pass"


def test_legacy_workbook_without_business_date_remains_backward_compatible(monkeypatch):
    monkeypatch.setattr(business_date, "current_vn_business_date", lambda: "2026-09-06")
    rows = tag_audit_contract._parse_action_workbook(
        BytesIO(_workbook_bytes(include_guide=False))
    )

    payload = tag_audit_contract._context_payload({
        "source": "uploaded-workbook",
        "job_id": None,
        "month": None,
        "rows": rows,
    })
    result = tag_audit_contract.compare_observation(rows, _observed())

    assert payload["business_date"] is None
    assert payload["business_date_stale"] is False
    assert result["verdict"]["code"] == "correct"
