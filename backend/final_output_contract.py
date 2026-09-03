# -*- coding: utf-8 -*-
"""End-to-end validation for the final CTKM workbook artifact."""
from __future__ import annotations

from datetime import date, datetime
from numbers import Number
from pathlib import Path

import openpyxl

from backend.workbook_semantics import (
    is_empty_placeholder,
    visible_column_indexes,
    visible_data_row_count,
    visible_nonempty_rows,
)


_REQUIRED_CTKM_SHEETS = {
    "HƯỚNG DẪN",
    "Gắn tem",
    "Tháo tem",
    "Chờ gắn",
    "Cần review",
    "CTKM thieu vi tri ke",
    "POG cần kiểm tra",
    "Tong hop",
    "POG không có CTKM",
    "POG cần review",
    "Audit hành động",
    "Canh bao trung thoi gian",
    "Xác nhận CTKM Clearance",
    "Tom tat",
    "Mapping log",
}

_SUMMARY_KEYS_TO_VERIFY = (
    "Thang bao cao",
    "So dong khop (Matched)",
    "So item duy nhat khop",
    "So dong KM thieu vi tri POG",
    "So item KM thieu vi tri POG",
    "So dong can kiem tra vi tri",
    "So canh bao trung thoi gian",
    "So dong cho gan",
    "So dong can review",
    "So dong POG khong co KM phu hop",
    "So item POG khong co KM phu hop",
)

_GUIDE_TARGETS = {
    "Gắn tem": "Gắn tem",
    "Tháo tem": "Tháo tem",
    "Chờ gắn": "Chờ gắn",
    "Cần review": "Cần review",
    "Thiếu vị trí": "CTKM thieu vi tri ke",
    "Thiếu vị trí KM": "CTKM thieu vi tri ke",
    "Review vị trí": "POG cần kiểm tra",
    "POG cần review": "POG cần review",
    "Xác nhận CTKM / Clearance": "Xác nhận CTKM Clearance",
}


def _summary_from_sheet(ws) -> dict:
    result = {}
    for row in range(2, (ws.max_row or 0) + 1):
        key = ws.cell(row=row, column=1).value
        if key is None or not str(key).strip():
            continue
        result[str(key)] = ws.cell(row=row, column=2).value
    return result


def _same_value(expected, actual) -> bool:
    if expected is None and actual is None:
        return True
    if isinstance(expected, Number) and isinstance(actual, Number):
        return float(expected) == float(actual)
    if isinstance(expected, (date, datetime)) and isinstance(actual, (date, datetime)):
        return expected == actual
    return str(expected) == str(actual)


def validate_ctkm_workbook(path: str | Path, summary: dict | None) -> None:
    """Reject a final artifact that is unreadable or internally inconsistent."""
    artifact = Path(path)
    if not artifact.is_file():
        raise RuntimeError("Pipeline không tạo được file Excel kết quả.")

    workbook = None
    try:
        workbook = openpyxl.load_workbook(artifact, data_only=True, read_only=False)
        missing = sorted(_REQUIRED_CTKM_SHEETS - set(workbook.sheetnames))
        if missing:
            raise RuntimeError(
                "Workbook kết quả thiếu sheet bắt buộc: " + ", ".join(missing)
            )
        if not workbook.sheetnames or workbook.sheetnames[0] != "HƯỚNG DẪN":
            raise RuntimeError("Workbook kết quả không đặt HƯỚNG DẪN ở sheet đầu tiên.")
        if workbook["Mapping log"].sheet_state != "hidden":
            raise RuntimeError("Mapping log phải được ẩn trong workbook kết quả.")
        for metadata_name in ("POG metadata", "KM metadata"):
            if metadata_name in workbook.sheetnames and workbook[metadata_name].sheet_state != "hidden":
                raise RuntimeError(f"{metadata_name} phải được ẩn trong workbook kết quả.")

        summary_dict = summary if isinstance(summary, dict) else {}
        workbook_summary = _summary_from_sheet(workbook["Tom tat"])
        for key in _SUMMARY_KEYS_TO_VERIFY:
            if key not in summary_dict:
                continue
            if key not in workbook_summary:
                raise RuntimeError(f"Tom tat thiếu chỉ số '{key}'.")
            if not _same_value(summary_dict[key], workbook_summary[key]):
                raise RuntimeError(
                    f"Tom tat không khớp summary cho '{key}': "
                    f"API={summary_dict[key]!r}, Excel={workbook_summary[key]!r}"
                )

        guide = workbook["HƯỚNG DẪN"]
        seen_targets: set[str] = set()
        for row in range(1, (guide.max_row or 0) + 1):
            label = guide.cell(row=row, column=1).value
            if label not in _GUIDE_TARGETS:
                continue
            target = _GUIDE_TARGETS[label]
            expected_count = visible_data_row_count(workbook[target])
            actual_count = guide.cell(row=row, column=2).value
            if not _same_value(expected_count, actual_count):
                raise RuntimeError(
                    f"HƯỚNG DẪN không khớp sheet '{target}': "
                    f"card={actual_count!r}, rows={expected_count}"
                )
            seen_targets.add(target)

        required_guide_targets = set(_GUIDE_TARGETS.values())
        missing_cards = sorted(required_guide_targets - seen_targets)
        if missing_cards:
            raise RuntimeError(
                "HƯỚNG DẪN thiếu card cho sheet: " + ", ".join(missing_cards)
            )
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Workbook kết quả không đọc được: {exc}") from exc
    finally:
        if workbook is not None:
            workbook.close()


def install_final_output_contract(core_module) -> None:
    if getattr(core_module.app.state, "final_output_contract_v1", False):
        return

    original_run_pipeline = core_module.run_pipeline

    def validated_run_pipeline(*args, **kwargs):
        result = original_run_pipeline(*args, **kwargs)
        validate_ctkm_workbook(result.output_filepath, result.summary)
        return result

    core_module.run_pipeline = validated_run_pipeline

    # Preview and artifact validation must count rows with exactly the same
    # placeholder/visibility rules.
    from backend import preview_contract

    preview_contract._visible_column_indexes = visible_column_indexes
    preview_contract._visible_nonempty_rows = visible_nonempty_rows
    preview_contract._is_empty_placeholder = is_empty_placeholder

    core_module.app.state.final_output_contract_v1 = True
