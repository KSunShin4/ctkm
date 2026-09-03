# -*- coding: utf-8 -*-
"""End-to-end validation for the final CTKM workbook artifact.

The validator deliberately uses OpenPyXL read-only streaming for cell values and
reads row/column visibility directly from worksheet XML. This preserves the same
final-artifact invariants without materializing a second full styled workbook in
memory after export, which is important on the 512 MiB Render runtime.
"""
from __future__ import annotations

from datetime import date, datetime
from numbers import Number
from pathlib import Path
import posixpath
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import openpyxl

from backend.workbook_semantics import (
    is_empty_placeholder,
    visible_column_indexes,
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

_LEGACY_CANONICAL_PAIRS = (
    ("So dong CTKM thieu vi tri ke", "So dong KM thieu vi tri POG"),
    ("So item CTKM thieu vi tri ke", "So item KM thieu vi tri POG"),
    ("So dong POG khong co CTKM phu hop", "So dong POG khong co KM phu hop"),
    ("So item POG khong co CTKM phu hop", "So item POG khong co KM phu hop"),
)

_SUMMARY_SHEET_COUNT_PAIRS = (
    ("So dong KM thieu vi tri POG", "CTKM thieu vi tri ke"),
    ("So dong can kiem tra vi tri", "POG cần kiểm tra"),
    ("So dong cho gan", "Chờ gắn"),
    ("So dong can review", "Cần review"),
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

_LEGACY_HIDDEN_SUMMARY_KEYS = {
    "So dong CTKM thieu vi tri ke",
    "So item CTKM thieu vi tri ke",
    "So dong POG khong co CTKM phu hop",
    "So item POG khong co CTKM phu hop",
}

_EMPTY_NOTE_PREFIXES = (
    "không có",
    "khong co",
    "không phát hiện",
    "khong phat hien",
    "chưa có",
    "chua co",
)

_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _same_value(expected, actual) -> bool:
    if expected is None and actual is None:
        return True
    if isinstance(expected, Number) and isinstance(actual, Number):
        return float(expected) == float(actual)
    if isinstance(expected, (date, datetime)) and isinstance(actual, (date, datetime)):
        return expected == actual
    return str(expected) == str(actual)


def _truthy_xml(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _sheet_xml_paths(artifact: Path) -> dict[str, str]:
    """Resolve visible workbook sheet names to their OOXML worksheet parts."""
    with ZipFile(artifact) as archive:
        workbook_root = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))

    rel_targets = {}
    for relation in rels_root.iter():
        if relation.tag.rsplit("}", 1)[-1] != "Relationship":
            continue
        rel_id = relation.attrib.get("Id")
        target = relation.attrib.get("Target")
        if rel_id and target:
            target = target.lstrip("/")
            if not target.startswith("xl/"):
                target = posixpath.normpath(posixpath.join("xl", target))
            rel_targets[rel_id] = target

    result = {}
    for sheet in workbook_root.iter():
        if sheet.tag.rsplit("}", 1)[-1] != "sheet":
            continue
        name = sheet.attrib.get("name")
        rel_id = sheet.attrib.get(f"{{{_REL_NS}}}id")
        target = rel_targets.get(rel_id)
        if name and target:
            result[name] = target
    return result


def _sheet_visibility(artifact: Path, xml_path: str) -> tuple[set[int], list[tuple[int, int]]]:
    hidden_rows: set[int] = set()
    hidden_columns: list[tuple[int, int]] = []
    with ZipFile(artifact) as archive, archive.open(xml_path) as stream:
        for event, elem in ET.iterparse(stream, events=("start", "end")):
            if event == "start":
                local = elem.tag.rsplit("}", 1)[-1]
                if local == "row" and _truthy_xml(elem.attrib.get("hidden")):
                    try:
                        hidden_rows.add(int(elem.attrib.get("r", "0")))
                    except ValueError:
                        pass
                elif local == "col" and _truthy_xml(elem.attrib.get("hidden")):
                    try:
                        start = int(elem.attrib.get("min", "0"))
                        end = int(elem.attrib.get("max", str(start)))
                    except ValueError:
                        continue
                    if start > 0 and end >= start:
                        hidden_columns.append((start, end))
            else:
                elem.clear()
    return hidden_rows, hidden_columns


def _column_hidden(index: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= index <= end for start, end in ranges)


def _visible_values(row, hidden_columns: list[tuple[int, int]]) -> list[object]:
    return [
        value for index, value in enumerate(row, start=1)
        if not _column_hidden(index, hidden_columns)
    ]


def _is_placeholder(headers: list[str], row_values: list[object], count: int) -> bool:
    if count != 1 or len(headers) != 1:
        return False
    if headers[0].strip().lower() not in {"ghi chu", "ghi chú"}:
        return False
    value = "" if not row_values or row_values[0] is None else str(row_values[0]).strip().lower()
    return value.startswith(_EMPTY_NOTE_PREFIXES)


def _stream_visible_row_count(ws, visibility: tuple[set[int], list[tuple[int, int]]]) -> int:
    hidden_rows, hidden_columns = visibility
    iterator = ws.iter_rows(values_only=True)
    header = next(iterator, tuple())
    headers = [
        "" if value is None else str(value)
        for value in _visible_values(header, hidden_columns)
    ]
    count = 0
    first_values: list[object] = []
    for row_index, row in enumerate(iterator, start=2):
        if row_index in hidden_rows:
            continue
        values = _visible_values(row, hidden_columns)
        if not any(value is not None and str(value).strip() for value in values):
            continue
        count += 1
        if count == 1:
            first_values = values
    return 0 if _is_placeholder(headers, first_values, count) else count


def _summary_from_stream(ws) -> tuple[dict, dict[str, int]]:
    result = {}
    indexes: dict[str, int] = {}
    for row_index, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row_index == 1:
            continue
        key = row[0] if len(row) > 0 else None
        if key is None or not str(key).strip():
            continue
        text = str(key)
        result[text] = row[1] if len(row) > 1 else None
        indexes[text] = row_index
    return result, indexes


def _guide_rows(ws):
    for row in ws.iter_rows(values_only=True):
        label = row[0] if len(row) > 0 else None
        count = row[1] if len(row) > 1 else None
        yield label, count


def validate_ctkm_workbook(path: str | Path, summary: dict | None) -> None:
    """Reject an unreadable/inconsistent artifact using bounded-memory reads."""
    artifact = Path(path)
    if not artifact.is_file():
        raise RuntimeError("Pipeline không tạo được file Excel kết quả.")

    workbook = None
    try:
        xml_paths = _sheet_xml_paths(artifact)
        visibility_needed = set(_GUIDE_TARGETS.values()) | {"Tom tat"}
        visibility = {}
        for sheet_name in visibility_needed:
            xml_path = xml_paths.get(sheet_name)
            if xml_path:
                visibility[sheet_name] = _sheet_visibility(artifact, xml_path)
            else:
                visibility[sheet_name] = (set(), [])

        workbook = openpyxl.load_workbook(
            artifact, data_only=True, read_only=True, keep_links=False
        )
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
        summary_ws = workbook["Tom tat"]
        workbook_summary, summary_rows = _summary_from_stream(summary_ws)
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

        for legacy_key, canonical_key in _LEGACY_CANONICAL_PAIRS:
            if legacy_key in summary_dict and canonical_key in summary_dict:
                if not _same_value(summary_dict[legacy_key], summary_dict[canonical_key]):
                    raise RuntimeError(
                        f"Summary legacy '{legacy_key}' lệch canonical '{canonical_key}'."
                    )

        hidden_summary_rows = visibility.get("Tom tat", (set(), []))[0]
        for legacy_key in _LEGACY_HIDDEN_SUMMARY_KEYS:
            row = summary_rows.get(legacy_key)
            if row is not None and row not in hidden_summary_rows:
                raise RuntimeError(
                    f"Tom tat phải ẩn legacy metric '{legacy_key}' để tránh nhãn sai nghĩa."
                )

        count_cache: dict[str, int] = {}

        def sheet_count(sheet_name: str) -> int:
            if sheet_name not in count_cache:
                count_cache[sheet_name] = _stream_visible_row_count(
                    workbook[sheet_name], visibility.get(sheet_name, (set(), []))
                )
            return count_cache[sheet_name]

        for summary_key, sheet_name in _SUMMARY_SHEET_COUNT_PAIRS:
            if summary_key not in summary_dict:
                continue
            count = sheet_count(sheet_name)
            if not _same_value(summary_dict[summary_key], count):
                raise RuntimeError(
                    f"Summary '{summary_key}' không khớp sheet '{sheet_name}': "
                    f"API={summary_dict[summary_key]!r}, rows={count}"
                )

        seen_targets: set[str] = set()
        for label, actual_count in _guide_rows(workbook["HƯỚNG DẪN"]):
            if label not in _GUIDE_TARGETS:
                continue
            target = _GUIDE_TARGETS[label]
            expected_count = sheet_count(target)
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
    # placeholder/visibility rules. Preview works on a small row window and can
    # keep the existing worksheet helper contract.
    from backend import preview_contract

    preview_contract._visible_column_indexes = visible_column_indexes
    preview_contract._visible_nonempty_rows = visible_nonempty_rows
    preview_contract._is_empty_placeholder = is_empty_placeholder

    core_module.app.state.final_output_contract_v1 = True
