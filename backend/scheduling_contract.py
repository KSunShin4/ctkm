# -*- coding: utf-8 -*-
"""Additive staff-scheduling API and exact-template Excel export."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import uuid

from fastapi import Body, Depends, HTTPException
from fastapi.responses import FileResponse
from openpyxl import load_workbook

from modules.scheduling_engine import (
    SchedulingError,
    generate_schedule,
    normalize_config,
    public_config,
    validate_schedule,
)


_STORE_LOCK = threading.RLock()
_STORE_VERSION = 2
_GCS_OBJECT_DEFAULT = "ctkm/schedules.json"
_TEMPLATE_NAME = "1885_Lich_lam_viec_template.xlsx"
_SAFE_FILENAME = re.compile(r"[^0-9A-Za-zÀ-ỹ._-]+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _storage_info(core_module) -> dict:
    bucket = os.getenv("SCHEDULE_GCS_BUCKET", "").strip()
    if bucket:
        return {
            "mode": "gcs",
            "durable": True,
            "bucket": bucket,
            "object": os.getenv("SCHEDULE_GCS_OBJECT", _GCS_OBJECT_DEFAULT).strip() or _GCS_OBJECT_DEFAULT,
        }
    configured_path = os.getenv("SCHEDULE_STORE_PATH", "").strip()
    path = Path(configured_path) if configured_path else Path(core_module._ROOT) / "logs" / "schedules.json"
    durable = os.getenv("SCHEDULE_STORE_DURABLE", "").strip().lower() in {"1", "true", "yes"}
    return {
        "mode": "local",
        "durable": durable,
        "path": str(path),
        "warning": None if durable else "Schedule storage đang dùng filesystem local/ephemeral; restart hoặc redeploy có thể làm mất lịch.",
    }


def _store_path(core_module) -> Path:
    info = _storage_info(core_module)
    if info["mode"] != "local":
        raise RuntimeError("_store_path chỉ dùng cho local schedule storage")
    path = Path(info["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _export_dir(core_module) -> Path:
    path = Path(core_module._ROOT) / "logs" / "schedule_exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _template_path() -> Path:
    return Path(__file__).resolve().parent / "templates" / _TEMPLATE_NAME


def _empty_store() -> dict:
    return {"version": _STORE_VERSION, "schedules": {}}


def _normalize_store(raw: object) -> dict:
    schedules = raw.get("schedules") if isinstance(raw, dict) else None
    return {"version": _STORE_VERSION, "schedules": schedules if isinstance(schedules, dict) else {}}


def _load_store_with_generation(core_module) -> tuple[dict, int | None]:
    info = _storage_info(core_module)
    if info["mode"] == "gcs":
        try:
            from google.cloud import storage
            from google.api_core.exceptions import NotFound
        except ImportError as exc:
            raise RuntimeError("Thiếu google-cloud-storage cho SCHEDULE_GCS_BUCKET") from exc
        client = storage.Client()
        blob = client.bucket(info["bucket"]).blob(info["object"])
        try:
            blob.reload()
            generation = int(blob.generation or 0)
            raw = json.loads(blob.download_as_text(encoding="utf-8"))
            return _normalize_store(raw), generation
        except NotFound:
            return _empty_store(), 0
        except (ValueError, TypeError, json.JSONDecodeError):
            return _empty_store(), int(blob.generation or 0)

    path = _store_path(core_module)
    if not path.exists():
        return _empty_store(), None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return _empty_store(), None
    return _normalize_store(raw), None


def _load_store(core_module) -> dict:
    return _load_store_with_generation(core_module)[0]


def _save_store(core_module, data: dict, *, expected_generation: int | None = None) -> None:
    payload = {"version": _STORE_VERSION, "schedules": data.get("schedules", {})}
    info = _storage_info(core_module)
    if info["mode"] == "gcs":
        try:
            from google.cloud import storage
        except ImportError as exc:
            raise RuntimeError("Thiếu google-cloud-storage cho SCHEDULE_GCS_BUCKET") from exc
        blob = storage.Client().bucket(info["bucket"]).blob(info["object"])
        blob.upload_from_string(
            json.dumps(payload, ensure_ascii=False, indent=2),
            content_type="application/json; charset=utf-8",
            if_generation_match=0 if expected_generation in (None, 0) else expected_generation,
        )
        return

    path = _store_path(core_module)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _mutate_store(core_module, mutator):
    info = _storage_info(core_module)
    attempts = 4 if info["mode"] == "gcs" else 1
    with _STORE_LOCK:
        for attempt in range(attempts):
            store, generation = _load_store_with_generation(core_module)
            result = mutator(store)
            try:
                _save_store(core_module, store, expected_generation=generation)
                return result
            except Exception as exc:
                if info["mode"] != "gcs":
                    raise
                try:
                    from google.api_core.exceptions import PreconditionFailed
                except ImportError:
                    raise
                if isinstance(exc, PreconditionFailed) and attempt + 1 < attempts:
                    continue
                if isinstance(exc, PreconditionFailed):
                    raise HTTPException(status_code=409, detail="Lịch vừa được thay đổi ở phiên khác. Hãy tải lại rồi thử lại.") from exc
                raise
    raise HTTPException(status_code=409, detail="Không thể ghi lịch do xung đột cập nhật")


def _get_schedule(core_module, schedule_id: str) -> dict:
    with _STORE_LOCK:
        item = _load_store(core_module)["schedules"].get(schedule_id)
        if not isinstance(item, dict):
            raise HTTPException(status_code=404, detail="Không tìm thấy lịch")
        return deepcopy(item)


def _validation_payload(body: dict) -> tuple[dict, list[dict]]:
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Payload không hợp lệ")
    config = body.get("config") if isinstance(body.get("config"), dict) else body
    assignments = body.get("assignments")
    if not isinstance(assignments, list):
        raise HTTPException(status_code=422, detail="Thiếu assignments")
    return config, assignments


def _validate_or_422(config: dict, assignments: list[dict]) -> dict:
    try:
        normalized = normalize_config(config)
        validation = validate_schedule(normalized, assignments)
    except SchedulingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"normalized": normalized, "config": public_config(normalized), "validation": validation}


def _schedule_summary(item: dict) -> dict:
    config = item.get("config") or {}
    return {
        "id": item.get("id"),
        "store_label": config.get("store_label"),
        "week_start": config.get("week_start"),
        "week_end": config.get("week_end"),
        "status": item.get("status"),
        "version": item.get("version"),
        "validation_status": (item.get("validation") or {}).get("status"),
        "updated_at": item.get("updated_at"),
        "created_at": item.get("created_at"),
    }


def _display_name(employee: dict) -> str:
    name = employee.get("name", "")
    code = employee.get("staff_code", "")
    return f"{name} - {code}" if code else str(name)


def _export_filename(config: dict) -> str:
    start = datetime.fromisoformat(config["week_start"]).strftime("%d-%m")
    end = datetime.fromisoformat(config["week_end"]).strftime("%d_%m_%Y")
    label = _SAFE_FILENAME.sub("_", str(config.get("store_label") or "lich")).strip("_") or "lich"
    return f"{label}_Lich_lam_viec_{start}-{end}.xlsx"


def export_schedule_to_template(core_module, item: dict) -> tuple[Path, str]:
    template = _template_path()
    if not template.is_file():
        raise HTTPException(status_code=500, detail="Thiếu template Excel lịch làm việc 1885")
    config = item.get("config") or {}
    assignments = item.get("assignments") or []
    checked = _validate_or_422(config, assignments)
    validation = checked["validation"]
    if validation["status"] == "INVALID":
        raise HTTPException(status_code=409, detail={"message": "Lịch đang INVALID, không thể xuất Excel", "errors": validation["errors"]})
    normalized = checked["normalized"]
    employee_by_id = {employee["id"]: employee for employee in normalized["employees"]}
    order = {employee["id"]: index for index, employee in enumerate(normalized["employees"])}
    rows_by_day = {key: [] for key in [entry["date"] for entry in normalized["staffing"]]}
    for row in validation["assignments"]:
        rows_by_day[row["date"]].append(row)

    output_name = _export_filename(normalized)
    output_path = _export_dir(core_module) / f"{item['id']}_v{item.get('version', 1)}_{output_name}"
    workbook = load_workbook(template)
    try:
        ws = workbook[workbook.sheetnames[0]]
        start_date = datetime.fromisoformat(normalized["week_start"])
        end_date = datetime.fromisoformat(normalized["week_end"])
        ws["A1"] = f"Lịch làm việc {normalized.get('store_label') or '1885'} ngày {start_date.strftime('%d/%m/%y')} đến {end_date.strftime('%d/%m/%y')}"
        weekdays = ["thứ 2", "thứ 3", "thứ 4", "thứ 5", "thứ 6", "thứ 7", "chủ nhật"]
        day_keys = []
        for offset in range(7):
            current = start_date.date() + timedelta(days=offset)
            day_keys.append(current.isoformat())
            column = 2 + offset
            ws.cell(2, column).value = current.day
            ws.cell(3, column).value = weekdays[offset]
            for row_number in range(4, 11):
                ws.cell(row_number, column).value = None

        for offset, day_key in enumerate(day_keys):
            column = 2 + offset
            day_rows = sorted(rows_by_day.get(day_key, []), key=lambda row: order.get(row["employee_id"], 999))
            m06 = [row for row in day_rows if row["shift"] == "MORNING" and row.get("start_time") == "06:00"]
            m07 = [row for row in day_rows if row["shift"] == "MORNING" and row.get("start_time") == "07:00"]
            afternoon = [row for row in day_rows if row["shift"] == "AFTERNOON"]
            off = [row for row in day_rows if row["shift"] == "OFF"]
            if len(m06) > 2 or len(m07) > 1 or len(afternoon) > 3:
                raise HTTPException(status_code=409, detail=f"Lịch {day_key} vượt số dòng ca của template 1885")
            for index, row in enumerate(m06):
                ws.cell(4 + index, column).value = _display_name(employee_by_id[row["employee_id"]])
            if m07:
                ws.cell(6, column).value = _display_name(employee_by_id[m07[0]["employee_id"]])
            for index, row in enumerate(afternoon):
                ws.cell(7 + index, column).value = _display_name(employee_by_id[row["employee_id"]])
            if off:
                ws.cell(10, column).value = ", ".join(f"{employee_by_id[row['employee_id']]['name']} off" for row in off)

        workbook.save(output_path)
    finally:
        workbook.close()
    return output_path, output_name


def _insert_before_frontend(core_module, path: str, endpoint, methods: list[str], **kwargs) -> None:
    core_module.app.add_api_route(path, endpoint, methods=methods, **kwargs)
    routes = core_module.app.router.routes
    route = next(
        item for item in reversed(routes)
        if getattr(item, "path", None) == path
        and set(methods).issubset(getattr(item, "methods", set()) or set())
    )
    routes.remove(route)
    mount_index = next(
        (
            index for index, item in enumerate(routes)
            if item.__class__.__name__ == "Mount"
            and (getattr(item, "name", None) == "frontend" or getattr(item, "path", None) in {"", "/"})
        ),
        len(routes),
    )
    routes.insert(mount_index, route)


def install_scheduling_contract(core_module) -> None:
    if getattr(core_module.app.state, "staff_scheduling_contract_v1", False):
        return

    async def schedule_page():
        index_path = core_module._FRONTEND_DIST / "index.html"
        if not index_path.is_file():
            raise HTTPException(status_code=404, detail="Frontend xếp lịch chưa được build")
        return FileResponse(index_path)

    async def schedule_generate(payload: dict = Body(...), _admin: str = Depends(core_module.require_admin)):
        try:
            return generate_schedule(payload, variants=3)
        except SchedulingError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def schedule_validate(payload: dict = Body(...), _admin: str = Depends(core_module.require_admin)):
        config, assignments = _validation_payload(payload)
        checked = _validate_or_422(config, assignments)
        return checked["validation"]

    async def schedule_create(payload: dict = Body(...), _admin: str = Depends(core_module.require_admin)):
        config, assignments = _validation_payload(payload)
        checked = _validate_or_422(config, assignments)
        if checked["validation"]["status"] == "INVALID":
            raise HTTPException(status_code=409, detail={"message": "Không thể lưu lịch INVALID", "errors": checked["validation"]["errors"]})
        now = _utc_now()
        schedule_id = uuid.uuid4().hex
        item = {
            "id": schedule_id,
            "version": 1,
            "status": "DRAFT",
            "variant": str(payload.get("variant") or "manual"),
            "config": checked["config"],
            "assignments": checked["validation"]["assignments"],
            "validation": {key: checked["validation"][key] for key in ("status", "errors", "warnings", "metrics")},
            "created_at": now,
            "updated_at": now,
        }
        def mutate(store):
            store["schedules"][schedule_id] = item
            return deepcopy(item)
        return _mutate_store(core_module, mutate)

    async def schedule_update(schedule_id: str, payload: dict = Body(...), _admin: str = Depends(core_module.require_admin)):
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="Payload không hợp lệ")

        def mutate(store):
            current = store["schedules"].get(schedule_id)
            if not isinstance(current, dict):
                raise HTTPException(status_code=404, detail="Không tìm thấy lịch")
            expected_version = payload.get("expected_version")
            if expected_version is not None and int(expected_version) != int(current.get("version", 1)):
                raise HTTPException(status_code=409, detail="Lịch đã được cập nhật ở phiên khác. Hãy tải lại trước khi lưu.")
            if current.get("status") == "FINAL" and not bool(payload.get("reopen")):
                raise HTTPException(status_code=409, detail="Lịch FINAL phải được mở lại rõ ràng trước khi chỉnh sửa.")

            config = payload.get("config") if isinstance(payload.get("config"), dict) else current.get("config")
            assignments = payload.get("assignments") if isinstance(payload.get("assignments"), list) else current.get("assignments")
            checked = _validate_or_422(config, assignments)
            if checked["validation"]["status"] == "INVALID":
                raise HTTPException(status_code=409, detail={"message": "Không thể lưu lịch INVALID", "errors": checked["validation"]["errors"]})
            updated = deepcopy(current)
            updated["config"] = checked["config"]
            updated["assignments"] = checked["validation"]["assignments"]
            updated["validation"] = {key: checked["validation"][key] for key in ("status", "errors", "warnings", "metrics")}
            updated["variant"] = str(payload.get("variant") or current.get("variant") or "manual")
            updated["version"] = int(current.get("version", 1)) + 1
            updated["status"] = "DRAFT"
            updated["updated_at"] = _utc_now()
            store["schedules"][schedule_id] = updated
            return deepcopy(updated)

        return _mutate_store(core_module, mutate)

    async def schedule_finalize(schedule_id: str, payload: dict = Body(default={}), _admin: str = Depends(core_module.require_admin)):
        payload = payload if isinstance(payload, dict) else {}

        def mutate(store):
            current = store["schedules"].get(schedule_id)
            if not isinstance(current, dict):
                raise HTTPException(status_code=404, detail="Không tìm thấy lịch")
            expected_version = payload.get("expected_version")
            if expected_version is not None and int(expected_version) != int(current.get("version", 1)):
                raise HTTPException(status_code=409, detail="Lịch đã được cập nhật ở phiên khác. Hãy tải lại trước khi chốt.")
            checked = _validate_or_422(current.get("config") or {}, current.get("assignments") or [])
            if checked["validation"]["status"] == "INVALID":
                raise HTTPException(status_code=409, detail={"message": "Lịch INVALID nên chưa thể chốt", "errors": checked["validation"]["errors"]})
            updated = deepcopy(current)
            updated["validation"] = {key: checked["validation"][key] for key in ("status", "errors", "warnings", "metrics")}
            updated["status"] = "FINAL"
            updated["version"] = int(current.get("version", 1)) + 1
            updated["updated_at"] = _utc_now()
            store["schedules"][schedule_id] = updated
            return deepcopy(updated)

        return _mutate_store(core_module, mutate)

    async def schedule_get(schedule_id: str, _admin: str = Depends(core_module.require_admin)):
        return _get_schedule(core_module, schedule_id)

    async def schedule_list(_admin: str = Depends(core_module.require_admin)):
        with _STORE_LOCK:
            values = list(_load_store(core_module)["schedules"].values())
        return sorted((_schedule_summary(item) for item in values), key=lambda item: item.get("updated_at") or "", reverse=True)

    async def schedule_storage(_admin: str = Depends(core_module.require_admin)):
        return _storage_info(core_module)

    async def schedule_export(schedule_id: str, _admin: str = Depends(core_module.require_admin)):
        item = _get_schedule(core_module, schedule_id)
        path, filename = export_schedule_to_template(core_module, item)
        return FileResponse(
            path=str(path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=filename,
        )

    bindings = (
        ("/schedule", schedule_page, ["GET"], {"include_in_schema": False}),
        ("/api/schedules/generate", schedule_generate, ["POST"], {}),
        ("/api/schedules/validate", schedule_validate, ["POST"], {}),
        ("/api/schedules", schedule_create, ["POST"], {}),
        ("/api/schedules", schedule_list, ["GET"], {}),
        ("/api/schedules/storage", schedule_storage, ["GET"], {}),
        ("/api/schedules/{schedule_id}", schedule_get, ["GET"], {}),
        ("/api/schedules/{schedule_id}", schedule_update, ["PATCH"], {}),
        ("/api/schedules/{schedule_id}/finalize", schedule_finalize, ["POST"], {}),
        ("/api/schedules/{schedule_id}/export.xlsx", schedule_export, ["GET"], {}),
    )
    for path, endpoint, methods, kwargs in bindings:
        _insert_before_frontend(core_module, path, endpoint, methods, **kwargs)

    for name, value in {
        "schedule_page": schedule_page,
        "schedule_generate": schedule_generate,
        "schedule_validate": schedule_validate,
        "schedule_create": schedule_create,
        "schedule_update": schedule_update,
        "schedule_finalize": schedule_finalize,
        "schedule_get": schedule_get,
        "schedule_list": schedule_list,
        "schedule_storage": schedule_storage,
        "schedule_export": schedule_export,
    }.items():
        setattr(core_module, name, value)
    core_module.app.state.staff_scheduling_contract_v1 = True