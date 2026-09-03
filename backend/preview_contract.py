# -*- coding: utf-8 -*-
"""Preview the final workbook exactly as users can see it in Excel.

The exporter deliberately hides technical columns, metadata sheets and a few
legacy summary rows.  The historical API preview ignored those visibility flags
and also counted placeholder ``Ghi chu`` rows as real work.  This module keeps
preview semantics aligned with the final workbook without changing workbook data.
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter


_NON_TABULAR_SHEETS = {"HƯỚNG DẪN"}
_ACTION_SHEETS = {"Gắn tem", "Tháo tem", "Chờ gắn", "Cần review"}
_RECONCILIATION_SHEETS = {
    "Tong hop", "CTKM thieu vi tri ke", "POG cần kiểm tra",
    "POG không có CTKM", "POG cần review",
}
_AUDIT_SHEETS = {"Audit hành động", "Canh bao trung thoi gian"}
_CONFIRMATION_SHEETS = {"Xác nhận CTKM Clearance"}
_SUMMARY_SHEETS = {"Tom tat"}


def sheet_kind(sheet_name: str) -> str:
    if sheet_name in _ACTION_SHEETS:
        return "action"
    if sheet_name in _RECONCILIATION_SHEETS:
        return "reconciliation"
    if sheet_name in _AUDIT_SHEETS:
        return "audit"
    if sheet_name in _CONFIRMATION_SHEETS:
        return "confirmation"
    if sheet_name in _SUMMARY_SHEETS:
        return "summary"
    return "data"


def _visible_column_indexes(ws) -> list[int]:
    indexes = []
    for index in range(1, (ws.max_column or 0) + 1):
        dimension = ws.column_dimensions.get(get_column_letter(index))
        if dimension is not None and bool(dimension.hidden):
            continue
        indexes.append(index)
    return indexes


def _visible_nonempty_rows(ws, column_indexes: list[int]):
    for row_index in range(2, (ws.max_row or 0) + 1):
        dimension = ws.row_dimensions.get(row_index)
        if dimension is not None and bool(dimension.hidden):
            continue
        values = [ws.cell(row=row_index, column=index).value for index in column_indexes]
        if not any(value is not None and str(value).strip() for value in values):
            continue
        yield values


def _is_empty_placeholder(headers: list[str], rows: list[list[object]]) -> bool:
    if len(headers) != 1 or headers[0].strip().lower() not in {"ghi chu", "ghi chú"}:
        return False
    if len(rows) != 1:
        return False
    value = "" if rows[0][0] is None else str(rows[0][0]).strip().lower()
    return value.startswith("không có") or value.startswith("khong co")


def build_visible_preview(path: str | Path, rows: int = 50) -> dict:
    """Return only visible, tabular workbook content.

    ``total_rows`` counts visible non-empty data rows.  Empty-sheet placeholders
    created by exporter ``_safe`` are reported as zero rows.  Hidden technical
    columns/rows and hidden metadata sheets are intentionally excluded.
    """
    limit = max(0, int(rows))
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=False)
    try:
        sheets = {}
        for sheet_name in workbook.sheetnames:
            ws = workbook[sheet_name]
            if ws.sheet_state != "visible" or sheet_name in _NON_TABULAR_SHEETS:
                continue

            column_indexes = _visible_column_indexes(ws)
            headers = [
                "" if ws.cell(row=1, column=index).value is None
                else str(ws.cell(row=1, column=index).value)
                for index in column_indexes
            ]
            raw_rows = list(_visible_nonempty_rows(ws, column_indexes))
            if _is_empty_placeholder(headers, raw_rows):
                total_rows = 0
                preview_rows = []
            else:
                total_rows = len(raw_rows)
                preview_rows = raw_rows[:limit]

            sheets[sheet_name] = {
                "headers": headers,
                "rows": [
                    ["" if value is None else str(value) for value in row]
                    for row in preview_rows
                ],
                "total_rows": total_rows,
                "sheet_kind": sheet_kind(sheet_name),
            }
        return {"sheets": sheets}
    finally:
        workbook.close()


def install_preview_contract(core_module) -> None:
    """Intercept only GET /api/preview/* and preserve the existing auth contract."""
    if getattr(core_module.app.state, "visible_preview_contract", False):
        return

    @core_module.app.middleware("http")
    async def visible_preview_middleware(request, call_next):
        prefix = "/api/preview/"
        if request.method != "GET" or not request.url.path.startswith(prefix):
            return await call_next(request)

        job_id = request.url.path[len(prefix):].strip("/")
        if not job_id or "/" in job_id:
            return await call_next(request)

        try:
            core_module.require_admin(request.headers.get("authorization"))
        except core_module.HTTPException as exc:
            return core_module.JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        job = core_module._jobs.get(job_id)
        if not job:
            return core_module.JSONResponse(
                status_code=404, content={"detail": f"Khong tim thay job '{job_id}'"}
            )
        path = Path(job.get("output_path", ""))
        if not path.is_file():
            return core_module.JSONResponse(
                status_code=404, content={"detail": "File ket qua chua san sang"}
            )
        try:
            rows = int(request.query_params.get("rows", "50"))
        except (TypeError, ValueError):
            return core_module.JSONResponse(
                status_code=422, content={"detail": "rows phai la so nguyen"}
            )

        try:
            return core_module.JSONResponse(content=build_visible_preview(path, rows))
        except Exception as exc:
            return core_module.JSONResponse(
                status_code=500, content={"detail": f"Loi doc file ket qua: {exc}"}
            )

    core_module.app.state.visible_preview_contract = True
