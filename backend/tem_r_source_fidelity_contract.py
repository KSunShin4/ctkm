# -*- coding: utf-8 -*-
"""Preserve raw Tem R ITEMID values without changing allocation semantics.

The allocator now keeps uploaded ``ITEMID`` values source-faithful in core and
uses only technical ``_item_key`` for normalized identity. This compatibility
contract remains defensive for older allocator implementations, while never
overwriting an already-correct technical key produced by current core.
"""
from __future__ import annotations

from functools import wraps

import pandas as pd


_MARKER = "_ctkm_tem_r_source_fidelity_v1"


def _is_missing(value) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _normalized_item(value) -> str | None:
    if _is_missing(value):
        return None
    text = str(value).strip().upper()
    if not text or text in {"NAN", "NONE", "#N/A", "#REF!", "#VALUE!"}:
        return None
    return text


def _source_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Mirror the allocator's repeated-header removal without mutating values."""
    if frame is None or frame.empty or "ITEMID" not in frame.columns:
        return frame.copy() if frame is not None else pd.DataFrame()
    repeated_header = frame["ITEMID"].map(_normalized_item).eq("ITEMID")
    return frame.loc[~repeated_header].copy().reset_index(drop=True)


def _raw_itemids_for_plan(source: pd.DataFrame, rows: pd.DataFrame) -> list[object]:
    if len(source) != len(rows):
        raise RuntimeError(
            "Tem R source fidelity invariant failed: số dòng plan khác số dòng nguồn sau header"
        )

    if "_excel_row" in source.columns and "_excel_row" in rows.columns:
        by_excel_row = {}
        for _, source_row in source.iterrows():
            excel_row = source_row.get("_excel_row")
            if _is_missing(excel_row):
                continue
            key = int(excel_row)
            if key in by_excel_row:
                raise RuntimeError(
                    f"Tem R source fidelity invariant failed: trùng _excel_row={key}"
                )
            by_excel_row[key] = source_row.get("ITEMID")

        result = []
        for _, plan_row in rows.iterrows():
            excel_row = plan_row.get("_excel_row")
            if _is_missing(excel_row) or int(excel_row) not in by_excel_row:
                raise RuntimeError(
                    "Tem R source fidelity invariant failed: không truy ngược được ITEMID theo _excel_row"
                )
            result.append(by_excel_row[int(excel_row)])
        return result

    return source["ITEMID"].tolist()


def _restore_plan_itemids(tem_r_module, source_frame: pd.DataFrame, plan):
    source = _source_rows(source_frame)
    rows = plan.rows.copy()
    raw_itemids = _raw_itemids_for_plan(source, rows)

    # Current core already exposes normalized technical identity. Preserve it.
    # Older cores normalized ITEMID directly, so derive a key only as fallback.
    if "_item_key" not in rows.columns:
        rows["_item_key"] = rows["ITEMID"].map(_normalized_item)
    rows["ITEMID"] = raw_itemids

    audit = plan.audit.copy()
    if len(audit) != len(raw_itemids):
        raise RuntimeError(
            "Tem R source fidelity invariant failed: audit không cùng số dòng với plan"
        )
    audit["ITEMID"] = raw_itemids

    exceptions = plan.exceptions.copy()
    if not exceptions.empty and "ITEMID" in exceptions.columns:
        if "_excel_row" in source.columns:
            raw_by_row = {
                int(row["_excel_row"]): row.get("ITEMID")
                for _, row in source.iterrows()
                if not _is_missing(row.get("_excel_row"))
            }
        else:
            raw_by_row = {
                position + 2: value for position, value in enumerate(raw_itemids)
            }
        restored = []
        for _, exception in exceptions.iterrows():
            row_number = exception.get("row")
            raw = None
            if not _is_missing(row_number):
                raw = raw_by_row.get(int(row_number))
            restored.append(
                exception.get("ITEMID") if raw is None else raw
            )
        exceptions["ITEMID"] = restored

    return tem_r_module.TemRPlan(rows=rows, audit=audit, exceptions=exceptions)


def install_tem_r_source_fidelity_contract(core_module) -> None:
    if getattr(core_module.app.state, "tem_r_source_fidelity_contract_v1", False):
        return

    tem_r_module = core_module._tem_r_mod
    current = tem_r_module.build_tem_r_plan
    if getattr(current, _MARKER, False):
        core_module.app.state.tem_r_source_fidelity_contract_v1 = True
        return

    @wraps(current)
    def source_faithful_build_tem_r_plan(frame, *args, **kwargs):
        plan = current(frame, *args, **kwargs)
        return _restore_plan_itemids(tem_r_module, frame, plan)

    setattr(source_faithful_build_tem_r_plan, _MARKER, True)
    tem_r_module.build_tem_r_plan = source_faithful_build_tem_r_plan

    # ``create_tem_r_workbook`` resolves ``build_tem_r_plan`` from the facade
    # module globals at call time, so replacing this attribute also makes the
    # generated audit workbook source-faithful without duplicating exporter code.
    core_module.app.state.tem_r_source_fidelity_contract_v1 = True
