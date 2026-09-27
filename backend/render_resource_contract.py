# -*- coding: utf-8 -*-
"""Render resource guard for process-local heavy Excel jobs.

The CTKM endpoint performs a mapping preflight before it submits the real job.
On small Render instances that preflight can temporarily retain upload bytes and
DataFrames until the request coroutine returns. Starting the worker immediately
creates a needless peak where preflight objects and full pipeline objects coexist.

This contract keeps synchronous queue reservation semantics, but dispatches the
worker on the next event-loop turn. That lets the request frame become collectible
before the full pipeline starts. It also emits lightweight RSS stage logs so a
future platform restart can be localized to preflight/pipeline/export instead of
showing up only as a generic HTTP 503 in the browser.
"""
from __future__ import annotations

import asyncio
import gc
from pathlib import Path
import threading


def current_rss_mb() -> float | None:
    """Return current Linux RSS in MiB without adding a psutil dependency."""
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                parts = line.split()
                if len(parts) >= 2:
                    return round(int(parts[1]) / 1024.0, 1)
    except (OSError, ValueError):
        pass
    return None


def _log(job_id: str, kind: str, stage: str, *, detail: str | None = None) -> None:
    rss = current_rss_mb()
    suffix = f" detail={detail}" if detail else ""
    print(
        f"[CTKM-RUNTIME] job={job_id} kind={kind} stage={stage} "
        f"rss_mb={rss if rss is not None else 'unknown'}{suffix}",
        flush=True,
    )


def _shrink_known_upload_closure(work) -> None:
    """Drop retained Clearance bytes while preserving the closure's boolean use.

    The current CTKM work closure only evaluates ``clearance_content is not None``
    after submission; it never reads the bytes again because the upload has already
    been written to disk. Replacing a captured bytes object with ``True`` preserves
    that exact condition and can release up to MAX_PIPELINE_FILE_MB before the full
    pipeline starts. If the closure shape changes, this helper safely does nothing.
    """
    closure = getattr(work, "__closure__", None)
    freevars = getattr(getattr(work, "__code__", None), "co_freevars", ())
    if not closure or not freevars:
        return
    for name, cell in zip(freevars, closure):
        if name != "clearance_content":
            continue
        try:
            value = cell.cell_contents
        except ValueError:
            continue
        if isinstance(value, (bytes, bytearray, memoryview)):
            try:
                cell.cell_contents = True
            except (AttributeError, TypeError, ValueError):
                pass


def install_render_resource_contract(core_module) -> None:
    if getattr(core_module.app.state, "render_resource_contract_v1", False):
        return

    queue = core_module._heavy_queue
    cleanup_job_artifacts = core_module._cleanup_job_artifacts

    def run_queued_job(job_id: str, kind: str, work) -> None:
        acquired = False
        _log(job_id, kind, "worker_wait")
        try:
            queue.acquire(job_id, kind)
            acquired = True
            job = core_module._jobs[job_id]
            job.update(status="running", progress=10, message="Đang xử lý file")
            _log(job_id, kind, "pipeline_start")

            summary, warnings = work(job)
            output_raw = str(job.get("output_path") or "").strip()
            output_path = Path(output_raw) if output_raw else None
            if output_path is None or not output_path.is_file():
                raise RuntimeError("Tác vụ kết thúc nhưng không tạo được file kết quả.")

            job.update(
                status="completed", progress=100, message="Hoàn tất",
                summary=summary, warnings=warnings, error=None,
            )
            _log(job_id, kind, "pipeline_complete")
        except core_module.MappingConfirmationRequired:
            job = core_module._jobs.get(job_id)
            if job is not None:
                job.update(
                    status="awaiting_mapping_confirmation",
                    progress=30,
                    message="Cần xác nhận mapping trước khi tiếp tục",
                    error=None,
                )
            _log(job_id, kind, "mapping_confirmation_required")
        except Exception as exc:
            job = core_module._jobs.get(job_id)
            if job is not None:
                output_raw = str(job.get("output_path") or "").strip()
                if output_raw:
                    try:
                        Path(output_raw).unlink(missing_ok=True)
                    except OSError:
                        pass
                job.update(
                    status="failed", message="Xử lý thất bại", error=str(exc),
                    progress=100,
                )
            _log(job_id, kind, "pipeline_failed", detail=f"{type(exc).__name__}: {exc}")
        finally:
            if acquired:
                queue.release(job_id)
            else:
                queue.cancel(job_id)
            job = core_module._jobs.get(job_id)
            if not job or job.get("status") != "awaiting_mapping_confirmation":
                cleanup_job_artifacts(job_id, kind)
            gc.collect()
            _log(job_id, kind, "worker_released")

    def submit_job(job_id: str, kind: str, work) -> None:
        try:
            queue.reserve(job_id, kind)
        except RuntimeError as exc:
            cleanup_job_artifacts(job_id, kind, output=True)
            core_module._jobs.pop(job_id, None)
            raise core_module.HTTPException(status_code=503, detail=str(exc)) from exc

        _shrink_known_upload_closure(work)
        _log(job_id, kind, "reserved")

        def start_worker() -> None:
            # This callback runs after the request coroutine has yielded/returned.
            # Collect preflight DataFrames/upload buffers before loading them again.
            gc.collect()
            _log(job_id, kind, "dispatch")
            thread = threading.Thread(
                target=run_queued_job, args=(job_id, kind, work), daemon=True
            )
            try:
                thread.start()
            except Exception as exc:
                queue.cancel(job_id)
                cleanup_job_artifacts(job_id, kind, output=True)
                job = core_module._jobs.get(job_id)
                if job is not None:
                    job.update(
                        status="failed", progress=100,
                        message="Không khởi động được tác vụ", error=str(exc),
                    )
                _log(job_id, kind, "dispatch_failed", detail=f"{type(exc).__name__}: {exc}")

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Synchronous tests/CLI compatibility.
            start_worker()
        else:
            loop.call_soon(start_worker)

    core_module._run_queued_job = run_queued_job
    core_module._submit_job = submit_job
    core_module.app.state.render_resource_contract_v1 = True
