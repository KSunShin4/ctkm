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
        assert captured["ctkm_mapping_source"].startswith("standard-fact")
        assert captured["pog_mapping_source"].startswith("standard-pog")
        assert captured["clearance_mapping_source"].startswith("standard-fact")
    finally:
        main_api._jobs.pop(response["job_id"], None)


def test_mapping_confirmation_required_for_missing_required_target():
    schema = {
        "item_id": {"required": True},
        "promo_from": {"required": True},
        "optional": {"required": False},
    }
    assert main_api._mapping_needs_confirmation(
        {"mapping": {"A": "item_id"}, "confidence": {"A": 0.99}}, schema
    )


def test_mapping_confirmation_required_for_low_confidence_required_target():
    schema = {"item_id": {"required": True}}
    assert main_api._mapping_needs_confirmation(
        {"mapping": {"mystery": "item_id"}, "confidence": {"mystery": 0.60}}, schema
    )
    assert not main_api._mapping_needs_confirmation(
        {"mapping": {"mystery": "item_id"}, "confidence": {"mystery": 0.95}}, schema
    )


def test_confirm_mapping_requeues_same_job_and_saves_preset(monkeypatch, tmp_path):
    job_id = "resume01"
    resumed = {}
    stored = {}

    def work(job):
        resumed["job_id"] = job["job_id"]

    main_api._jobs[job_id] = {
        "job_id": job_id, "kind": "ctkm", "status": "awaiting_mapping_confirmation",
        "progress": 30, "message": "waiting", "summary": {}, "warnings": [], "error": None,
        "created_at": "2026-09-26T00:00:00", "month": "2026-09",
        "output_path": str(tmp_path / "out.xlsx"), "resume_work": work,
        "mapping_confirmation": {
            "ctkm_columns": ["sku", "campaign", "from", "to"],
            "pog_columns": ["sku", "store"],
        },
        "mapping_sources": {"ctkm": "gemini", "pog": "gemini"},
    }
    monkeypatch.setattr(main_api, "_store_preset", lambda *a, **kw: stored.update(kw))
    monkeypatch.setattr(main_api, "_submit_job", lambda jid, kind, fn: fn(main_api._jobs[jid]))

    response = asyncio.run(main_api.confirm_job_mapping(
        job_id=job_id,
        ctkm_mapping='{"sku":"item_id","campaign":"campaign_name","from":"promo_from","to":"promo_to"}',
        pog_mapping='{"sku":"item_id","store":"store_id"}',
        save_preset=True,
        _admin="test-admin",
    ))
    try:
        assert response["job_id"] == job_id
        assert resumed["job_id"] == job_id
        assert stored["ctkm_mapping"]["sku"] == "item_id"
        assert main_api._jobs[job_id]["confirmed_mappings"]["pog"]["store"] == "store_id"
        assert main_api._jobs[job_id]["mapping_sources"] == {
            "ctkm": "user-confirmed", "pog": "user-confirmed"
        }
    finally:
        main_api._jobs.pop(job_id, None)



def test_production_ctkm_route_pauses_for_low_confidence_mapping_then_resumes_same_job(monkeypatch, tmp_path):
    captured = {}

    class FakeUpload:
        def __init__(self, filename):
            self.filename = filename

    async def fake_read_upload(_upload, _max_bytes, _label):
        return b"validated-by-fixture"

    ctkm_frame = pd.DataFrame([{
        "sku": "P1001", "campaign": "Promo",
        "from": "2026-09-01", "to": "2026-09-30",
    }])
    pog_frame = pd.DataFrame([{"sku": "P1001", "store": "SGPMC0001"}])

    def fake_load(path, **_kwargs):
        if path.endswith("pog.xlsx"):
            return SimpleNamespace(
                sheets={"POG": SimpleNamespace(df=pog_frame)},
                pog_snapshot_month="2026-09",
            )
        return SimpleNamespace(
            sheets={"CTKM": SimpleNamespace(df=ctkm_frame)},
            pog_snapshot_month=None,
        )

    def fake_preview(sheet_name, df, _schema, logs):
        if sheet_name == "CTKM":
            mapping = {
                "sku": "item_id", "campaign": "campaign_name",
                "from": "promo_from", "to": "promo_to",
            }
        else:
            mapping = {"sku": "item_id", "store": "store_id"}
        logs.append({
            "sheet_name": sheet_name,
            "mapping": mapping,
            "confidence": {key: 0.60 for key in mapping},
            "unmapped": [],
            "low_confidence_fields": list(mapping),
            "source": "gemini",
        })
        return mapping, logs

    def fake_run_pipeline(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(summary={"ok": 1}, warnings=[])

    def run_immediately(job_id, _kind, work):
        job = main_api._jobs[job_id]
        try:
            summary, warnings = work(job)
            job.update(
                status="completed", summary=summary, warnings=warnings, progress=100,
            )
        except main_api.MappingConfirmationRequired:
            job.update(
                status="awaiting_mapping_confirmation",
                progress=30,
                message="Cần xác nhận mapping trước khi tiếp tục",
            )

    monkeypatch.setattr(main_api, "_TMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr(main_api, "_OUT_DIR", tmp_path / "out")
    main_api._TMP_DIR.mkdir()
    main_api._OUT_DIR.mkdir()
    monkeypatch.setattr(main_api, "_read_upload_limited", fake_read_upload)
    monkeypatch.setattr(main_api._main_mod.L, "load_workbook_raw", fake_load)
    monkeypatch.setattr(main_api._main_mod, "_infer_standard_fact_mapping", lambda _df: {})
    monkeypatch.setattr(main_api._main_mod, "_infer_standard_pog_mapping", lambda _df: {})
    monkeypatch.setattr(main_api._main_mod, "preview_mapping", fake_preview)
    monkeypatch.setattr(main_api, "_get_saved_preset", lambda *_args: {})
    monkeypatch.setattr(main_api, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(main_api, "_submit_job", run_immediately)
    monkeypatch.setattr(main_api, "_enforce_gemini_cooldown", lambda: None)

    accepted = asyncio.run(main_api.enqueue_ctkm(
        ctkm_file=FakeUpload("ctkm.xlsx"),
        pog_file=FakeUpload("pog.xlsx"),
        clearance_file=None,
        month="2026-09",
        strict_month=False,
        ctkm_sheet_name="CTKM",
        clearance_sheet_name=None,
        pog_sheet_name="POG",
        ctkm_mapping_override=None,
        pog_mapping_override=None,
        selected_output_columns=None,
        business_date="2026-09-15",
        mapping_mode="auto",
        _admin="test-admin",
    ))
    job_id = accepted["job_id"]

    try:
        assert accepted["status"] == "awaiting_mapping_confirmation"
        assert accepted["mapping_confirmation"]["ctkm"]["source"] == "gemini"
        assert main_api._jobs[job_id]["resume_work"]

        resumed = asyncio.run(main_api.confirm_job_mapping(
            job_id=job_id,
            ctkm_mapping='{"sku":"item_id","campaign":"campaign_name","from":"promo_from","to":"promo_to"}',
            pog_mapping='{"sku":"item_id","store":"store_id"}',
            save_preset=False,
            _admin="test-admin",
        ))

        assert resumed["job_id"] == job_id
        assert main_api._jobs[job_id]["status"] == "completed"
        assert captured["ctkm_mapping_source"] == "user-confirmed"
        assert captured["pog_mapping_source"] == "user-confirmed"
        assert captured["ctkm_mapping_override"]["sku"] == "item_id"
        assert captured["pog_mapping_override"]["store"] == "store_id"
    finally:
        main_api._jobs.pop(job_id, None)


def test_queued_job_mapping_confirmation_is_not_marked_failed(monkeypatch, tmp_path):
    job_id = "pause01"
    main_api._jobs[job_id] = {
        "job_id": job_id,
        "kind": "ctkm",
        "status": "queued",
        "output_path": str(tmp_path / "out.xlsx"),
        "created_at": "2026-09-27T00:00:00",
    }
    queue = SimpleNamespace(
        acquire=lambda *_args: None,
        release=lambda *_args: None,
    )
    monkeypatch.setattr(main_api, "_heavy_queue", queue)

    def pause(_job):
        raise main_api.MappingConfirmationRequired()

    try:
        main_api._run_queued_job(job_id, "ctkm", pause)
        assert main_api._jobs[job_id]["status"] == "awaiting_mapping_confirmation"
        assert main_api._jobs[job_id]["error"] is None
    finally:
        main_api._jobs.pop(job_id, None)
