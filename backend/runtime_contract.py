# -*- coding: utf-8 -*-
"""Runtime contracts for queued Excel jobs and downloadable outputs.

This module does not change business processing. It hardens the process-local
queue/job lifecycle used by the FastAPI facade:

* capacity is reserved synchronously before a 202 response is returned;
* queued jobs are visible in queue position immediately;
* failed jobs cannot expose partial output files;
* cleanup protects queued/running artifacts and expires legacy jobs correctly;
* list/download endpoints expose only public lifecycle state.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import threading
import time


_ACTIVE_STATUSES = {"queued", "running", "awaiting_mapping_confirmation"}


class ReservedHeavyJobQueue:
    """Single active worker with synchronous capacity reservation.

    ``reserve`` is called by queued endpoints before the worker thread starts, so
    two concurrent submissions cannot both pass a stale snapshot capacity check.
    Legacy synchronous callers can still call ``acquire`` directly.
    """

    def __init__(self, max_jobs: int = 5):
        self._max_jobs = max(1, int(max_jobs))
        self._condition = threading.Condition()
        self._waiting: list[dict] = []
        self._active: dict | None = None

    def _find_waiting(self, job_id: str):
        return next((entry for entry in self._waiting if entry["job_id"] == job_id), None)

    def reserve(self, job_id: str, kind: str) -> None:
        with self._condition:
            if self._active and self._active["job_id"] == job_id:
                return
            if self._find_waiting(job_id) is not None:
                return
            if len(self._waiting) + (1 if self._active else 0) >= self._max_jobs:
                raise RuntimeError("Hàng đợi đang đầy. Vui lòng chờ một tác vụ hoàn tất rồi thử lại.")
            self._waiting.append({
                "job_id": job_id,
                "kind": kind,
                "queued_at": datetime.now().isoformat(),
                "reserved": True,
            })
            self._condition.notify_all()

    def acquire(self, job_id: str, kind: str) -> None:
        with self._condition:
            entry = self._find_waiting(job_id)
            if entry is None:
                if self._active and self._active["job_id"] == job_id:
                    return
                if len(self._waiting) + (1 if self._active else 0) >= self._max_jobs:
                    raise RuntimeError("Hàng đợi đang đầy. Vui lòng chờ một tác vụ hoàn tất rồi thử lại.")
                entry = {
                    "job_id": job_id,
                    "kind": kind,
                    "queued_at": datetime.now().isoformat(),
                    "reserved": False,
                }
                self._waiting.append(entry)

            while self._active is not None or not self._waiting or self._waiting[0] is not entry:
                self._condition.wait()

            self._waiting.pop(0)
            entry = dict(entry)
            entry.pop("reserved", None)
            entry["started_at"] = datetime.now().isoformat()
            self._active = entry

    def cancel(self, job_id: str) -> None:
        with self._condition:
            self._waiting = [entry for entry in self._waiting if entry["job_id"] != job_id]
            self._condition.notify_all()

    def release(self, job_id: str) -> None:
        with self._condition:
            if self._active and self._active["job_id"] == job_id:
                self._active = None
            self._condition.notify_all()

    def snapshot(self) -> dict:
        with self._condition:
            return {
                "capacity": self._max_jobs,
                "active": dict(self._active) if self._active else None,
                "waiting": [
                    {
                        **{key: value for key, value in entry.items() if key != "reserved"},
                        "position": position,
                    }
                    for position, entry in enumerate(self._waiting, start=1)
                ],
            }


def _output_path(job: dict) -> Path | None:
    raw = str(job.get("output_path") or "").strip()
    return Path(raw) if raw else None


def _created_timestamp(job: dict) -> float:
    raw = job.get("created_timestamp")
    try:
        if raw is not None:
            return float(raw)
    except (TypeError, ValueError):
        pass
    created_at = job.get("created_at")
    if created_at:
        try:
            return datetime.fromisoformat(str(created_at)).timestamp()
        except (TypeError, ValueError):
            pass
    output_path = _output_path(job)
    if output_path is not None:
        try:
            return output_path.stat().st_mtime
        except OSError:
            pass
    return 0.0


def _effective_status(job: dict) -> str:
    status = str(job.get("status") or "").strip().lower()
    if status:
        return status
    # Legacy synchronous /api/tem-r stores a job only after successful workbook
    # creation and historically omitted status/progress fields.
    path = _output_path(job)
    if path is not None and path.is_file() and job.get("summary") is not None:
        return "completed"
    return "failed"


def _remove_tree(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink(missing_ok=True)
    except OSError:
        pass


def _job_temp_paths(core_module, job_id: str, kind: str | None = None) -> list[Path]:
    paths = [core_module._TMP_DIR / job_id, core_module._TMP_DIR / f"tem_r_{job_id}"]
    if kind:
        paths.append(core_module._TMP_DIR / f"{kind}_{job_id}")
    return list(dict.fromkeys(paths))


def install_runtime_contract(core_module) -> None:
    if getattr(core_module.app.state, "runtime_contract_v1", False):
        return

    old_queue = core_module._heavy_queue
    capacity = int(old_queue.snapshot().get("capacity") or 1)
    queue = ReservedHeavyJobQueue(capacity)
    core_module._heavy_queue = queue

    def cleanup_job_artifacts(job_id: str, kind: str | None = None, *, output: bool = False) -> None:
        for path in _job_temp_paths(core_module, job_id, kind):
            _remove_tree(path)
        if output:
            job = core_module._jobs.get(job_id)
            if job:
                _remove_tree(_output_path(job))

    def job_public(job: dict) -> dict:
        status = _effective_status(job)
        if job.get("status") is None:
            job["status"] = status
        if job.get("created_timestamp") is None:
            job["created_timestamp"] = _created_timestamp(job)
        snapshot = queue.snapshot()
        waiting = next(
            (item for item in snapshot["waiting"] if item["job_id"] == job.get("job_id")),
            None,
        )
        output_path = _output_path(job)
        has_output = status == "completed" and output_path is not None and output_path.is_file()
        return {
            key: job.get(key) for key in (
                "job_id", "kind", "status", "progress", "message", "summary",
                "warnings", "error", "created_at", "month",
                "mapping_confirmation", "mapping_sources",
            )
        } | {
            "queue_position": waiting.get("position") if waiting else 0,
            "has_output": has_output,
        }

    def cleanup_old_jobs() -> None:
        cutoff = time.time() - core_module._JOB_TTL_SECONDS
        protected_outputs: set[Path] = set()
        protected_tmp: set[Path] = set()

        for job_id, job in list(core_module._jobs.items()):
            status = _effective_status(job)
            if job.get("status") is None:
                job["status"] = status
            created = _created_timestamp(job)
            job.setdefault("created_timestamp", created)
            output = _output_path(job)
            if status in _ACTIVE_STATUSES:
                if output is not None:
                    protected_outputs.add(output)
                protected_tmp.update(_job_temp_paths(core_module, job_id, job.get("kind")))
                continue
            if created >= cutoff:
                continue
            _remove_tree(output)
            for path in _job_temp_paths(core_module, job_id, job.get("kind")):
                _remove_tree(path)
            core_module._jobs.pop(job_id, None)

        for path in list(core_module._TMP_DIR.iterdir()):
            try:
                if path in protected_tmp or path.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue
            _remove_tree(path)

        for path in list(core_module._OUT_DIR.iterdir()):
            try:
                if path in protected_outputs or path.stat().st_mtime >= cutoff:
                    continue
            except OSError:
                continue
            _remove_tree(path)

    def run_queued_job(job_id: str, kind: str, work) -> None:
        acquired = False
        try:
            queue.acquire(job_id, kind)
            acquired = True
            job = core_module._jobs[job_id]
            job.update(status="running", progress=10, message="Đang xử lý file")
            summary, warnings = work(job)
            output_path = _output_path(job)
            if output_path is None or not output_path.is_file():
                raise RuntimeError("Tác vụ kết thúc nhưng không tạo được file kết quả.")
            job.update(
                status="completed", progress=100, message="Hoàn tất",
                summary=summary, warnings=warnings, error=None,
            )
        except core_module.MappingConfirmationRequired:
            job = core_module._jobs.get(job_id)
            if job is not None:
                job.update(
                    status="awaiting_mapping_confirmation",
                    progress=30,
                    message="Cần xác nhận mapping trước khi tiếp tục",
                    error=None,
                )
        except Exception as exc:
            job = core_module._jobs.get(job_id)
            if job is not None:
                _remove_tree(_output_path(job))
                job.update(
                    status="failed", message="Xử lý thất bại", error=str(exc),
                    progress=100,
                )
        finally:
            if acquired:
                queue.release(job_id)
            else:
                queue.cancel(job_id)
            job = core_module._jobs.get(job_id)
            if not job or job.get("status") != "awaiting_mapping_confirmation":
                cleanup_job_artifacts(job_id, kind)

    def submit_job(job_id: str, kind: str, work) -> None:
        try:
            queue.reserve(job_id, kind)
        except RuntimeError as exc:
            # Input files/directories are already written by the endpoint before
            # submission. Remove them immediately if capacity reservation fails.
            cleanup_job_artifacts(job_id, kind, output=True)
            core_module._jobs.pop(job_id, None)
            raise core_module.HTTPException(status_code=503, detail=str(exc)) from exc

        thread = threading.Thread(
            target=run_queued_job, args=(job_id, kind, work), daemon=True
        )
        try:
            thread.start()
        except Exception:
            queue.cancel(job_id)
            cleanup_job_artifacts(job_id, kind, output=True)
            core_module._jobs.pop(job_id, None)
            raise

    def output_ready(job: dict) -> bool:
        output = _output_path(job)
        return _effective_status(job) == "completed" and output is not None and output.is_file()

    def replace_route(path: str, method: str, endpoint) -> None:
        for route in core_module.app.routes:
            if getattr(route, "path", None) != path:
                continue
            if method not in (getattr(route, "methods", None) or set()):
                continue
            route.endpoint = endpoint
            dependant = getattr(route, "dependant", None)
            if dependant is not None:
                dependant.call = endpoint
            return
        raise RuntimeError(f"Không tìm thấy route {method} {path} để cài runtime contract")

    def download_result(job_id: str, _admin: str | None = None):
        job = core_module._jobs.get(job_id)
        if not job:
            raise core_module.HTTPException(
                status_code=404, detail=f"Khong tim thay job '{job_id}'"
            )
        status = _effective_status(job)
        if status in _ACTIVE_STATUSES:
            raise core_module.HTTPException(
                status_code=409, detail="Tác vụ chưa hoàn tất; chưa có file để tải."
            )
        if status != "completed":
            raise core_module.HTTPException(
                status_code=409, detail="Tác vụ thất bại; không có file kết quả hợp lệ."
            )
        path = _output_path(job)
        if path is None or not path.is_file():
            raise core_module.HTTPException(
                status_code=404, detail="File kết quả đã hết hạn hoặc không còn tồn tại."
            )
        return core_module.FileResponse(
            path=str(path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=job.get("output_name") or path.name,
        )

    def list_jobs(_admin: str | None = None):
        cleanup_old_jobs()
        return sorted(
            [job_public(job) for job in core_module._jobs.values()],
            key=lambda item: item.get("created_at") or "",
            reverse=True,
        )

    core_module._cleanup_old_jobs = cleanup_old_jobs
    core_module._job_public = job_public
    core_module._run_queued_job = run_queued_job
    core_module._submit_job = submit_job
    core_module._job_output_ready = output_ready
    core_module._effective_job_status = _effective_status
    core_module._cleanup_job_artifacts = cleanup_job_artifacts

    replace_route("/api/download/{job_id}", "GET", download_result)
    replace_route("/api/jobs", "GET", list_jobs)
    core_module.download_result = download_result
    core_module.list_jobs = list_jobs
    core_module.app.state.runtime_contract_v1 = True
