# -*- coding: utf-8 -*-
"""Align expiration input validation with the UI and shared API conventions."""
from __future__ import annotations

import asyncio
from datetime import datetime
import re

from fastapi import File, Form, HTTPException, UploadFile


_ENTRY_DATE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _valid_entry_date(value: str) -> bool:
    text = str(value or "").strip()
    if not _ENTRY_DATE.fullmatch(text):
        return False
    try:
        datetime.strptime(text, "%d/%m/%Y")
        return True
    except ValueError:
        return False


def _replace_route(core_module, path: str, method: str, endpoint) -> None:
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
    raise RuntimeError(f"Không tìm thấy route {method} {path} để cài expiration contract")


def install_expiration_api_contract(core_module) -> None:
    if getattr(core_module.app.state, "expiration_api_contract_v1", False):
        return

    expiration_mod = core_module._expiration_mod
    original_check_entries = expiration_mod.check_entries

    def strict_check_entries(frame, raw_entries: str):
        results = original_check_entries(frame, raw_entries)
        for result in results:
            raw = str(result.get("input") or "")
            parts = [part.strip() for part in raw.split(";")]
            # Leave structural errors to the original checker. Tighten only the
            # date field that the UI/documentation explicitly defines as DD/MM/YYYY.
            if len(parts) != 3 or not all(parts):
                continue
            if _valid_entry_date(parts[2]):
                continue
            result["status"] = "invalid"
            result["message"] = "Hạn dùng phải có dạng DD/MM/YYYY"
            result["exp_date"] = parts[2]
            result["normalized"] = f"{parts[0].upper()};{parts[1]};{parts[2]}"
            result.pop("related_rows", None)
            result.pop("on_hand", None)
        return results

    expiration_mod.check_entries = strict_check_entries

    async def check_expiration(
        expiration_file: UploadFile = File(...),
        entries: str = Form(...),
    ):
        # This workflow intentionally remains public; only CTKM/Tem R require
        # admin auth in the current product. Harden validation without changing
        # that access model.
        if not expiration_file.filename or not expiration_file.filename.lower().endswith(".xlsx"):
            raise HTTPException(status_code=422, detail="expiration_file phải là file .xlsx")

        entry_lines = [line for line in str(entries or "").splitlines() if line.strip()]
        if not entry_lines:
            raise HTTPException(
                status_code=422,
                detail="Hãy nhập ít nhất một dòng theo mẫu MÃ_P;SỐ_LÔ;DD/MM/YYYY.",
            )
        max_entries = int(getattr(expiration_mod, "MAX_EXPIRATION_ROWS", 250_000))
        if len(entry_lines) > max_entries:
            raise HTTPException(
                status_code=422,
                detail=f"Danh sách kiểm tra vượt quá {max_entries:,} dòng.",
            )

        content = await core_module._read_upload_limited(
            expiration_file, core_module._MAX_EXPIRATION_BYTES, "File hạn dùng"
        )

        # Do not block the shared thread pool waiting on a threading.Semaphore.
        # The endpoint is intentionally public, so excess concurrent requests must
        # fail fast instead of occupying all to_thread workers used by other APIs.
        acquired = core_module._expiration_slots.acquire(blocking=False)
        if not acquired:
            raise HTTPException(
                status_code=503,
                detail="Hệ thống đang xử lý nhiều yêu cầu hạn dùng. Hãy thử lại sau ít giây.",
                headers={"Retry-After": "2"},
            )
        try:
            frame, sheet_name, cache_hit = await asyncio.to_thread(
                core_module._load_expiration_cached, content
            )
            if frame.empty or "ITEMID" not in frame.columns or not frame["ITEMID"].astype(str).str.strip().ne("").any():
                raise ValueError(
                    f"Sheet hạn dùng '{sheet_name}' không có dòng sản phẩm ITEMID để đối chiếu."
                )
            results = await asyncio.to_thread(expiration_mod.check_entries, frame, entries)
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Lỗi đọc file hạn dùng: {exc}") from exc
        finally:
            core_module._expiration_slots.release()

        matched = sum(row.get("status") == "matched" for row in results)
        return {
            "sheet_name": sheet_name,
            "source_rows": len(frame),
            "total": len(results),
            "matched": matched,
            "unmatched": len(results) - matched,
            "cache_hit": cache_hit,
            "results": results,
        }

    _replace_route(core_module, "/api/check-expiration", "POST", check_expiration)
    core_module.check_expiration = check_expiration
    core_module.app.state.expiration_api_contract_v1 = True
