import asyncio

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from backend import main_api


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


def test_ctkm_queue_requires_explicit_pog_sheet_before_reading_uploads():
    class FakeUpload:
        def __init__(self, filename):
            self.filename = filename

        async def read(self, _limit):
            raise AssertionError("request should be rejected before reading uploads")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(main_api.enqueue_ctkm(
            ctkm_file=FakeUpload("ctkm.xlsx"),
            pog_file=FakeUpload("pog.xlsx"),
            clearance_file=None,
            month="2026-08",
            strict_month=False,
            ctkm_sheet_name="CTKM",
            clearance_sheet_name=None,
            pog_sheet_name=None,
            ctkm_mapping_override=None,
            pog_mapping_override=None,
            selected_output_columns=None,
            business_date=None,
            mapping_mode="saved_only",
            _admin="test-admin",
        ))

    assert exc_info.value.status_code == 422
    assert "sheet POG" in str(exc_info.value.detail)


def test_inspect_pog_multiple_sheets_does_not_load_full_workbook_before_selection(monkeypatch, tmp_path):
    class FakeUpload:
        filename = "POG.XLSX"

    async def validated_upload(_upload, _max_bytes, _label):
        # Container validation is covered separately; this test isolates sheet-selection behavior.
        return b"validated-xlsx-fixture"

    monkeypatch.setattr(main_api, "_TMP_DIR", tmp_path)
    monkeypatch.setattr(main_api, "_read_upload_limited", validated_upload)
    monkeypatch.setattr(
        main_api._main_mod.L,
        "inspect_workbook_sheets",
        lambda _path: ["POG A", "POG B"],
    )

    def should_not_load(*_args, **_kwargs):
        raise AssertionError("full POG workbook must not load before sheet selection")

    monkeypatch.setattr(main_api._main_mod.L, "load_workbook_raw", should_not_load)

    result = asyncio.run(main_api.inspect_pog_file(
        pog_file=FakeUpload(),
        pog_sheet_name=None,
        _admin="test-admin",
    ))

    assert result["suggested_sheet"] is None
    assert result["requires_sheet_selection"] is True
    assert result["snapshot_month"] is None
    assert result["sheet_names"] == ["POG A", "POG B"]


def test_preview_counts_visible_rows_and_limits_only_returned_rows(tmp_path):
    output = tmp_path / "result.xlsx"
    workbook = Workbook()
    ws = workbook.active
    ws.title = "Large"
    ws.append(["A", "B"])
    for number in range(1, 6):
        ws.append([number, f"row-{number}"])
    # Hide the second data row. It must not count toward the preview badge.
    ws.row_dimensions[3].hidden = True
    workbook.save(output)

    job_id = "preview-hardening"
    main_api._jobs[job_id] = {
        "job_id": job_id,
        "kind": "ctkm",
        "status": "completed",
        "progress": 100,
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
        ["1", "row-1"], ["3", "row-3"], ["4", "row-4"],
    ]
    assert result["sheets"]["Large"]["total_rows"] == 4
    assert result["sheets"]["Large"]["sheet_kind"] == "data"
