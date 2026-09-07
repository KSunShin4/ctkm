# -*- coding: utf-8 -*-
"""Fast manual shelf-check mode for store staff.

This contract deliberately does not reuse the admin/global tag-audit context.
A store user uploads an already-generated CTKM action workbook into an isolated,
short-lived session and receives only the current Gắn-tem checklist grouped by
POG/location. Progress and fail reasons stay device-local in the browser.

The routes are intentionally not protected by the admin dependency: this is an
operational store workflow, not an administration workflow. Isolation, bounded
upload size, bounded session count and TTL prevent one staff session from
changing the admin scanner context or another staff session.
"""
from __future__ import annotations

from io import BytesIO
import os
import secrets
import threading
import time

from fastapi import File, HTTPException, UploadFile

from backend.tag_audit_progress_contract import checklist_rows, context_id


_SESSION_LOCK = threading.RLock()
_SESSIONS: dict[str, dict] = {}
_SESSION_TTL_SECONDS = max(900, int(os.getenv("TAG_AUDIT_SHELF_SESSION_TTL_SECONDS", "28800")))
_MAX_SESSIONS = max(2, int(os.getenv("TAG_AUDIT_SHELF_MAX_SESSIONS", "16")))
_MAX_UPLOAD_BYTES = max(1, int(os.getenv("TAG_AUDIT_SHELF_MAX_MB", "15"))) * 1024 * 1024


def _clean_sessions(now: float | None = None) -> None:
    current = float(now if now is not None else time.time())
    cutoff = current - _SESSION_TTL_SECONDS
    with _SESSION_LOCK:
        expired = [key for key, value in _SESSIONS.items() if float(value.get("touched_at") or 0) < cutoff]
        for key in expired:
            _SESSIONS.pop(key, None)
        if len(_SESSIONS) <= _MAX_SESSIONS:
            return
        oldest = sorted(_SESSIONS.items(), key=lambda pair: float(pair[1].get("touched_at") or 0))
        for key, _value in oldest[: max(0, len(_SESSIONS) - _MAX_SESSIONS)]:
            _SESSIONS.pop(key, None)


def _shelf_identity(item: dict) -> tuple[str, str]:
    pog = str(item.get("pog_code") or "").strip()
    location = str(item.get("location_id") or "").strip()
    if pog and location:
        return f"{pog}::{location}", f"{pog} · {location}"
    if pog:
        return f"{pog}::__NO_LOCATION__", pog
    if location:
        return f"__NO_POG__::{location}", location
    return "__NO_LOCATION__", "Chưa có vị trí kệ"


def _decorate_items(items: list[dict]) -> list[dict]:
    decorated: list[dict] = []
    for item in items:
        shelf_key, shelf_label = _shelf_identity(item)
        row = dict(item)
        row["shelf_key"] = shelf_key
        row["shelf_label"] = shelf_label
        decorated.append(row)
    return decorated


def _build_shelves(items: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    order: list[str] = []
    for item in items:
        key = str(item.get("shelf_key") or "__NO_LOCATION__")
        if key not in grouped:
            grouped[key] = {
                "shelf_key": key,
                "shelf_label": item.get("shelf_label") or "Chưa có vị trí kệ",
                "pog_code": item.get("pog_code"),
                "location_id": item.get("location_id"),
                "action_count": 0,
                "sku_count": 0,
            }
            order.append(key)
        grouped[key]["action_count"] += 1

    sku_sets: dict[str, set[str]] = {key: set() for key in grouped}
    for item in items:
        sku_sets[str(item.get("shelf_key") or "__NO_LOCATION__")].add(str(item.get("item_id") or ""))
    for key in order:
        grouped[key]["sku_count"] = len({sku for sku in sku_sets[key] if sku})
    return [grouped[key] for key in order]


def _session_payload(session_id: str, session: dict) -> dict:
    items = session["items"]
    return {
        "session_id": session_id,
        "context_id": session["context_id"],
        "created_at": session["created_at"],
        "expires_in_seconds": _SESSION_TTL_SECONDS,
        "action_count": len(items),
        "shelf_count": len(session["shelves"]),
        "shelves": session["shelves"],
        "items": items,
        "progress_scope": "gan_tem_only",
    }


def _get_session(session_id: str) -> dict:
    _clean_sessions()
    key = str(session_id or "").strip()
    with _SESSION_LOCK:
        session = _SESSIONS.get(key)
        if session is None:
            raise HTTPException(status_code=404, detail="Phiên kiểm kệ đã hết hạn hoặc không tồn tại")
        session["touched_at"] = time.time()
        return dict(session)


def install_tag_audit_shelf_contract(tag_audit_module, core_module) -> None:
    if getattr(core_module.app.state, "tag_audit_shelf_contract_v1", False):
        return

    async def create_shelf_session(workbook: UploadFile = File(...)):
        filename = str(workbook.filename or "")
        if not filename.lower().endswith(".xlsx"):
            raise HTTPException(status_code=422, detail="File kiểm kệ phải là .xlsx")
        content = await core_module._read_upload_limited(
            workbook,
            min(_MAX_UPLOAD_BYTES, core_module._MAX_PIPELINE_BYTES),
            "Workbook kiểm kệ",
        )
        try:
            rows = await core_module.asyncio.to_thread(
                tag_audit_module._parse_action_workbook, BytesIO(content)
            )
            items = _decorate_items(checklist_rows(tag_audit_module, rows))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Workbook kiểm kệ không hợp lệ: {exc}") from exc
        if not items:
            raise HTTPException(status_code=422, detail="Không tìm thấy action Gắn tem cần kiểm trong workbook")

        now = time.time()
        _clean_sessions(now)
        session_id = "shelf_" + secrets.token_urlsafe(18)
        session = {
            "context_id": context_id(tag_audit_module, rows),
            "items": items,
            "shelves": _build_shelves(items),
            "created_at": core_module.datetime.now().isoformat(),
            "touched_at": now,
        }
        with _SESSION_LOCK:
            _SESSIONS[session_id] = session
            _clean_sessions(now)
        return _session_payload(session_id, session)

    async def read_shelf_session(session_id: str):
        session = _get_session(session_id)
        return _session_payload(session_id, session)

    tag_audit_module._insert_api_route_before_frontend(
        core_module,
        "/api/tag-audit/shelf/session",
        create_shelf_session,
        ["POST"],
        response_model=None,
    )
    tag_audit_module._insert_api_route_before_frontend(
        core_module,
        "/api/tag-audit/shelf/session/{session_id}",
        read_shelf_session,
        ["GET"],
        response_model=None,
    )
    core_module.create_tag_audit_shelf_session = create_shelf_session
    core_module.read_tag_audit_shelf_session = read_shelf_session
    core_module.app.state.tag_audit_shelf_contract_v1 = True
