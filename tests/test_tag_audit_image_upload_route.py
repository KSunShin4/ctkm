import asyncio
from io import BytesIO

from fastapi import UploadFile
from starlette.datastructures import Headers

from backend import main_api
from backend import tag_audit_contract


def _row():
    return {
        "item_id": "P30766",
        "item_name": "Sản phẩm thử nghiệm",
        "key_channel": "All channel",
        "channel": "ALL CHANNEL",
        "campaign_name": "FULL MONTH",
        "campaign_detail": "GIẢM 25%",
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "normal_price": 225000,
        "promo_price": 168750,
        "expected_action": "gan_tem",
        "source_sheet": "Gắn tem",
    }


def _observed():
    return {
        "item_id": "P30766",
        "item_id_candidates": ["P30766"],
        "barcode": "",
        "product_name": "Sản phẩm thử nghiệm",
        "promo_text": "GIẢM 25%",
        "normal_price": 225000,
        "promo_price": 168750,
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "raw_text": "P30766 168750 01/09-30/09",
        "confidence": 0.99,
    }


def test_tag_check_accepts_jpeg_bytes_without_xlsx_validation(monkeypatch):
    """Regression: scanner images must never enter the OOXML/ZIP validator."""
    monkeypatch.setattr(tag_audit_contract, "_CONTEXT_CACHE", {
        "source_key": "test:image-upload",
        "source": "uploaded-workbook",
        "job_id": None,
        "month": "2026-09",
        "rows": [_row()],
    })
    monkeypatch.setattr(
        tag_audit_contract,
        "_extract_tag_with_gemini",
        lambda image, mime_type, month: _observed(),
    )

    upload = UploadFile(
        filename="shelf-tag.jpg",
        file=BytesIO(b"not-a-real-jpeg-but-valid-route-test-bytes"),
        headers=Headers({"content-type": "image/jpeg"}),
    )

    result = asyncio.run(main_api.check_tag(
        image=upload,
        manual_item_id="",
        barcode_hint="",
        manual_promo_price="",
        manual_normal_price="",
        manual_promo_from="",
        manual_promo_to="",
        manual_promo_text="",
        _admin="admin",
    ))

    assert result["verdict"]["code"] == "correct"
    assert result["observed"]["item_id"] == "P30766"
