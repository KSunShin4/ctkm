from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
import os

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from backend.runtime_contract import ReservedHeavyJobQueue, install_runtime_contract


class _OldQueue:
    def __init__(self, capacity=2):
        self.capacity = capacity

    def snapshot(self):
        return {"capacity": self.capacity, "active": None, "waiting": []}


def _fake_core(tmp_path, capacity=2):
    app = FastAPI()

    @app.get("/api/download/{job_id}")
    def old_download(job_id: str):
        return {"old": job_id}

    @app.get("/api/jobs")
    def old_jobs():
        return []

    root_tmp = tmp_path / "tmp"
    root_out = tmp_path / "out"
    root_tmp.mkdir()
    root_out.mkdir()
    return SimpleNamespace(
        app=app,
        _heavy_queue=_OldQueue(capacity),
        _jobs={},
        _TMP_DIR=root_tmp,
        _OUT_DIR=root_out,
        _JOB_TTL_SECONDS=60,
        HTTPException=HTTPException,
        FileResponse=FileResponse,
    )


def _job(core, job_id, *, status="queued", age_seconds=0):
    output = core._OUT_DIR / f"{job_id}.xlsx"
    created = datetime.now() - timedelta(seconds=age_seconds)
    data = {
        "job_id": job_id,
        "kind": "ctkm",
        "status": status,
        "progress": 0,
        "message": "",
        "output_path": str(output),
        "output_name": output.name,
        "summary": {},
        "warnings": [],
        "error": None,
        "created_at": created.isoformat(),
        "created_timestamp": created.timestamp(),
        "month": "2026-09",
    }
    core._jobs[job_id] = data
    return data


def test_queue_reserves_capacity_before_worker_thread_starts():
    queue = ReservedHeavyJobQueue(2)
    queue.reserve("a", "ctkm")
    queue.reserve("b", "tem_r")

    snapshot = queue.snapshot()
    assert [item["job_id"] for item in snapshot["waiting"]] == ["a", "b"]
    assert [item["position"] for item in snapshot["waiting"]] == [1, 2]

    with pytest.raises(RuntimeError, match="Hàng đợi đang đầy"):
        queue.reserve("c", "ctkm")


def test_failed_job_deletes_partial_output_and_temp_inputs(tmp_path):
    core = _fake_core(tmp_path, capacity=1)
    install_runtime_contract(core)
    job = _job(core, "deadbeef")
    job_dir = core._TMP_DIR / "deadbeef"
    job_dir.mkdir()
    (job_dir / "ctkm.xlsx").write_bytes(b"input")

    def work(_current):
        Path(job["output_path"]).write_bytes(b"partial workbook")
        raise RuntimeError("boom")

    core._heavy_queue.reserve("deadbeef", "ctkm")
    core._run_queued_job("deadbeef", "ctkm", work)

    assert job["status"] == "failed"
    assert job["progress"] == 100
    assert not Path(job["output_path"]).exists()
    assert not job_dir.exists()
    assert core._job_public(job)["has_output"] is False


def test_completed_job_is_the_only_downloadable_state(tmp_path):
    core = _fake_core(tmp_path, capacity=1)
    install_runtime_contract(core)
    job = _job(core, "okjob")

    def work(_current):
        Path(job["output_path"]).write_bytes(b"xlsx")
        return {"ok": 1}, []

    core._heavy_queue.reserve("okjob", "ctkm")
    core._run_queued_job("okjob", "ctkm", work)

    assert job["status"] == "completed"
    assert core._job_public(job)["has_output"] is True
    response = core.download_result("okjob")
    assert isinstance(response, FileResponse)

    queued = _job(core, "queued")
    Path(queued["output_path"]).write_bytes(b"partial")
    with pytest.raises(HTTPException) as exc_info:
        core.download_result("queued")
    assert exc_info.value.status_code == 409


def test_cleanup_protects_active_artifacts_and_expires_terminal_and_legacy_jobs(tmp_path):
    core = _fake_core(tmp_path, capacity=2)
    install_runtime_contract(core)

    active = _job(core, "active", status="queued", age_seconds=120)
    active_output = Path(active["output_path"])
    active_output.write_bytes(b"partial")
    active_tmp = core._TMP_DIR / "active"
    active_tmp.mkdir()
    (active_tmp / "source.xlsx").write_bytes(b"source")

    expired = _job(core, "expired", status="completed", age_seconds=120)
    expired_output = Path(expired["output_path"])
    expired_output.write_bytes(b"done")

    legacy_output = core._OUT_DIR / "legacy.xlsx"
    legacy_output.write_bytes(b"done")
    legacy_created = datetime.now() - timedelta(seconds=120)
    core._jobs["legacy"] = {
        "job_id": "legacy",
        "output_path": str(legacy_output),
        "output_name": legacy_output.name,
        "summary": {"tem_r_total_rows": 1},
        "warnings": [],
        "created_at": legacy_created.isoformat(),
    }

    old = datetime.now().timestamp() - 120
    for path in (active_output, active_tmp, expired_output, legacy_output):
        os.utime(path, (old, old))

    core._cleanup_old_jobs()

    assert "active" in core._jobs
    assert active_output.exists()
    assert active_tmp.exists()
    assert "expired" not in core._jobs
    assert not expired_output.exists()
    assert "legacy" not in core._jobs
    assert not legacy_output.exists()


def test_job_list_is_sanitized_and_never_exposes_server_output_path(tmp_path):
    core = _fake_core(tmp_path, capacity=1)
    install_runtime_contract(core)
    job = _job(core, "public", status="completed")
    Path(job["output_path"]).write_bytes(b"done")

    items = core.list_jobs()

    assert len(items) == 1
    assert items[0]["job_id"] == "public"
    assert items[0]["has_output"] is True
    assert "output_path" not in items[0]
    assert "created_timestamp" not in items[0]
