# -*- coding: utf-8 -*-
"""
FastAPI Backend — CTKM Pipeline API
=====================================
Endpoints:
  POST /api/run        — upload 2 file, chon thang, chay pipeline, tra ket qua
  GET  /api/download   — download file Excel ket qua
  GET  /api/preview    — lay du lieu preview (JSON, N dong dau moi sheet)
  GET  /api/health     — health check

Chay local:
  uvicorn backend.main_api:app --reload --port 8000

Cau hinh CORS cho phep frontend Vite (http://localhost:5173) goi duoc.
"""
from __future__ import annotations

import importlib.util
import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
import types
import uuid
from collections import OrderedDict
from datetime import datetime
import tempfile
from pathlib import Path
from typing import Optional

import uvicorn
import pandas as pd
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── Duong dan goc du an ──────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent
_ROOT        = _BACKEND_DIR.parent          # thu muc ctkm_pipeline/
_MDIR        = _ROOT / "modules"
_TMP_DIR     = Path(tempfile.gettempdir()) / "ctkm_pipeline_backend"  # tmp ngoai project de khong kich hoat reload
_OUT_DIR     = _ROOT / "output"
_PRESETS_PATH = _ROOT / "logs" / "workflow_presets.json"
_TMP_DIR.mkdir(parents=True, exist_ok=True)
_OUT_DIR.mkdir(parents=True, exist_ok=True)
_PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
except ImportError:
    pass

# ── Bootstrap pipeline modules (giong main.py) ───────────────────────────────
def _boot_modules():
    if "modules" not in sys.modules:
        pkg = types.ModuleType("modules")
        pkg.__path__ = [str(_MDIR)]
        sys.modules["modules"] = pkg

def _imp(filename: str, alias: str):
    full = f"modules.{alias}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, _MDIR / filename)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    setattr(sys.modules["modules"], alias, mod)
    spec.loader.exec_module(mod)
    return mod

_boot_modules()
_imp("config_loader.py",      "config_loader")
_imp("1_loader.py",           "loader")
_imp("2_sheet_classifier.py", "classifier")
_imp("3_column_mapper.py",    "column_mapper")
_imp("4_mapping_cache.py",    "mapping_cache")
_imp("5_normalizer.py",       "normalizer")
_imp("6_time_filter.py",      "time_filter")
_imp("7_joiner.py",           "joiner")
_imp("8_reconciler.py",       "reconciler")
_imp("9_exporter.py",         "exporter")
_tem_r_mod = _imp("10_tem_r.py", "tem_r")
_expiration_mod = _imp("11_expiration_checker.py", "expiration_checker")

# Import ham chay pipeline tu main.py
_main_spec = importlib.util.spec_from_file_location("ctkm_main", _ROOT / "main.py")
_main_mod  = importlib.util.module_from_spec(_main_spec)
sys.modules["ctkm_main"] = _main_mod
_main_spec.loader.exec_module(_main_mod)
run_pipeline = _main_mod.run_pipeline
list_ctkm_sheet_names = _main_mod.list_ctkm_sheet_names
preview_mapping = _main_mod.preview_mapping

# Import exception class de bat rate limit error rieng
_cm_mod = sys.modules.get("modules.column_mapper")
GeminiRateLimitError = getattr(_cm_mod, "GeminiRateLimitError", None) if _cm_mod else None

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="CTKM Pipeline API",
    description="Tong hop chuong trinh khuyen mai + vi tri ke theo thang.",
    version="1.0.0",
)

def _get_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173")
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or ["http://localhost:5173", "http://localhost:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory job store (don gian cho 1 server, 1 process) ───────────────────
# Voi production nhieu user dong thoi, thay bang Redis / DB
_jobs: dict[str, dict] = {}
_gemini_cooldown_until: float = 0.0
_gemini_cooldown_lock = threading.Lock()


class _HeavyJobQueue:
    """One in-process lane for memory/CPU-heavy Excel jobs."""

    def __init__(self, max_jobs: int = 5):
        self._max_jobs = max(1, max_jobs)
        self._condition = threading.Condition()
        self._waiting: list[dict] = []
        self._active: dict | None = None

    def acquire(self, job_id: str, kind: str) -> None:
        entry = {"job_id": job_id, "kind": kind, "queued_at": datetime.now().isoformat()}
        with self._condition:
            if len(self._waiting) + (1 if self._active else 0) >= self._max_jobs:
                raise RuntimeError("Hàng đợi đang đầy. Vui lòng chờ một tác vụ hoàn tất rồi thử lại.")
            self._waiting.append(entry)
            while self._active is not None or self._waiting[0] is not entry:
                self._condition.wait()
            self._waiting.pop(0)
            entry["started_at"] = datetime.now().isoformat()
            self._active = entry

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
                    {**entry, "position": position}
                    for position, entry in enumerate(self._waiting, start=1)
                ],
            }


_heavy_queue = _HeavyJobQueue(int(os.getenv("HEAVY_JOB_QUEUE_SIZE", "5")))
_expiration_slots = threading.BoundedSemaphore(
    max(1, int(os.getenv("EXPIRATION_CONCURRENCY", "5")))
)
_expiration_cache_lock = threading.Lock()
_expiration_cache: OrderedDict[str, tuple[pd.DataFrame, str]] = OrderedDict()
_EXPIRATION_CACHE_SIZE = max(1, int(os.getenv("EXPIRATION_CACHE_SIZE", "1")))
_MAX_EXPIRATION_BYTES = int(os.getenv("MAX_EXPIRATION_FILE_MB", "20")) * 1024 * 1024
_MAX_TEM_R_BYTES = int(os.getenv("MAX_TEM_R_FILE_MB", "25")) * 1024 * 1024
_MAX_PIPELINE_BYTES = int(os.getenv("MAX_PIPELINE_FILE_MB", "50")) * 1024 * 1024
_JOB_TTL_SECONDS = max(900, int(os.getenv("JOB_TTL_SECONDS", "21600")))


async def _read_upload_limited(upload: UploadFile, max_bytes: int, label: str) -> bytes:
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"{label} vượt quá giới hạn {max_bytes // (1024 * 1024)} MB",
        )
    if not content:
        raise HTTPException(status_code=422, detail=f"{label} đang trống")
    return content


def _cleanup_old_jobs() -> None:
    cutoff = time.time() - _JOB_TTL_SECONDS
    for job_id, job in list(_jobs.items()):
        created = job.get("created_timestamp", time.time())
        if created >= cutoff or job.get("status") in {"queued", "running"}:
            continue
        path = Path(job.get("output_path", ""))
        if path.is_file():
            path.unlink(missing_ok=True)
        _jobs.pop(job_id, None)
    for path in _TMP_DIR.iterdir():
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                for child in path.iterdir():
                    if child.is_file():
                        child.unlink(missing_ok=True)
                path.rmdir()
        except OSError:
            pass
    for path in _OUT_DIR.iterdir():
        try:
            if path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
        except OSError:
            pass


def _new_job(job_id: str, kind: str, output_path: Path, output_name: str, **extra) -> dict:
    now = time.time()
    job = {
        "job_id": job_id, "kind": kind, "status": "queued", "progress": 0,
        "message": "Đã vào hàng đợi", "output_path": str(output_path),
        "output_name": output_name, "summary": {}, "warnings": [],
        "error": None, "created_at": datetime.now().isoformat(),
        "created_timestamp": now, **extra,
    }
    _jobs[job_id] = job
    return job


def _run_queued_job(job_id: str, kind: str, work) -> None:
    try:
        _heavy_queue.acquire(job_id, kind)
        job = _jobs[job_id]
        job.update(status="running", progress=10, message="Đang xử lý file")
        summary, warnings = work(job)
        job.update(status="completed", progress=100, message="Hoàn tất", summary=summary, warnings=warnings)
    except Exception as exc:
        job = _jobs.get(job_id)
        if job is not None:
            job.update(status="failed", message="Xử lý thất bại", error=str(exc))
    finally:
        _heavy_queue.release(job_id)


def _submit_job(job_id: str, kind: str, work) -> None:
    snapshot = _heavy_queue.snapshot()
    if len(snapshot["waiting"]) + (1 if snapshot["active"] else 0) >= snapshot["capacity"]:
        _jobs.pop(job_id, None)
        raise HTTPException(status_code=503, detail="Hàng đợi đang đầy. Vui lòng thử lại sau.")
    threading.Thread(target=_run_queued_job, args=(job_id, kind, work), daemon=True).start()


def _job_public(job: dict) -> dict:
    snapshot = _heavy_queue.snapshot()
    waiting = next((item for item in snapshot["waiting"] if item["job_id"] == job["job_id"]), None)
    return {
        key: job.get(key) for key in (
            "job_id", "kind", "status", "progress", "message", "summary",
            "warnings", "error", "created_at", "month",
        )
    } | {"queue_position": waiting.get("position") if waiting else 0, "has_output": Path(job["output_path"]).is_file()}


def _load_expiration_cached(content: bytes) -> tuple[pd.DataFrame, str, bool]:
    """Parse identical inventory exports once; cache is bounded for Render RAM."""
    fingerprint = hashlib.sha256(content).hexdigest()
    with _expiration_cache_lock:
        cached = _expiration_cache.get(fingerprint)
        if cached is not None:
            _expiration_cache.move_to_end(fingerprint)
            return cached[0], cached[1], True
        frame, sheet_name = _expiration_mod.load_expiration_export(content)
        _expiration_cache[fingerprint] = (frame, sheet_name)
        while len(_expiration_cache) > _EXPIRATION_CACHE_SIZE:
            _expiration_cache.popitem(last=False)
        return frame, sheet_name, False

# Admin auth is stateless so a Render restart does not invalidate server-side
# sessions. ADMIN_PASSWORD is mandatory; ADMIN_SESSION_SECRET is recommended.
_ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip() or "admin"
_ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
_ADMIN_SESSION_SECRET = os.getenv("ADMIN_SESSION_SECRET", "") or _ADMIN_PASSWORD
_ADMIN_TOKEN_TTL = max(300, int(os.getenv("ADMIN_TOKEN_TTL_SECONDS", "43200")))


def _token_signature(payload: str) -> str:
    digest = hmac.new(
        _ADMIN_SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _create_admin_token() -> str:
    expires_at = int(time.time()) + _ADMIN_TOKEN_TTL
    payload = f"admin:{expires_at}:{secrets.token_hex(8)}"
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{encoded}.{_token_signature(encoded)}"


def _validate_admin_token(token: str) -> bool:
    if not _ADMIN_PASSWORD or not _ADMIN_SESSION_SECRET or "." not in token:
        return False
    encoded, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _token_signature(encoded)):
        return False
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = base64.urlsafe_b64decode(padded).decode("utf-8")
        role, expires_at, _nonce = payload.split(":", 2)
        return role == "admin" and int(expires_at) > int(time.time())
    except (ValueError, UnicodeDecodeError):
        return False


def require_admin(authorization: Optional[str] = Header(None)) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not _validate_admin_token(token.strip()):
        raise HTTPException(status_code=401, detail="Cần đăng nhập bằng tài khoản admin")
    return "admin"


def _set_gemini_cooldown(seconds: int) -> None:
    global _gemini_cooldown_until
    with _gemini_cooldown_lock:
        _gemini_cooldown_until = max(_gemini_cooldown_until, time.time() + max(60, seconds))


def _enforce_gemini_cooldown() -> None:
    with _gemini_cooldown_lock:
        remaining = max(0, int(_gemini_cooldown_until - time.time()))
    if remaining:
        raise HTTPException(
            status_code=429,
            detail={
                "type": "gemini_cooldown",
                "message": f"Gemini đang trong cooldown. Thử lại sau {remaining} giây hoặc dùng chế độ chỉ mapping đã lưu.",
                "suggestion": "Không chạy lại chế độ Gemini trong thời gian cooldown để tránh lãng phí quota.",
            },
            headers={"Retry-After": str(remaining)},
        )


def _preset_key(ctkm_columns, pog_columns) -> str:
    return "|".join(sorted(str(c).strip().lower() for c in ctkm_columns)) + "::" + \
        "|".join(sorted(str(c).strip().lower() for c in pog_columns))


def _load_presets() -> dict:
    if not _PRESETS_PATH.exists():
        return {}
    try:
        return json.loads(_PRESETS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_presets(presets: dict) -> None:
    _PRESETS_PATH.write_text(json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_saved_preset(ctkm_columns, pog_columns) -> dict:
    return _load_presets().get(_preset_key(ctkm_columns, pog_columns), {})


def _store_preset(ctkm_columns, pog_columns, ctkm_mapping=None, pog_mapping=None, output_columns=None) -> None:
    presets = _load_presets()
    key = _preset_key(ctkm_columns, pog_columns)
    current = presets.get(key, {})
    if ctkm_mapping is not None:
        current["ctkm_mapping"] = ctkm_mapping
    if pog_mapping is not None:
        current["pog_mapping"] = pog_mapping
    if output_columns is not None:
        current["output_columns"] = output_columns
    current["updated_at"] = datetime.now().isoformat()
    presets[key] = current
    _save_presets(presets)


def _list_presets() -> list[dict]:
    presets = _load_presets()
    results = []
    for key, value in presets.items():
        ctkm_sig, pog_sig = key.split("::", 1) if "::" in key else (key, "")
        results.append({
            "key": key,
            "ctkm_signature": ctkm_sig,
            "pog_signature": pog_sig,
            "updated_at": value.get("updated_at"),
            "has_ctkm_mapping": bool(value.get("ctkm_mapping")),
            "has_pog_mapping": bool(value.get("pog_mapping")),
            "has_output_columns": bool(value.get("output_columns")),
        })
    return sorted(results, key=lambda item: item.get("updated_at") or "", reverse=True)


def _delete_preset(key: str) -> bool:
    presets = _load_presets()
    if key not in presets:
        return False
    del presets[key]
    _save_presets(presets)
    return True


@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.post("/api/auth/login")
def admin_login(
    username: str = Form(...),
    password: str = Form(...),
):
    if not _ADMIN_PASSWORD:
        raise HTTPException(
            status_code=503,
            detail="Admin chưa được cấu hình. Hãy đặt ADMIN_PASSWORD trên Render.",
        )
    valid_user = hmac.compare_digest(username.strip(), _ADMIN_USERNAME)
    valid_password = hmac.compare_digest(password, _ADMIN_PASSWORD)
    if not (valid_user and valid_password):
        raise HTTPException(status_code=401, detail="Sai tài khoản hoặc mật khẩu")
    return {
        "access_token": _create_admin_token(),
        "token_type": "bearer",
        "expires_in": _ADMIN_TOKEN_TTL,
        "role": "admin",
    }


@app.get("/api/auth/me")
def auth_me(_admin: str = Depends(require_admin)):
    return {"role": "admin", "username": _ADMIN_USERNAME}


@app.get("/api/queue/status")
def queue_status(_admin: str = Depends(require_admin)):
    return _heavy_queue.snapshot()


@app.get("/api/job/{job_id}/status")
def job_status(job_id: str, _admin: str = Depends(require_admin)):
    _cleanup_old_jobs()
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ")
    return _job_public(job)


@app.post("/api/jobs/tem-r", status_code=202)
async def enqueue_tem_r(
    tem_r_file: UploadFile = File(...), max_location_distance: float = Form(1),
    stock_column: str = Form(...), column_mapping: Optional[str] = Form(None),
    sheet_name: Optional[str] = Form(None), header_row: Optional[int] = Form(None),
    _admin: str = Depends(require_admin),
):
    _cleanup_old_jobs()
    if not tem_r_file.filename or not tem_r_file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="tem_r_file phải là file .xlsx")
    content = await _read_upload_limited(tem_r_file, _MAX_TEM_R_BYTES, "File Tem R")
    mapping = json.loads(column_mapping) if column_mapping else None
    if mapping is not None and not isinstance(mapping, dict):
        raise HTTPException(status_code=422, detail="Ánh xạ cột Tem R không hợp lệ")
    job_id = uuid.uuid4().hex[:8]
    job_dir = _TMP_DIR / f"tem_r_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    source_path, output_path = job_dir / "tem_r.xlsx", _OUT_DIR / f"tem_r_{job_id}.xlsx"
    source_path.write_bytes(content)
    job = _new_job(job_id, "tem_r", output_path, output_path.name)

    def work(current):
        current.update(progress=30, message="Đang phân bổ Tem R")
        try:
            plan = _tem_r_mod.create_tem_r_workbook(
                source_path, output_path, max_location_distance=max_location_distance,
                stock_column=stock_column.strip(), column_mapping=mapping,
                sheet_name=sheet_name, header_row=header_row,
            )
            summary = {
                "tem_r_total_rows": len(plan.rows),
                "tem_r_replaced_rows": int(plan.rows["TEM_R_REPRESENTATIVE"].notna().sum()),
                "tem_r_exceptions": len(plan.exceptions),
            }
            return summary, plan.exceptions["reason"].tolist()
        finally:
            source_path.unlink(missing_ok=True)

    _submit_job(job_id, "tem_r", work)
    return _job_public(job)


@app.post("/api/jobs/ctkm", status_code=202)
async def enqueue_ctkm(
    ctkm_file: UploadFile = File(...), pog_file: UploadFile = File(...),
    month: str = Form(...), strict_month: bool = Form(False),
    ctkm_sheet_name: Optional[str] = Form(None),
    ctkm_mapping_override: Optional[str] = Form(None),
    pog_mapping_override: Optional[str] = Form(None),
    selected_output_columns: Optional[str] = Form(None),
    mapping_mode: str = Form("auto"), _admin: str = Depends(require_admin),
):
    import re
    _cleanup_old_jobs()
    if not re.match(r"^\d{4}-\d{2}$", month):
        raise HTTPException(status_code=422, detail="month phải có dạng YYYY-MM")
    if not ctkm_file.filename.lower().endswith(".xlsx") or not pog_file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="CTKM và POG phải là file .xlsx")
    if mapping_mode not in {"auto", "saved_only"}:
        raise HTTPException(status_code=422, detail="mapping_mode không hợp lệ")
    if mapping_mode == "auto":
        _enforce_gemini_cooldown()
    ctkm_content, pog_content = await asyncio.gather(
        _read_upload_limited(ctkm_file, _MAX_PIPELINE_BYTES, "File CTKM"),
        _read_upload_limited(pog_file, _MAX_PIPELINE_BYTES, "File POG"),
    )
    try:
        ctkm_override = json.loads(ctkm_mapping_override) if ctkm_mapping_override else None
        pog_override = json.loads(pog_mapping_override) if pog_mapping_override else None
        output_columns = json.loads(selected_output_columns) if selected_output_columns else None
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"JSON cấu hình không hợp lệ: {exc.msg}") from exc
    job_id = uuid.uuid4().hex[:8]
    job_dir = _TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    ctkm_path, pog_path = job_dir / "ctkm.xlsx", job_dir / "pog.xlsx"
    output_path = _OUT_DIR / f"tong_hop_ctkm_{month}_{job_id}.xlsx"
    ctkm_path.write_bytes(ctkm_content); pog_path.write_bytes(pog_content)
    job = _new_job(job_id, "ctkm", output_path, output_path.name, month=month)

    def work(current):
        try:
            current.update(progress=20, message="Đang đọc CTKM và POG")
            local_ctkm, local_pog, local_output = ctkm_override, pog_override, output_columns
            wb_ctkm = _main_mod.L.load_workbook_raw(str(ctkm_path), is_pog_file=False)
            wb_pog = _main_mod.L.load_workbook_raw(str(pog_path), is_pog_file=True)
            _primary_name, primary_sheet = _main_mod._select_primary_ctkm_sheet(wb_ctkm, ctkm_sheet_name)
            pog_name = next(iter(wb_pog.sheets)) if wb_pog.sheets else None
            if pog_name:
                preset = _get_saved_preset(list(primary_sheet.df.columns), list(wb_pog.sheets[pog_name].df.columns))
                local_ctkm = local_ctkm or preset.get("ctkm_mapping")
                local_pog = local_pog or preset.get("pog_mapping")
                local_output = local_output or preset.get("output_columns")
            if mapping_mode == "saved_only" and (not local_ctkm or not local_pog):
                raise ValueError("Chưa có mapping đã lưu cho cấu trúc hai file này")
            current.update(progress=45, message="Đang ghép dữ liệu và xuất Excel")
            result = run_pipeline(
                str(ctkm_path), str(pog_path), month, str(output_path), strict_month,
                ctkm_sheet_name, local_ctkm, local_pog, local_output,
            )
            return result.summary, result.warnings
        finally:
            ctkm_path.unlink(missing_ok=True); pog_path.unlink(missing_ok=True)

    _submit_job(job_id, "ctkm", work)
    return _job_public(job)


@app.post("/api/check-expiration")
async def check_expiration(
    expiration_file: UploadFile = File(..., description="File Detail Expiration Onhand by Item (.xlsx)"),
    entries: str = Form(..., description="Mỗi dòng: ITEMID;BATCHNUMER;DD/MM/YYYY"),
):
    """Đối chiếu danh sách mã sản phẩm, số lô và hạn dùng với file Excel."""
    if not expiration_file.filename or not expiration_file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="expiration_file phải là file .xlsx")
    content = await _read_upload_limited(expiration_file, _MAX_EXPIRATION_BYTES, "File hạn dùng")
    await asyncio.to_thread(_expiration_slots.acquire)
    try:
        frame, sheet_name, cache_hit = await asyncio.to_thread(_load_expiration_cached, content)
        results = await asyncio.to_thread(_expiration_mod.check_entries, frame, entries)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc file hạn dùng: {exc}") from exc
    finally:
        _expiration_slots.release()
    matched = sum(row["status"] == "matched" for row in results)
    return {
        "sheet_name": sheet_name,
        "source_rows": len(frame),
        "total": len(results),
        "matched": matched,
        "unmatched": len(results) - matched,
        "cache_hit": cache_hit,
        "results": results,
    }


@app.post("/api/tem-r")
async def run_tem_r(
    tem_r_file: UploadFile = File(..., description="File Tem R (.xlsx)"),
    max_location_distance: float = Form(1, description="Khoảng cách vị trí kệ tối đa"),
    stock_column: str = Form(..., description="Tên cột tồn kho do người dùng xác nhận"),
    column_mapping: Optional[str] = Form(None, description="JSON ánh xạ cột bắt buộc Tem R"),
    sheet_name: Optional[str] = Form(None, description="Sheet dữ liệu Tem R"),
    header_row: Optional[int] = Form(None, description="Dòng tiêu đề Tem R"),
    _admin: str = Depends(require_admin),
):
    """Phân bổ Tem R theo tồn dư và vị trí liền kề trên cùng kệ."""
    if not tem_r_file.filename or not tem_r_file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="tem_r_file phải là file .xlsx")
    if max_location_distance <= 0:
        raise HTTPException(status_code=422, detail="max_location_distance phải lớn hơn 0")
    if not stock_column.strip():
        raise HTTPException(status_code=422, detail="Hãy chọn cột tồn kho")

    job_id = uuid.uuid4().hex[:8]
    job_dir = _TMP_DIR / f"tem_r_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    source_path = job_dir / "tem_r.xlsx"
    output_path = _OUT_DIR / f"tem_r_{job_id}.xlsx"
    source_path.write_bytes(await _read_upload_limited(tem_r_file, _MAX_TEM_R_BYTES, "File Tem R"))
    acquired = False
    try:
        parsed_mapping = json.loads(column_mapping) if column_mapping else None
        if parsed_mapping is not None and not isinstance(parsed_mapping, dict):
            raise ValueError("Ánh xạ cột Tem R không hợp lệ")
        try:
            await asyncio.to_thread(_heavy_queue.acquire, job_id, "tem_r")
            acquired = True
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        plan = await asyncio.to_thread(
            _tem_r_mod.create_tem_r_workbook,
            source_path,
            output_path,
            max_location_distance=max_location_distance,
            stock_column=stock_column.strip(),
            column_mapping=parsed_mapping,
            sheet_name=sheet_name,
            header_row=header_row,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý Tem R: {exc}") from exc
    finally:
        if acquired:
            _heavy_queue.release(job_id)

    _jobs[job_id] = {
        "job_id": job_id,
        "month": None,
        "output_path": str(output_path),
        "output_name": output_path.name,
        "summary": {
            "tem_r_total_rows": len(plan.rows),
            "tem_r_replaced_rows": int(plan.rows["TEM_R_REPRESENTATIVE"].notna().mul(plan.rows["TEM R"].notna()).sum()),
            "tem_r_exceptions": len(plan.exceptions),
        },
        "warnings": plan.exceptions["reason"].tolist(),
        "created_at": datetime.now().isoformat(),
    }
    return {"job_id": job_id, "summary": _jobs[job_id]["summary"], "warnings": _jobs[job_id]["warnings"]}


@app.post("/api/inspect-tem-r")
async def inspect_tem_r_file(
    tem_r_file: UploadFile = File(..., description="File Tem R (.xlsx)"),
    _admin: str = Depends(require_admin),
):
    """Read headers so the user can explicitly confirm which column contains stock."""
    if not tem_r_file.filename or not tem_r_file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="tem_r_file phải là file .xlsx")
    job_dir = _TMP_DIR / f"inspect_tem_r_{uuid.uuid4().hex[:8]}"
    job_dir.mkdir(parents=True, exist_ok=True)
    source_path = job_dir / "tem_r.xlsx"
    source_path.write_bytes(await _read_upload_limited(tem_r_file, _MAX_TEM_R_BYTES, "File Tem R"))
    try:
        result = await asyncio.to_thread(_tem_r_mod.inspect_tem_r_workbook, source_path)
        columns = result["columns"]
        normalized = {str(column).strip().upper(): column for column in columns}
        result["required_columns"] = list(_tem_r_mod.REQUIRED_COLUMNS)
        result["suggested_mapping"] = {
            canonical: normalized.get(canonical, "") for canonical in _tem_r_mod.REQUIRED_COLUMNS
        }
        for option in result.get("sheet_options", []):
            lookup = {str(column).strip().upper(): column for column in option["columns"]}
            option["suggested_mapping"] = {
                canonical: lookup.get(canonical, "") for canonical in _tem_r_mod.REQUIRED_COLUMNS
            }
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi đọc cột file Tem R: {exc}") from exc


@app.get("/api/presets")
def get_presets(_admin: str = Depends(require_admin)):
    """Tra ve danh sach preset workflow da luu."""
    return {"items": _list_presets(), "count": len(_list_presets())}


@app.post("/api/presets")
def save_preset(
    ctkm_columns: str = Form(..., description="JSON array cột CTKM"),
    pog_columns: str = Form(..., description="JSON array cột POG"),
    ctkm_mapping: str = Form(..., description="JSON mapping CTKM đã xác nhận"),
    pog_mapping: str = Form(..., description="JSON mapping POG đã xác nhận"),
    selected_output_columns: Optional[str] = Form(None, description="JSON array cột output"),
    _admin: str = Depends(require_admin),
):
    """Lưu mapping đã duyệt ngay, để lần chạy sau không cần gọi Gemini."""
    try:
        parsed_ctkm_columns = json.loads(ctkm_columns)
        parsed_pog_columns = json.loads(pog_columns)
        parsed_ctkm_mapping = json.loads(ctkm_mapping)
        parsed_pog_mapping = json.loads(pog_mapping)
        parsed_output_columns = json.loads(selected_output_columns) if selected_output_columns else None
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Preset JSON không hợp lệ: {exc.msg}") from exc
    if not all(isinstance(value, list) for value in (parsed_ctkm_columns, parsed_pog_columns)):
        raise HTTPException(status_code=422, detail="Danh sách cột preset phải là JSON array")
    if not all(isinstance(value, dict) for value in (parsed_ctkm_mapping, parsed_pog_mapping)):
        raise HTTPException(status_code=422, detail="Mapping preset phải là JSON object")
    try:
        _main_mod._validate_manual_mapping(
            parsed_ctkm_mapping,
            pd.DataFrame(columns=parsed_ctkm_columns),
            _main_mod.SCHEMA["fact_fields"],
        )
        _main_mod._validate_manual_mapping(
            parsed_pog_mapping,
            pd.DataFrame(columns=parsed_pog_columns),
            _main_mod.SCHEMA["pog_fields"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _store_preset(
        parsed_ctkm_columns,
        parsed_pog_columns,
        ctkm_mapping=parsed_ctkm_mapping,
        pog_mapping=parsed_pog_mapping,
        output_columns=parsed_output_columns,
    )
    return {"saved": True, "key": _preset_key(parsed_ctkm_columns, parsed_pog_columns)}


@app.delete("/api/presets")
def delete_preset(key: str, _admin: str = Depends(require_admin)):
    """Xoa preset theo key signature."""
    if not key:
        raise HTTPException(status_code=422, detail="key khong duoc trong")
    if not _delete_preset(key):
        raise HTTPException(status_code=404, detail=f"Khong tim thay preset '{key}'")
    return {"deleted": True, "key": key}


@app.post("/api/inspect-ctkm")
async def inspect_ctkm_file(
    ctkm_file: UploadFile = File(..., description="File Excel CTKM (.xlsx)"),
    _admin: str = Depends(require_admin),
):
    """Doc 1 lan file CTKM de tra ve danh sach sheet co du lieu cho nguoi dung chon."""
    if not ctkm_file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="ctkm_file phai la file .xlsx")

    tmp_path = _TMP_DIR / f"inspect_{uuid.uuid4().hex[:8]}.xlsx"
    tmp_path.write_bytes(await _read_upload_limited(ctkm_file, _MAX_PIPELINE_BYTES, "File CTKM"))
    try:
        wb_ctkm = await asyncio.to_thread(
            _main_mod.L.load_workbook_raw, str(tmp_path), is_pog_file=False
        )
        sheets = list_ctkm_sheet_names(wb_ctkm)
        return {
            "sheet_names": sheets,
            "suggested_sheet": sheets[0] if len(sheets) == 1 else next(
                (name for name in sheets if "tong hop" in name.lower() or "tổng hợp" in name.lower()),
                sheets[0] if sheets else None,
            ),
        }
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.post("/api/inspect-pog")
async def inspect_pog_file(
    pog_file: UploadFile = File(..., description="File Excel POG (.xlsx)"),
    _admin: str = Depends(require_admin),
):
    """Doc 1 lan file POG de lay snapshot month truoc khi chay pipeline."""
    if not pog_file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="pog_file phai la file .xlsx")

    tmp_path = _TMP_DIR / f"inspect_{uuid.uuid4().hex[:8]}_pog.xlsx"
    tmp_path.write_bytes(await _read_upload_limited(pog_file, _MAX_PIPELINE_BYTES, "File POG"))
    try:
        wb_pog = await asyncio.to_thread(
            _main_mod.L.load_workbook_raw, str(tmp_path), is_pog_file=True
        )
        return {
            "snapshot_month": wb_pog.pog_snapshot_month,
            "sheet_names": list(wb_pog.sheets.keys()),
        }
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.post("/api/preview-mapping")
async def preview_mapping_job(
    ctkm_file: UploadFile = File(..., description="File Excel CTKM (.xlsx)"),
    pog_file: UploadFile = File(..., description="File Excel POG (.xlsx)"),
    ctkm_sheet_name: str = Form(..., description="Ten sheet CTKM can review mapping"),
    manual_only: bool = Form(False, description="Chi doc cot, khong goi Gemini"),
    _admin: str = Depends(require_admin),
):
    """Tra ve cot va mapping goi y; Gemini loi van cho phep mapping thu cong."""
    if not ctkm_file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="ctkm_file phai la file .xlsx")
    if not pog_file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="pog_file phai la file .xlsx")

    job_id = uuid.uuid4().hex[:8]
    job_dir = _TMP_DIR / f"preview_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    ctkm_path = job_dir / "ctkm.xlsx"
    pog_path = job_dir / "pog.xlsx"
    ctkm_content, pog_content = await asyncio.gather(
        _read_upload_limited(ctkm_file, _MAX_PIPELINE_BYTES, "File CTKM"),
        _read_upload_limited(pog_file, _MAX_PIPELINE_BYTES, "File POG"),
    )
    ctkm_path.write_bytes(ctkm_content)
    pog_path.write_bytes(pog_content)

    try:
        wb_ctkm, wb_pog = await asyncio.gather(
            asyncio.to_thread(_main_mod.L.load_workbook_raw, str(ctkm_path), is_pog_file=False),
            asyncio.to_thread(_main_mod.L.load_workbook_raw, str(pog_path), is_pog_file=True),
        )
        if ctkm_sheet_name not in wb_ctkm.sheets:
            raise HTTPException(status_code=422, detail=f"Khong tim thay sheet CTKM '{ctkm_sheet_name}'")
        ctkm_sheet = wb_ctkm.sheets[ctkm_sheet_name]
        pog_sheet_name = next(iter(wb_pog.sheets)) if wb_pog.sheets else None
        if not pog_sheet_name:
            raise HTTPException(status_code=422, detail="File POG khong co sheet nao co du lieu.")

        stored_preset = _get_saved_preset(list(ctkm_sheet.df.columns), list(wb_pog.sheets[pog_sheet_name].df.columns))

        def mapping_preview_or_manual(sheet_name, df, schema_section, preset_mapping):
            columns = [str(col) for col in df.columns]
            if preset_mapping:
                mapping = _main_mod._validate_manual_mapping(preset_mapping, df, schema_section)
                return {
                    "mapping": mapping,
                    "confidence": {source: 1.0 for source in mapping},
                    "unmapped": [col for col in columns if col not in mapping],
                    "source": "saved-preset",
                }, None

            if manual_only:
                return {
                    "mapping": {},
                    "confidence": {},
                    "unmapped": columns,
                    "source": "manual",
                }, None

            logs = []
            try:
                _enforce_gemini_cooldown()
                preview_mapping(sheet_name, df, schema_section, logs)
                result = logs[-1] if logs else {}
                return result, None
            except Exception as exc:
                # Preview must remain usable when Gemini is unavailable. Do not
                # expose credentials or a full upstream response to the browser.
                return {
                    "mapping": {},
                    "confidence": {},
                    "unmapped": columns,
                    "source": "manual-fallback",
                }, f"{type(exc).__name__}: {exc}"

        ctkm_result, ctkm_mapping_error = mapping_preview_or_manual(
            ctkm_sheet_name,
            ctkm_sheet.df,
            _main_mod.SCHEMA["fact_fields"],
            stored_preset.get("ctkm_mapping"),
        )
        pog_result, pog_mapping_error = mapping_preview_or_manual(
            pog_sheet_name,
            wb_pog.sheets[pog_sheet_name].df,
            _main_mod.SCHEMA["pog_fields"],
            stored_preset.get("pog_mapping"),
        )

        return {
            "ctkm_sheet_name": ctkm_sheet_name,
            "pog_sheet_name": pog_sheet_name,
            "ctkm_mapping": ctkm_result,
            "pog_mapping": pog_result,
            "mapping_warnings": [
                message for message in (
                    f"CTKM: {ctkm_mapping_error}" if ctkm_mapping_error else None,
                    f"POG: {pog_mapping_error}" if pog_mapping_error else None,
                ) if message
            ],
            "stored_preset": stored_preset,
            "ctkm_preview": {
                "columns": list(ctkm_sheet.df.columns),
            },
            "pog_preview": {
                "columns": list(wb_pog.sheets[pog_sheet_name].df.columns),
                "snapshot_month": wb_pog.pog_snapshot_month,
            },
        }
    finally:
        try:
            for item in job_dir.iterdir():
                item.unlink(missing_ok=True)
            job_dir.rmdir()
        except Exception:
            pass


@app.post("/api/run")
async def run_job(
    ctkm_file:  UploadFile = File(..., description="File Excel CTKM (.xlsx)"),
    pog_file:   UploadFile = File(..., description="File Excel POG (.xlsx)"),
    month:      str        = Form(..., description="Thang bao cao, dang YYYY-MM (vd 2026-05)"),
    strict_month: bool     = Form(False, description="Dung pipeline neu lech thang POG/CTKM"),
    ctkm_sheet_name: Optional[str] = Form(None, description="Ten sheet CTKM tong hop can xu ly"),
    ctkm_mapping_override: Optional[str] = Form(None, description="JSON mapping override cho sheet CTKM"),
    pog_mapping_override: Optional[str] = Form(None, description="JSON mapping override cho sheet POG"),
    selected_output_columns: Optional[str] = Form(None, description="JSON array cac cot output can giu lai"),
    mapping_mode: str = Form("auto", description="auto hoac saved_only"),
    _admin: str = Depends(require_admin),
):
    """
    Upload 2 file Excel + chon thang -> chay pipeline -> tra ket qua.
    Tra ve job_id de frontend dung goi /api/download va /api/preview.
    """
    # Validate month format
    import re
    if not re.match(r"^\d{4}-\d{2}$", month):
        raise HTTPException(status_code=422, detail="month phai co dang YYYY-MM, vd 2026-05")

    if not ctkm_file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="ctkm_file phai la file .xlsx")
    if not pog_file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="pog_file phai la file .xlsx")
    if mapping_mode not in {"auto", "saved_only"}:
        raise HTTPException(status_code=422, detail="mapping_mode phai la auto hoac saved_only")
    if mapping_mode == "auto":
        _enforce_gemini_cooldown()

    # Luu file upload tam thoi
    job_id   = str(uuid.uuid4())[:8]
    job_dir  = _TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    ctkm_path = job_dir / "ctkm.xlsx"
    pog_path  = job_dir / "pog.xlsx"
    out_path  = _OUT_DIR / f"tong_hop_ctkm_{month}_{job_id}.xlsx"

    ctkm_content, pog_content = await asyncio.gather(
        _read_upload_limited(ctkm_file, _MAX_PIPELINE_BYTES, "File CTKM"),
        _read_upload_limited(pog_file, _MAX_PIPELINE_BYTES, "File POG"),
    )
    ctkm_path.write_bytes(ctkm_content)
    pog_path.write_bytes(pog_content)

    try:
        await asyncio.to_thread(_heavy_queue.acquire, job_id, "ctkm")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Chay pipeline
    try:
        parsed_ctkm_override = json.loads(ctkm_mapping_override) if ctkm_mapping_override else None
        parsed_pog_override = json.loads(pog_mapping_override) if pog_mapping_override else None
        parsed_output_columns = json.loads(selected_output_columns) if selected_output_columns else None

        wb_ctkm, wb_pog = await asyncio.gather(
            asyncio.to_thread(_main_mod.L.load_workbook_raw, str(ctkm_path), is_pog_file=False),
            asyncio.to_thread(_main_mod.L.load_workbook_raw, str(pog_path), is_pog_file=True),
        )
        primary_ctkm_name, primary_ctkm_sheet = _main_mod._select_primary_ctkm_sheet(wb_ctkm, ctkm_sheet_name)
        pog_sheet_name = next(iter(wb_pog.sheets)) if wb_pog.sheets else None
        if pog_sheet_name:
            saved_preset = _get_saved_preset(
                list(primary_ctkm_sheet.df.columns),
                list(wb_pog.sheets[pog_sheet_name].df.columns),
            )
            if parsed_ctkm_override is None:
                parsed_ctkm_override = saved_preset.get("ctkm_mapping")
            if parsed_pog_override is None:
                parsed_pog_override = saved_preset.get("pog_mapping")
            if parsed_output_columns is None:
                parsed_output_columns = saved_preset.get("output_columns")
            if mapping_mode == "saved_only" and (not parsed_ctkm_override or not parsed_pog_override):
                raise ValueError(
                    "Chưa có mapping đã lưu cho cấu trúc hai file này. Hãy dùng chế độ tự động và lưu mapping sau khi duyệt."
                )
            _store_preset(
                list(primary_ctkm_sheet.df.columns),
                list(wb_pog.sheets[pog_sheet_name].df.columns),
                ctkm_mapping=parsed_ctkm_override,
                pog_mapping=parsed_pog_override,
                output_columns=parsed_output_columns,
            )

        result = await asyncio.to_thread(
            run_pipeline,
            ctkm_filepath=str(ctkm_path),
            pog_filepath=str(pog_path),
            target_month=month,
            output_path=str(out_path),
            fail_on_month_mismatch=strict_month,
            ctkm_sheet_name=ctkm_sheet_name,
            ctkm_mapping_override=parsed_ctkm_override,
            pog_mapping_override=parsed_pog_override,
            selected_output_columns=parsed_output_columns,
        )
    except Exception as e:
        # Phan loai loi de frontend hien thi thong bao phu hop
        err_cls = type(e).__name__

        # 429 Rate Limit — nguoi dung can cho, khong phai loi server
        if "GeminiRateLimitError" in err_cls or (
            GeminiRateLimitError and isinstance(e, GeminiRateLimitError)
        ):
            category = getattr(e, "category", "unknown")
            retry_after = max(60, int(getattr(e, "retry_after", 0) or 0))
            _set_gemini_cooldown(retry_after)
            suggestions = {
                "daily_quota": "Quota theo ngày của Gemini đã hết. Hãy dùng mapping đã lưu, chờ quota làm mới hoặc bật billing.",
                "token_quota": "Quota token của Gemini đã hết. Hãy giảm số cột/mẫu dữ liệu, chờ vài phút hoặc bật billing.",
                "rate_quota": "Quota theo phút của Gemini đã hết. Không chạy song song; chờ vài phút rồi thử lại.",
                "service_overload": "Gemini đang quá tải. Hãy chờ vài phút rồi thử lại; không cần sửa file dữ liệu.",
                "unknown": "Gemini từ chối yêu cầu do giới hạn tạm thời. Hãy chờ vài phút hoặc dùng mapping đã lưu.",
            }
            raise HTTPException(
                status_code=429,
                detail={
                    "type": "rate_limit",
                    "category": category,
                    "quota": getattr(e, "quota", None),
                    "request_id": getattr(e, "request_id", None),
                    "message": str(e),
                    "suggestion": suggestions.get(category, suggestions["unknown"]),
                },
                headers={"Retry-After": str(retry_after)},
            )

        # Loi API key chua cau hinh
        if "GeminiMappingError" in err_cls and "your_gemini_api_key" in str(e).lower():
            raise HTTPException(
                status_code=400,
                detail=(
                    "GEMINI_API_KEY chua duoc cau hinh. "
                    "Mo file .env va dien API key that tu Google AI Studio."
                ),
            )

        # Loi nghiep vu (thang bao cao sai format, file rong...)
        if isinstance(e, ValueError):
            raise HTTPException(status_code=400, detail=str(e))

        # Loi bat ngo khac
        raise HTTPException(status_code=500, detail=f"Loi pipeline [{err_cls}]: {e}")
    finally:
        _heavy_queue.release(job_id)

    # Luu job info
    _jobs[job_id] = {
        "job_id":      job_id,
        "month":       month,
        "output_path": str(out_path),
        "output_name": out_path.name,
        "summary":     result.summary,
        "warnings":    result.warnings,
        "created_at":  datetime.now().isoformat(),
    }

    return {
        "job_id":   job_id,
        "summary":  result.summary,
        "warnings": result.warnings,
        "has_output": out_path.exists(),
    }


@app.get("/api/download/{job_id}")
def download_result(job_id: str, _admin: str = Depends(require_admin)):
    """Tra ve file Excel ket qua de frontend trigger download."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Khong tim thay job '{job_id}'")
    path = Path(job["output_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File ket qua khong ton tai.")
    return FileResponse(
        path=str(path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=job["output_name"],
    )


@app.get("/api/preview/{job_id}")
def preview_result(job_id: str, rows: int = 50, _admin: str = Depends(require_admin)):
    """
    Doc N dong dau cua moi sheet trong file Excel ket qua, tra ve JSON.
    Frontend dung de hien thi bang preview ma khong can download file.
    """
    import openpyxl
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Khong tim thay job '{job_id}'")
    path = Path(job["output_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File ket qua khong ton tai.")

    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        sheets_data = {}
        for sn in wb.sheetnames:
            ws  = wb[sn]
            all_rows = list(ws.iter_rows(values_only=True))
            if not all_rows:
                sheets_data[sn] = {"headers": [], "rows": [], "total_rows": 0}
                continue
            headers = [str(h) if h is not None else "" for h in all_rows[0]]
            data_rows = []
            for row in all_rows[1: rows + 1]:
                data_rows.append([
                    str(v) if v is not None else ""
                    for v in row
                ])
            sheets_data[sn] = {
                "headers":    headers,
                "rows":       data_rows,
                "total_rows": max(0, len(all_rows) - 1),
            }
        wb.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Loi doc file ket qua: {e}")

    return {
        "job_id":  job_id,
        "month":   job["month"],
        "summary": job["summary"],
        "sheets":  sheets_data,
    }


@app.get("/api/jobs")
def list_jobs(_admin: str = Depends(require_admin)):
    """Lich su cac job da chay (trong session hien tai)."""
    return sorted(_jobs.values(), key=lambda x: x["created_at"], reverse=True)


# Serve the production frontend from the API's origin. This mount stays last so
# API routes take precedence and Vite's index handles client-side navigation.
_FRONTEND_DIST = _ROOT / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run("backend.main_api:app", host="0.0.0.0", port=8000, reload=True)
