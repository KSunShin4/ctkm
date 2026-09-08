# -*- coding: utf-8 -*-
"""Fast manual shelf-check mode for store staff.

The manual shelf workflow is store-facing, isolated from Admin scanner context,
and includes both active Gắn-tem tasks and all due Tháo-tem tasks. POG is the
primary work unit; only very large POG groups are split by location to avoid
forcing staff through many tiny technical shelf cards.
"""
from __future__ import annotations

from io import BytesIO
import os
import re
import secrets
import threading
import time

from fastapi import File, HTTPException, UploadFile

from backend.tag_audit_progress_contract import (
    shelf_context_id,
    shelf_task_rows,
    store_scope_id,
    workbook_scope_id,
)


_SESSION_LOCK = threading.RLock()
_SESSIONS: dict[str, dict] = {}
_SESSION_TTL_SECONDS = max(900, int(os.getenv("TAG_AUDIT_SHELF_SESSION_TTL_SECONDS", "28800")))
_MAX_SESSIONS = max(2, int(os.getenv("TAG_AUDIT_SHELF_MAX_SESSIONS", "16")))
_MAX_UPLOAD_BYTES = max(1, int(os.getenv("TAG_AUDIT_SHELF_MAX_MB", "15"))) * 1024 * 1024
_MAX_GROUP_ACTIONS = max(10, int(os.getenv("TAG_AUDIT_SHELF_MAX_GROUP_ACTIONS", "30")))


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


def _natural_key(value) -> tuple:
    parts = re.split(r"(\d+)", str(value or "").strip().lower())
    return tuple(int(part) if part.isdigit() else part for part in parts)


def _group_identity(item: dict, pog_counts: dict[str, int], max_group_actions: int) -> tuple[str, str, str]:
    pog = str(item.get("pog_code") or "").strip()
    location = str(item.get("location_id") or "").strip()
    if pog:
        if pog_counts.get(pog, 0) > max_group_actions and location:
            return f"POG::{pog}::LOC::{location}", f"{pog} · {location}", "pog_location"
        return f"POG::{pog}", pog, "pog"
    if location:
        return f"LOC::{location}", location, "location"
    return "__NO_LOCATION__", "Chưa có vị trí kệ", "unknown"


def _decorate_items(items: list[dict], max_group_actions: int = _MAX_GROUP_ACTIONS) -> list[dict]:
    pog_counts: dict[str, int] = {}
    for item in items:
        pog = str(item.get("pog_code") or "").strip()
        if pog:
            pog_counts[pog] = pog_counts.get(pog, 0) + 1

    decorated: list[dict] = []
    for item in items:
        shelf_key, shelf_label, group_mode = _group_identity(item, pog_counts, max_group_actions)
        row = dict(item)
        row["shelf_key"] = shelf_key
        row["shelf_label"] = shelf_label
        row["shelf_group_mode"] = group_mode
        row["location_label"] = str(item.get("location_id") or "").strip()
        decorated.append(row)

    # Physical walk order: group -> location -> facing -> SKU -> campaign/action.
    # Same SKU/action variants therefore stay adjacent instead of sending staff
    # back to the same product after several unrelated items.
    decorated.sort(
        key=lambda item: (
            _natural_key(item.get("shelf_label")),
            _natural_key(item.get("location_id")),
            _natural_key(item.get("facing")),
            str(item.get("item_id") or "").strip().upper(),
            0 if item.get("expected_action") == "thao_tem" else 1,
            str(item.get("campaign_name") or ""),
            str(item.get("task_key") or ""),
        )
    )
    return decorated


def _build_shelves(items: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    order: list[str] = []
    sku_sets: dict[str, set[str]] = {}
    location_sets: dict[str, set[str]] = {}

    for item in items:
        key = str(item.get("shelf_key") or "__NO_LOCATION__")
        if key not in grouped:
            grouped[key] = {
                "shelf_key": key,
                "shelf_label": item.get("shelf_label") or "Chưa có vị trí kệ",
                "shelf_group_mode": item.get("shelf_group_mode") or "unknown",
                "pog_code": item.get("pog_code"),
                "location_id": item.get("location_id") if item.get("shelf_group_mode") != "pog" else None,
                "action_count": 0,
                "attach_count": 0,
                "remove_count": 0,
                "sku_count": 0,
                "location_count": 0,
                "locations": [],
            }
            sku_sets[key] = set()
            location_sets[key] = set()
            order.append(key)
        grouped[key]["action_count"] += 1
        if item.get("expected_action") == "thao_tem":
            grouped[key]["remove_count"] += 1
        else:
            grouped[key]["attach_count"] += 1
        item_id = str(item.get("item_id") or "").strip()
        if item_id:
            sku_sets[key].add(item_id)
        location = str(item.get("location_id") or "").strip()
        if location:
            location_sets[key].add(location)

    for key in order:
        grouped[key]["sku_count"] = len(sku_sets[key])
        locations = sorted(location_sets[key], key=_natural_key)
        grouped[key]["locations"] = locations
        grouped[key]["location_count"] = len(locations)
    return [grouped[key] for key in order]


def _session_payload(session_id: str, session: dict) -> dict:
    items = session["items"]
    return {
        "session_id": session_id,
        "context_id": session["context_id"],
        "workbook_scope_id": session["workbook_scope_id"],
        "store_scope_id": session["store_scope_id"],
        "created_at": session["created_at"],
        "expires_in_seconds": _SESSION_TTL_SECONDS,
        "action_count": len(items),
        "attach_count": sum(1 for item in items if item.get("expected_action") == "gan_tem"),
        "remove_count": sum(1 for item in items if item.get("expected_action") == "thao_tem"),
        "shelf_count": len(session["shelves"]),
        "shelves": session["shelves"],
        "items": items,
        "progress_scope": "gan_and_thao",
        "max_group_actions": _MAX_GROUP_ACTIONS,
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
            items = _decorate_items(shelf_task_rows(tag_audit_module, rows))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Workbook kiểm kệ không hợp lệ: {exc}") from exc
        if not items:
            raise HTTPException(status_code=422, detail="Không tìm thấy action Gắn tem hoặc Tháo tem cần xử lý trong workbook")

        now = time.time()
        _clean_sessions(now)
        session_id = "shelf_" + secrets.token_urlsafe(18)
        session = {
            "context_id": shelf_context_id(tag_audit_module, rows),
            "workbook_scope_id": workbook_scope_id(tag_audit_module, rows),
            "store_scope_id": store_scope_id(tag_audit_module, rows),
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
