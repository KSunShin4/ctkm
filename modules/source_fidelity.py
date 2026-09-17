# -*- coding: utf-8 -*-
"""Restore source columns that operational reconciliation does not consume.

The action builder intentionally works with a compact business schema.  That is
useful for deterministic action logic, but the final ``Audit hành động`` is also
our source-lineage surface.  Dropping unmapped/secondary source columns before
that audit makes the output impossible to reconcile back to the uploaded file.

This contract keeps action logic unchanged and restores *only* columns that were
present on the source promotion rows but absent from the action frame.  Values are
copied by stable source-row lineage and are never normalized or inferred.
"""
from __future__ import annotations

from functools import wraps

import pandas as pd


_MARKER = "_ctkm_source_fidelity_v1"


def _blank(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


def _fallback_source_row_id(row, position: int) -> str:
    source = row.get("program_source")
    source = "CTKM" if _blank(source) else str(source).strip()
    sheet = row.get("source_sheet")
    sheet = "Sheet1" if _blank(sheet) else str(sheet).strip()
    return f"{source}:{sheet}:{position}"


def _source_row_id(row, position: int) -> str:
    value = row.get("source_row_id")
    return _fallback_source_row_id(row, position) if _blank(value) else str(value)


def _lineage_ids(row) -> list[str]:
    values = []
    for field in ("source_row_ids", "source_row_id"):
        value = row.get(field)
        if _blank(value):
            continue
        values.extend(part.strip() for part in str(value).split("|") if part.strip())
    return list(dict.fromkeys(values))


def _fingerprint(value):
    try:
        if pd.isna(value):
            return ("missing", "")
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return ("timestamp", value.isoformat())
    return (type(value).__name__, str(value))


def _restore_missing_source_columns(
    source_frame: pd.DataFrame | None,
    actions: pd.DataFrame | None,
) -> tuple[pd.DataFrame | None, list[str]]:
    if source_frame is None or actions is None or source_frame.empty or actions.empty:
        return actions, []

    missing_columns = [
        column for column in source_frame.columns
        if column not in actions.columns
    ]
    if not missing_columns:
        return actions, []

    source_lookup: dict[str, pd.Series] = {}
    for position, (_, row) in enumerate(source_frame.iterrows(), start=2):
        row_id = _source_row_id(row, position)
        existing = source_lookup.get(row_id)
        if existing is not None:
            # A stable lineage id must identify one source row.  Failing here is
            # safer than silently selecting one of two different raw rows.
            if any(
                _fingerprint(existing.get(column)) != _fingerprint(row.get(column))
                for column in source_frame.columns
            ):
                raise RuntimeError(
                    f"Source fidelity invariant failed; lineage id trùng nhưng dữ liệu khác: {row_id}"
                )
            continue
        source_lookup[row_id] = row

    result = actions.copy()
    for column in missing_columns:
        result[column] = pd.NA

    unmatched: list[str] = []
    for idx, action in result.iterrows():
        lineage = _lineage_ids(action)
        source_rows = [source_lookup[row_id] for row_id in lineage if row_id in source_lookup]
        if not source_rows:
            unmatched.append(str(action.get("source_row_id") or action.get("item_id") or idx))
            continue

        for column in missing_columns:
            values = [row.get(column) for row in source_rows]
            fingerprints = {_fingerprint(value) for value in values}
            if len(fingerprints) > 1:
                raise RuntimeError(
                    "Source fidelity invariant failed; exact-duplicate lineage chứa "
                    f"giá trị nguồn khác nhau ở cột {column!r}: {lineage}"
                )
            result.at[idx, column] = values[0]

    if unmatched:
        sample = ", ".join(unmatched[:5])
        raise RuntimeError(
            "Source fidelity invariant failed; action không truy ngược được dòng nguồn: "
            + sample
        )

    return result, missing_columns


def _hide_restored_columns_from_operational_front_view(columns: list[str]) -> None:
    """Keep raw extras in the workbook audit without cluttering task sheets."""
    if not columns:
        return
    from modules import ctkm_performance

    user_columns = set(ctkm_performance.USER_ACTION_COLUMNS)
    for column in columns:
        if column in user_columns or column in ctkm_performance.TECHNICAL_ACTION_COLUMNS:
            continue
        ctkm_performance.TECHNICAL_ACTION_COLUMNS.append(column)


def apply_source_fidelity_hook(core_module, facade_module=None) -> None:
    """Wrap the current action builder once and preserve source passthrough data."""
    _ = facade_module
    current = core_module.RC.build_fefo_action_frame
    if getattr(current, _MARKER, False):
        return

    @wraps(current)
    def source_faithful_actions(df_ctkm, *args, **kwargs):
        actions = current(df_ctkm, *args, **kwargs)
        restored, columns = _restore_missing_source_columns(df_ctkm, actions)
        _hide_restored_columns_from_operational_front_view(columns)
        return restored

    setattr(source_faithful_actions, _MARKER, True)
    source_faithful_actions.__wrapped__ = current
    core_module.RC.build_fefo_action_frame = source_faithful_actions
