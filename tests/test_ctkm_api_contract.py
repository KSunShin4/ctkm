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

        async def read(self, _limit):
            return b"xlsx-placeholder"

    def fake_workbook(sheet_name):
        sheet = SimpleNamespace(df=pd.DataFrame(columns=["Item", "Campaign"]))
        return SimpleNamespace(sheets={sheet_name: sheet})

    def fake_load(path, **_kwargs):
        return fake_workbook("POG" if path.endswith("pog.xlsx") else "CTKM")

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
    monkeypatch.setattr(main_api._main_mod.L, "load_workbook_raw", fake_load)
    monkeypatch.setattr(
        main_api._main_mod, "_select_primary_ctkm_sheet",
        lambda workbook, _selected: ("CTKM", workbook.sheets["CTKM"]),
    )
    monkeypatch.setattr(
        main_api, "_get_saved_preset",
        lambda *_args: {"ctkm_mapping": {"Item": "item_id"}, "pog_mapping": {"Item": "item_id"}},
    )
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
    finally:
        main_api._jobs.pop(response["job_id"], None)
