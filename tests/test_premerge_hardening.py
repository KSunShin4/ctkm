from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import HTTPException

import main
from backend import main_api


def _sheet(*, empty: bool = False):
    frame = pd.DataFrame() if empty else pd.DataFrame({"Item": ["P1"]})
    return SimpleNamespace(df=frame, source_excel_rows=[2] if not empty else [])


def test_pog_multiple_nonempty_sheets_require_explicit_selection():
    workbook = SimpleNamespace(sheets={"POG A": _sheet(), "POG B": _sheet()})

    with pytest.raises(ValueError, match="nhieu sheet"):
        main._select_primary_pog_sheet(workbook)

    name, selected = main._select_primary_pog_sheet(workbook, "pog b")
    assert name == "POG B"
    assert selected is workbook.sheets["POG B"]


def test_pog_single_nonempty_sheet_is_selected_automatically():
    workbook = SimpleNamespace(sheets={"Notes": _sheet(empty=True), "POG": _sheet()})

    name, selected = main._select_primary_pog_sheet(workbook)

    assert name == "POG"
    assert selected is workbook.sheets["POG"]


@pytest.mark.parametrize("month", ["2026-00", "2026-13", "2026-1", "26-08", "not-a-month"])
def test_ctkm_request_rejects_invalid_month_before_queue(month):
    with pytest.raises(HTTPException) as exc_info:
        main_api._validate_ctkm_request_dates(month, None)

    assert exc_info.value.status_code == 422
    assert "YYYY-MM" in str(exc_info.value.detail)


@pytest.mark.parametrize("business_date", ["2026-02-30", "2026-2-03", "03/02/2026", "bad-date"])
def test_ctkm_request_rejects_invalid_business_date_before_queue(business_date):
    with pytest.raises(HTTPException) as exc_info:
        main_api._validate_ctkm_request_dates("2026-08", business_date)

    assert exc_info.value.status_code == 422
    assert "YYYY-MM-DD" in str(exc_info.value.detail)


def test_ctkm_request_accepts_valid_month_and_business_date():
    assert main_api._validate_ctkm_request_dates("2026-08", "2026-08-15") == "2026-08-15"
    assert main_api._validate_ctkm_request_dates("2026-08", "") is None


def test_preview_reads_only_requested_rows(monkeypatch, tmp_path):
    class FakeSheet:
        max_row = 100_001

        def iter_rows(self, *, min_row=None, max_row=None, values_only=False):
            assert min_row == 1
            assert max_row == 4  # header + three requested data rows
            assert values_only is True
            yield ("A", "B")
            yield (1, "one")
            yield (2, "two")
            yield (3, "three")

    class FakeWorkbook:
        sheetnames = ["Large"]

        def __init__(self):
            self.sheet = FakeSheet()
            self.closed = False

        def __getitem__(self, _name):
            return self.sheet

        def close(self):
            self.closed = True

    fake_workbook = FakeWorkbook()
    monkeypatch.setattr("openpyxl.load_workbook", lambda *_args, **_kwargs: fake_workbook)

    output = tmp_path / "result.xlsx"
    output.write_bytes(b"placeholder")
    job_id = "preview-hardening"
    main_api._jobs[job_id] = {
        "job_id": job_id,
        "month": "2026-08",
        "output_path": str(output),
        "output_name": output.name,
        "summary": {"ok": 1},
        "created_at": "2026-08-15T00:00:00",
    }
    try:
        result = main_api.preview_result(job_id, rows=3, _admin="test-admin")
    finally:
        main_api._jobs.pop(job_id, None)

    assert result["sheets"]["Large"]["rows"] == [
        ["1", "one"], ["2", "two"], ["3", "three"],
    ]
    assert result["sheets"]["Large"]["total_rows"] == 100_000
    assert fake_workbook.closed is True
