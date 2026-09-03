import asyncio
from types import SimpleNamespace

import pandas as pd

from backend import main_api


def test_legacy_run_delegates_business_date_and_clearance_to_ctkm_queue(monkeypatch):
    captured = {}

    async def fake_enqueue_ctkm(**kwargs):
        captured.update(kwargs)
        return {"job_id": "queued"}

    monkeypatch.setattr(main_api, "enqueue_ctkm", fake_enqueue_ctkm)
    ctkm_file, pog_file, clearance_file = object(), object(), object()

    result = asyncio.run(main_api.run_job(
        ctkm_file=ctkm_file,
        pog_file=pog_file,
        clearance_file=clearance_file,
        month="2026-08",
        strict_month=False,
        ctkm_sheet_name="CTKM",
        clearance_sheet_name="CLEARANCE",
        pog_sheet_name="POG",
        ctkm_mapping_override=None,
        pog_mapping_override=None,
        selected_output_columns=None,
        business_date="2026-08-15",
        mapping_mode="saved_only",
        _admin="test-admin",
    ))

    assert result == {"job_id": "queued"}
    assert captured["clearance_file"] is clearance_file
    assert captured["clearance_sheet_name"] == "CLEARANCE"
    assert captured["business_date"] == "2026-08-15"
    assert captured["ctkm_file"] is ctkm_file
    assert captured["pog_file"] is pog_file


def test_canonical_ctkm_queue_passes_business_date_and_clearance_to_pipeline(monkeypatch, tmp_path):
    captured = {}

    class FakeUpload:
        def __init__(self, filename):
            self.filename = filename

    async def fake_read_upload(_upload, _max_bytes, _label):
        # This test covers queue/preflight propagation, not XLSX container parsing.
        return b"validated-by-fixture"

    def fact_frame(*, clearance=False):
        if clearance:
            return pd.DataFrame([{
                "Item code": "P2001",
                "Product Name": "Clearance item",
                "From": "2026-08-01",
                "To": "2026-08-31",
                "Campaign Detail": "Clearance Isstop 1-3-4",
                "Scheme detail for customer": "Clearance",
                "Kênh áp dụng": "All channel",
            }])
        return pd.DataFrame([{
            "Item code 2": "P1001",
            "Product Name": "Monthly item",
            "From": "2026-08-01",
            "To": "2026-08-31",
            "Campaign": "Monthly",
            "KEY Channel": "Offline",
            "Channel": "OFFLINE",
        }])

    def pog_frame():
        return pd.DataFrame([{
            "ITEMID": "P1001",
            "STOREID": "SGPMC0001",
            "POGCODE": "POG.0001",
            "LOCATIONID": 1,
        }])

    def fake_load(path, **_kwargs):
        if path.endswith("pog.xlsx"):
            return SimpleNamespace(
                sheets={"POG": SimpleNamespace(df=pog_frame())},
                pog_snapshot_month="2026-08",
            )
        if path.endswith("clearance.xlsx"):
            return SimpleNamespace(
                sheets={"CLEARANCE": SimpleNamespace(df=fact_frame(clearance=True))},
                pog_snapshot_month=None,
            )
        return SimpleNamespace(
            sheets={"CTKM": SimpleNamespace(df=fact_frame())},
            pog_snapshot_month=None,
        )

    def fake_run_pipeline(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(summary={"ok": 1}, warnings=[])

    def run_immediately(job_id, _kind, work):
        summary, warnings = work(main_api._jobs[job_id])
        main_api._jobs[job_id].update(
            status="completed", summary=summary, warnings=warnings, progress=100,
        )

    monkeypatch.setattr(main_api, "_TMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr(main_api, "_OUT_DIR", tmp_path / "out")
    main_api._TMP_DIR.mkdir()
    main_api._OUT_DIR.mkdir()
    monkeypatch.setattr(main_api, "_read_upload_limited", fake_read_upload)
    monkeypatch.setattr(main_api._main_mod.L, "load_workbook_raw", fake_load)
    monkeypatch.setattr(main_api, "_get_saved_preset", lambda *_args: {})
    monkeypatch.setattr(main_api, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(main_api, "_submit_job", run_immediately)

    response = asyncio.run(main_api.enqueue_ctkm(
        ctkm_file=FakeUpload("ctkm.xlsx"),
        pog_file=FakeUpload("pog.xlsx"),
        clearance_file=FakeUpload("clearance.xlsx"),
        month="2026-08",
        strict_month=False,
        ctkm_sheet_name="CTKM",
        clearance_sheet_name="CLEARANCE",
        pog_sheet_name="POG",
        ctkm_mapping_override=None,
        pog_mapping_override=None,
        selected_output_columns=None,
        business_date="2026-08-15",
        mapping_mode="saved_only",
        _admin="test-admin",
    ))

    try:
        assert response["status"] == "completed"
        assert captured["business_date"] == "2026-08-15"
        assert captured["clearance_sheet_name"] == "CLEARANCE"
        assert captured["clearance_filepath"].endswith("clearance.xlsx")
        assert captured["ctkm_mapping_override"]["Item code 2"] == "item_id"
        assert captured["pog_mapping_override"]["ITEMID"] == "item_id"
        assert captured["clearance_mapping_override"]["Item code"] == "item_id"
    finally:
        main_api._jobs.pop(response["job_id"], None)
