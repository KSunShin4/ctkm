import threading
from types import SimpleNamespace

from backend import main_api  # installs production scanner layers
from backend import tag_audit_contract
from backend import tag_audit_local_ocr_contract as local_ocr
from backend.tag_audit_temporal_hint_contract import (
    infer_unique_promotion_year,
    install_tag_audit_temporal_hint_contract,
)


def _row(start="2026-09-01", end="2026-09-30"):
    return {"promo_from": start, "promo_to": end}


def test_production_installs_temporal_hint_contract_and_accepts_year_only_hint():
    assert tag_audit_contract._temporal_hint_contract_v1 is True
    assert local_ocr._year("2026") == 2026
    assert local_ocr._year("2026-09") == 2026


def test_unique_year_is_derived_from_workbook_dates_without_inventing_month():
    rows = [_row(), _row("2026-10-01", "2026-10-31")]

    assert infer_unique_promotion_year(tag_audit_contract, rows) == "2026"


def test_mixed_year_workbook_does_not_get_an_ocr_year_hint():
    rows = [_row(), _row("2027-01-01", "2027-01-31")]

    assert infer_unique_promotion_year(tag_audit_contract, rows) is None


def test_context_payload_exposes_year_hint_but_keeps_month_semantics_unchanged():
    payload = tag_audit_contract._context_payload({
        "source": "uploaded-workbook",
        "job_id": None,
        "month": None,
        "rows": [_row()],
    })

    assert payload["month"] is None
    assert payload["ocr_year_hint"] == "2026"


def test_extractor_uses_unique_cached_year_only_when_month_is_missing():
    received = []

    class FakeTagAudit:
        _temporal_hint_contract_v1 = False
        _CONTEXT_LOCK = threading.RLock()
        _CONTEXT_CACHE = {"rows": [_row()]}

        @staticmethod
        def _parse_iso_date(value):
            text = str(value or "")
            return text if len(text) >= 10 and text[4] == "-" and text[7] == "-" else None

        @staticmethod
        def _context_payload(cache):
            return {"month": cache.get("month")}

        @staticmethod
        def _extract_tag_with_gemini(image, mime_type, month):
            received.append(month)
            return {"month_seen": month}

    fake_local = SimpleNamespace(_year=lambda value: 2099)
    install_tag_audit_temporal_hint_contract(FakeTagAudit, fake_local)

    inferred = FakeTagAudit._extract_tag_with_gemini(b"image", "image/jpeg", None)
    explicit = FakeTagAudit._extract_tag_with_gemini(b"image", "image/jpeg", "2025-12")

    assert inferred["month_seen"] == "2026"
    assert explicit["month_seen"] == "2025-12"
    assert received == ["2026", "2025-12"]
    assert fake_local._year("2026") == 2026
    assert fake_local._year("anything-else") == 2099


def test_extractor_does_not_guess_when_cached_workbook_spans_multiple_years():
    received = []

    class FakeTagAudit:
        _temporal_hint_contract_v1 = False
        _CONTEXT_LOCK = threading.RLock()
        _CONTEXT_CACHE = {"rows": [_row(), _row("2027-01-01", "2027-01-31")]}

        @staticmethod
        def _parse_iso_date(value):
            text = str(value or "")
            return text if len(text) >= 10 and text[4] == "-" and text[7] == "-" else None

        @staticmethod
        def _context_payload(cache):
            return {}

        @staticmethod
        def _extract_tag_with_gemini(image, mime_type, month):
            received.append(month)
            return {}

    fake_local = SimpleNamespace(_year=lambda value: 2099)
    install_tag_audit_temporal_hint_contract(FakeTagAudit, fake_local)
    FakeTagAudit._extract_tag_with_gemini(b"image", "image/jpeg", None)

    assert received == [None]
