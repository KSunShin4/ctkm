# -*- coding: utf-8 -*-
"""Render-oriented CTKM workbook export without sacrificing source auditability.

The production profile avoids expensive diagnostic styling, but it must not
silently remove reconciliation/source evidence.  Operational sheets stay compact;
raw passthrough columns remain available in ``Audit hành động`` and source/control
metadata remains hidden for audit.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

from modules.all_km_reconciliation import (
    _frame_keys,
    _identity,
    build_all_km_reconciliation_frames,
)
from modules.ctkm_performance import align_task_summary_with_work_rows


SLIM_SHEET_ORDER = [
    "HƯỚNG DẪN",
    "TỔNG HỢP - TEM",
    "Gắn tem",
    "Tháo tem",
    "Chờ gắn",
    "Cần review",
    "CTKM thieu vi tri ke",
    "POG cần kiểm tra",
    "Tong hop",
    "POG không có KM",
    "POG không có Monthly CTKM",
    "POG cần review",
    "Audit hành động",
    "Mapping log",
    "POG không có CTKM",
    "POG metadata",
    "KM metadata",
]


def _truthy(value) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _in_scope(actions: pd.DataFrame) -> pd.Series:
    if "in_report_scope" not in actions.columns:
        return pd.Series(True, index=actions.index)
    return actions["in_report_scope"].fillna(False).astype(bool)


def _review_mask(actions: pd.DataFrame, exporter) -> pd.Series:
    if "review_required" in actions.columns:
        return actions["review_required"].map(_truthy)
    field = "scheduled_action" if "scheduled_action" in actions.columns else "action"
    if field not in actions.columns:
        return pd.Series(False, index=actions.index)
    return actions[field].apply(exporter._normalize_action_text).eq("review")


def _prepare_frames(exporter, df_fefo_actions: pd.DataFrame | None):
    if df_fefo_actions is None or df_fefo_actions.empty:
        base = pd.DataFrame(columns=[
            "task_id", "item_id", "item_name", "promo_uom", "program_source",
            "campaign_name", "campaign_detail", "promo_from", "promo_to",
            "normal_price", "promo_price", "key_channel", "channel", "product_type",
            "source_sheet", "scheduled_action", "action", "reason", "target_month",
            "location_status", "review_required", "review_reason",
        ])
        actions = base.copy()
    else:
        actions = df_fefo_actions.copy()

    for required_column in ("key_channel", "channel", "item_id", "item_name", "promo_uom"):
        if required_column not in actions.columns:
            actions[required_column] = pd.NA

    scope = _in_scope(actions)
    action_field = "scheduled_action" if "scheduled_action" in actions.columns else "action"
    normalized = (
        actions[action_field].apply(exporter._normalize_action_text)
        if action_field in actions.columns
        else pd.Series("", index=actions.index)
    )

    gan = actions[scope & normalized.isin({"gan tem", "gan tem fefo"})].copy()
    thao = actions[scope & normalized.isin({"thao tem", "thao tem fefo", "thao rem fefo"})].copy()
    wait = actions[scope & normalized.eq("cho gan tem")].copy()
    review = actions[scope & _review_mask(actions, exporter)].copy()

    if "location_completeness" in actions.columns:
        location_issues = actions[scope & ~actions["location_completeness"].eq("Đủ vị trí")].copy()
    elif "location_status" in actions.columns:
        location_issues = actions[scope & ~actions["location_status"].eq("Đủ vị trí")].copy()
    else:
        location_issues = pd.DataFrame(columns=actions.columns)

    if "location_needs_review" in actions.columns:
        location_review = actions[
            scope & actions["location_needs_review"].fillna(False).astype(bool)
        ].copy()
    else:
        # Completeness and review are independent location-quality axes.
        # Missing/partial coordinates belong to CTKM thieu vi tri ke, but without
        # the canonical review flag there is no evidence that a row belongs to
        # POG cần kiểm tra. Never manufacture review rows by copying the issue set.
        location_review = pd.DataFrame(columns=actions.columns)

    for frame in (gan, thao, wait, review):
        if "so_ngay_con_lai" not in frame.columns:
            frame["so_ngay_con_lai"] = ""

    gan = exporter._prepare_action_sheet(exporter._add_work_tracking_columns(gan))
    thao = exporter._prepare_action_sheet(exporter._add_work_tracking_columns(thao))
    wait = exporter._prepare_action_sheet(exporter._add_work_tracking_columns(wait))
    review = exporter._prepare_action_sheet(exporter._add_work_tracking_columns(review))
    location_issues = exporter._prepare_action_sheet(location_issues)
    location_review = exporter._prepare_action_sheet(location_review)
    audit = exporter._prepare_action_sheet(actions)
    total = exporter._build_total_action_frame(actions)
    return total, gan, thao, wait, review, location_issues, location_review, audit


def _lightweight_audit_style(ws, exporter) -> None:
    """Keep audit/reconciliation usable without expensive per-cell body styling."""
    ws.freeze_panes = "A2"
    ws.sheet_view.showGridLines = False
    if ws.max_row >= 1 and ws.max_column >= 1:
        ws.auto_filter.ref = ws.dimensions
    fill = PatternFill(fill_type="solid", fgColor="5B5EA6")
    font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for index, cell in enumerate(ws[1], start=1):
        header = str(cell.value or "")
        width = getattr(exporter, "_COLUMN_WIDTHS", {}).get(
            header, min(30, max(12, len(header) + 2))
        )
        ws.column_dimensions[exporter.get_column_letter(index)].width = width
    exporter._apply_bilingual_headers(ws)


def _trim_guide_to_slim_profile(workbook) -> None:
    """Remove only cards for user-facing sheets still omitted by slim profile."""
    ws = workbook["HƯỚNG DẪN"]
    rows_to_delete = []
    for row_idx in range(1, ws.max_row + 1):
        if ws.cell(row_idx, 1).value in {"Xác nhận CTKM / Clearance"}:
            rows_to_delete.append(row_idx)
    for row_idx in reversed(rows_to_delete):
        ws.delete_rows(row_idx, 1)
    ws["D10"] = (
        "Bản production slim: giảm styling/diagnostic nặng nhưng vẫn giữ "
        "reconciliation và source audit để không mất dữ liệu nguồn."
    )


def _safe_frame(exporter, frame: pd.DataFrame | None, message: str) -> pd.DataFrame:
    source = frame if frame is not None else pd.DataFrame()
    return exporter._safe(source, message)


def _metadata_from(frame: pd.DataFrame | None, attr_name: str) -> pd.DataFrame | None:
    if frame is None:
        return None
    metadata = getattr(frame, "attrs", {}).get(attr_name)
    return metadata.copy() if isinstance(metadata, pd.DataFrame) and not metadata.empty else None


def _write_hidden_metadata(writer, sheet_name: str, frame: pd.DataFrame | None) -> None:
    if frame is None or frame.empty:
        return
    frame.to_excel(writer, sheet_name=sheet_name, index=False)
    ws = writer.sheets[sheet_name]
    ws.freeze_panes = "A2"
    if ws.max_row >= 1 and ws.max_column >= 1:
        ws.auto_filter.ref = ws.dimensions
    ws.sheet_state = "hidden"


def _update_all_km_summary(
    main_core,
    summary: dict | None,
    matched_all: pd.DataFrame,
    monthly_pog_only: pd.DataFrame | None,
    missing_all_km: pd.DataFrame,
    actions: pd.DataFrame | None,
    added_keys: set[str],
) -> None:
    if not isinstance(summary, dict):
        return

    scoped_actions = actions.copy() if actions is not None else pd.DataFrame()
    if not scoped_actions.empty and "in_report_scope" in scoped_actions.columns:
        scoped_actions = scoped_actions[
            scoped_actions["in_report_scope"].fillna(False).astype(bool)
        ].copy()
    identity_input = scoped_actions if not scoped_actions.empty else matched_all
    identity = _identity(main_core, identity_input)

    monthly_keys = set(_frame_keys(main_core, identity, monthly_pog_only).dropna())
    matched_keys = set(_frame_keys(main_core, identity, matched_all).dropna())
    missing_keys = set(_frame_keys(main_core, identity, missing_all_km).dropna())

    summary["So dong khop (Matched)"] = len(matched_all)
    summary["So item duy nhat khop"] = len(matched_keys)
    summary["So dong POG khong co CTKM Monthly phu hop"] = (
        0 if monthly_pog_only is None else len(monthly_pog_only)
    )
    summary["So item POG khong co CTKM Monthly phu hop"] = len(monthly_keys)
    summary["So dong POG khong co KM phu hop"] = len(missing_all_km)
    summary["So item POG khong co KM phu hop"] = len(missing_keys)
    summary["So item Clearance bo sung vao Tong hop"] = len(added_keys)
    summary["So item KM+POG thieu trong Tong hop"] = 0

    # Legacy API aliases stay aligned with the canonical all-KM meaning.
    if "So dong POG khong co CTKM phu hop" in summary:
        summary["So dong POG khong co CTKM phu hop"] = len(missing_all_km)
    if "So item POG khong co CTKM phu hop" in summary:
        summary["So item POG khong co CTKM phu hop"] = len(missing_keys)


_SELECTABLE_PRESENTATION_FIELDS = {
    "item_id", "item_name", "promo_uom", "key_channel", "channel",
    "campaign_name", "campaign_detail", "promo_from", "promo_to",
    "normal_price", "promo_price", "product_type",
    "store_id", "pog_code", "location_id", "facing",
}
_PINNED_PRESENTATION_FIELDS = {
    "key_channel", "channel", "item_id", "item_name", "promo_uom",
}


def _apply_selected_output_visibility(ws, exporter, selected: set[str]) -> None:
    if not selected:
        return
    for index, cell in enumerate(ws[1], start=1):
        header = str(cell.value or "").strip()
        if header in _PINNED_PRESENTATION_FIELDS:
            ws.column_dimensions[exporter.get_column_letter(index)].hidden = False
            continue
        if header in _SELECTABLE_PRESENTATION_FIELDS:
            ws.column_dimensions[exporter.get_column_letter(index)].hidden = (
                header.lower() not in selected
            )


def _mapping_log_frame(mapping_logs) -> pd.DataFrame:
    rows = []
    for log in mapping_logs or []:
        sheet_name = log.get("sheet_name", "")
        source = log.get("source", "")
        confidence = log.get("confidence") or {}
        low = set(log.get("low_confidence_fields") or [])
        mapping = log.get("mapping") or {}
        for source_column, canonical_field in mapping.items():
            rows.append({
                "sheet": sheet_name,
                "cot_goc": source_column,
                "canonical_field": canonical_field,
                "confidence": confidence.get(source_column),
                "can_review": source_column in low,
                "nguon": source,
            })
        for source_column in log.get("unmapped") or []:
            rows.append({
                "sheet": sheet_name,
                "cot_goc": source_column,
                "canonical_field": "(KHONG MAP DUOC)",
                "confidence": confidence.get(source_column),
                "can_review": True,
                "nguon": source,
            })
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame({"Ghi chu": ["Chưa có mapping log."]})


def install_slim_output_contract(core_module) -> None:
    if getattr(core_module.app.state, "slim_output_contract_v1", False):
        return

    main_mod = core_module._main_mod
    main_core = getattr(main_mod, "_core", main_mod)
    exporter = main_mod.EX

    def export_final_report_slim(
        output_path,
        df_matched,
        df_ctkm_only,
        df_pog_only,
        overlap_warnings,
        mapping_logs,
        reconciliation_summary,
        snapshot_alignment_warning=None,
        selected_output_columns=None,
        df_fefo_actions=None,
        df_ctkm_clearance_confirmation=None,
        df_pog_review=None,
    ) -> str:
        del df_ctkm_only, overlap_warnings, snapshot_alignment_warning

        matched_all, missing_all_km, added_keys = build_all_km_reconciliation_frames(
            main_core, df_matched, df_pog_only, df_fefo_actions
        )
        _update_all_km_summary(
            main_core,
            reconciliation_summary,
            matched_all,
            df_pog_only,
            missing_all_km,
            df_fefo_actions,
            added_keys,
        )

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        align_task_summary_with_work_rows(reconciliation_summary, df_fefo_actions)
        total, gan, thao, wait, review, location_issues, location_review, audit = _prepare_frames(
            exporter, df_fefo_actions
        )

        selected = {
            str(column).strip().lower()
            for column in (selected_output_columns or [])
            if str(column).strip()
        }
        pog_review = df_pog_review.copy() if df_pog_review is not None else pd.DataFrame()
        pog_metadata = _metadata_from(df_pog_review, "pog_metadata")
        km_metadata = _metadata_from(df_ctkm_clearance_confirmation, "fact_metadata")

        business_date = (
            reconciliation_summary.get("Ngay nghiep vu")
            if isinstance(reconciliation_summary, dict) else None
        )
        report_date = pd.to_datetime(business_date, errors="coerce")
        if pd.notna(report_date):
            report_date = report_date.normalize()
            for frame in (gan, thao, wait, review):
                if "so_ngay_con_lai" in frame.columns and "promo_to" in frame.columns:
                    promo_to = pd.to_datetime(frame["promo_to"], errors="coerce")
                    remaining = (promo_to.dt.normalize() - report_date).dt.days.clip(lower=0)
                    frame["so_ngay_con_lai"] = remaining.where(promo_to.notna(), "")

        action_names = {"Gắn tem", "Tháo tem", "Chờ gắn", "Cần review"}
        audit_names = {
            "Tong hop", "POG không có KM", "POG không có Monthly CTKM",
            "POG cần review", "POG không có CTKM", "Audit hành động", "Mapping log",
        }
        tab_colors = {
            "TỔNG HỢP - TEM": "#4F81BD",
            "Gắn tem": "#2E7D32",
            "Tháo tem": "#F28C00",
            "Chờ gắn": "#C79B00",
            "Cần review": "#7030A0",
            "CTKM thieu vi tri ke": "#C0504D",
            "POG cần kiểm tra": "#C0504D",
            "Tong hop": "#4F81BD",
            "POG không có KM": "#9BBB59",
            "POG không có Monthly CTKM": "#9BBB59",
            "POG cần review": "#C65911",
            "Audit hành động": "#5B5EA6",
            "Mapping log": "#5B5EA6",
        }

        def display_header(raw):
            raw = str(raw or "")
            base = raw.split("__", 1)[0]
            exact = getattr(exporter, "_BILINGUAL_HEADERS", {}).get(raw)
            base_label = getattr(exporter, "_BILINGUAL_HEADERS", {}).get(base)
            if exact:
                return exact
            if base_label:
                return base_label if raw == base else f"{base_label.split(' (', 1)[0]} ({raw})"
            return raw

        def is_technical(raw, *, action_sheet=False):
            raw = str(raw or "")
            normalized = exporter._normalize_action_text(raw)
            while normalized.startswith("extra__"):
                normalized = normalized[len("extra__"):]
            if normalized in {
                "channel", "key channel", "kenh ap dung", "kenh ban", "sales channel",
            }:
                return False
            return (
                raw.startswith("extra__")
                or raw.startswith("source_sheet__")
                or (
                    action_sheet
                    and raw in {"target_month", "source_sheet", "pog_snapshot_month"}
                )
            )

        with pd.ExcelWriter(
            output_path,
            engine="xlsxwriter",
            engine_kwargs={"options": {"strings_to_urls": False}},
        ) as writer:
            book = writer.book
            header_blue = book.add_format({
                "bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78",
                "align": "center", "valign": "vcenter", "text_wrap": True,
                "border": 1, "border_color": "#D0D7DE",
            })
            header_audit = book.add_format({
                "bold": True, "font_color": "#FFFFFF", "bg_color": "#5B5EA6",
                "align": "center", "valign": "vcenter", "text_wrap": True,
            })
            date_format = book.add_format({"num_format": "dd/mm/yyyy"})
            unlocked = book.add_format({"locked": False, "bg_color": "#FFF2CC"})
            unlocked_datetime = book.add_format({
                "locked": False, "bg_color": "#FFF2CC",
                "num_format": "dd/mm/yyyy hh:mm",
            })
            done_fill = book.add_format({"bg_color": "#E2F0D9"})
            missing_fill = book.add_format({"bg_color": "#FFC7CE"})
            gan_fill = book.add_format({"bg_color": "#E8F5E9"})
            thao_fill = book.add_format({"bg_color": "#FFF3E0"})
            warning_fill = book.add_format({"bg_color": "#FFF2CC"})

            guide = book.add_worksheet("HƯỚNG DẪN")
            writer.sheets["HƯỚNG DẪN"] = guide
            title_format = book.add_format({
                "bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78",
                "font_size": 18, "align": "center", "valign": "vcenter",
            })
            card_format = book.add_format({"bold": True, "bg_color": "#DDEBF7"})
            guide.merge_range("A1:F2", "DANH SÁCH THAO TÁC TEM KHUYẾN MÃI", title_format)
            guide.write("A4", "Tháng báo cáo")
            guide.write(
                "B4",
                reconciliation_summary.get("Thang bao cao", "")
                if isinstance(reconciliation_summary, dict) else "",
            )
            guide.write("A5", "Ngày nghiệp vụ")
            if pd.notna(report_date):
                guide.write_datetime("B5", report_date.to_pydatetime(), date_format)
            else:
                guide.write("B5", business_date if business_date is not None else "")
            guide.write("D4", "Cách sử dụng", card_format)
            instructions = [
                "1. Lọc KEY Channel trước, sau đó lọc Channel.",
                "2. Lọc tiếp Cửa hàng → Mã kệ → Vị trí kệ.",
                "3. POG chỉ cung cấp vị trí; không quyết định Gắn/Tháo/Chờ.",
                "4. Cập nhật các ô màu vàng sau khi xử lý tại quầy.",
            ]
            for offset, instruction in enumerate(instructions, start=5):
                guide.write(offset - 1, 3, instruction)
            cards = [
                ("Gắn tem", len(gan), "Gắn tem"),
                ("Tháo tem", len(thao), "Tháo tem"),
                ("Chờ gắn", len(wait), "Chờ gắn"),
                ("Cần review", len(review), "Cần review"),
                ("Thiếu vị trí", len(location_issues), "CTKM thieu vi tri ke"),
                ("Review vị trí", len(location_review), "POG cần kiểm tra"),
                ("POG cần review", len(pog_review), "POG cần review"),
            ]
            for row_index, (label, count, target) in enumerate(cards, start=5):
                guide.write_url(
                    row_index, 0, f"internal:'{target}'!A1",
                    card_format, string=label,
                )
                guide.write(row_index, 1, count)
            guide.write(
                "D10",
                "Bản production slim: giữ reconciliation và source audit, "
                "giảm formatting theo từng ô để xuất file nhanh hơn.",
            )
            guide.set_column("A:A", 24)
            guide.set_column("B:B", 22)
            guide.set_column("D:D", 60)
            guide.hide_gridlines(2)
            guide.set_tab_color("#1F4E78")

            frames = [
                ("TỔNG HỢP - TEM", total, "Không có dữ liệu tổng hợp."),
                ("Gắn tem", gan, "Không có CTKM cần gắn tem."),
                ("Tháo tem", thao, "Không có CTKM cần tháo tem."),
                ("Chờ gắn", wait, "Không có CTKM đang chờ đến ngày gắn."),
                ("Cần review", review, "Không có CTKM cần review."),
                ("CTKM thieu vi tri ke", location_issues, "Không có công việc nào cần kiểm tra vị trí POG."),
                ("POG cần kiểm tra", location_review, "Không có vị trí POG nào cần review."),
                ("Tong hop", matched_all, "Không có KM nào khớp POG."),
                ("POG không có KM", missing_all_km, "Không có POG nào thiếu KM."),
                ("POG không có Monthly CTKM", df_pog_only, "Không có POG nào thiếu Monthly CTKM."),
                ("POG cần review", pog_review, "Không có dòng POG business nào cần review."),
                ("Audit hành động", audit, "Không có dữ liệu hành động để audit."),
                ("Mapping log", _mapping_log_frame(mapping_logs), "Chưa có mapping log."),
                ("POG không có CTKM", missing_all_km, "Không có POG nào thiếu KM."),
            ]

            for sheet_name, frame, empty_message in frames:
                if sheet_name in {"TỔNG HỢP - TEM", "Mapping log"}:
                    safe = frame.copy() if frame is not None else pd.DataFrame()
                    if safe.empty and sheet_name == "Mapping log":
                        safe = pd.DataFrame({"Ghi chu": [empty_message]})
                else:
                    safe = _safe_frame(exporter, frame, empty_message)

                safe.to_excel(writer, sheet_name=sheet_name, index=False)
                ws = writer.sheets[sheet_name]
                action_sheet = sheet_name in action_names
                ws.hide_gridlines(2)
                ws.freeze_panes(1, 2 if action_sheet else 0)
                if len(safe.columns):
                    ws.autofilter(0, 0, max(0, len(safe)), len(safe.columns) - 1)
                ws.set_tab_color(tab_colors.get(sheet_name, "#4F81BD"))

                header_format = header_audit if sheet_name in audit_names else header_blue
                raw_headers = [str(column) for column in safe.columns]
                for col_index, raw in enumerate(raw_headers):
                    label = display_header(raw)
                    ws.write(0, col_index, label, header_format)
                    width = getattr(exporter, "_COLUMN_WIDTHS", {}).get(
                        raw, min(30, max(12, len(label) + 2))
                    )
                    hidden = is_technical(raw, action_sheet=action_sheet)
                    if sheet_name in {
                        "TỔNG HỢP - TEM", "Gắn tem", "Tháo tem", "Chờ gắn", "Cần review",
                    } and selected:
                        if raw in _PINNED_PRESENTATION_FIELDS:
                            hidden = False
                        elif raw in _SELECTABLE_PRESENTATION_FIELDS:
                            hidden = raw.lower() not in selected
                    column_format = date_format if raw in {
                        "promo_from", "promo_to", "ngay_gan_tem", "ngay_thao_tem",
                    } else None
                    if action_sheet and raw in {
                        "processing_status", "processed_by", "processed_at", "staff_note",
                    }:
                        column_format = unlocked_datetime if raw == "processed_at" else unlocked
                    ws.set_column(
                        col_index, col_index, width, column_format,
                        {"hidden": bool(hidden)},
                    )

                if action_sheet and len(safe.columns):
                    max_row = len(safe)
                    if "processing_status" in raw_headers and max_row:
                        status_col = raw_headers.index("processing_status")
                        ws.data_validation(
                            1, status_col, max_row, status_col,
                            {
                                "validate": "list",
                                "source": [
                                    "Chưa xử lý", "Đã xong",
                                    "Không tìm thấy", "Không thực hiện được",
                                ],
                                "ignore_blank": False,
                            },
                        )
                        status_letter = exporter.get_column_letter(status_col + 1)
                        ws.conditional_format(
                            1, 0, max_row, len(raw_headers) - 1,
                            {
                                "type": "formula",
                                "criteria": f'=${status_letter}2="Đã xong"',
                                "format": done_fill,
                            },
                        )
                        ws.conditional_format(
                            1, 0, max_row, len(raw_headers) - 1,
                            {
                                "type": "formula",
                                "criteria": f'=${status_letter}2="Không tìm thấy"',
                                "format": missing_fill,
                            },
                        )
                    if "action" in raw_headers and max_row:
                        action_col = raw_headers.index("action")
                        action_letter = exporter.get_column_letter(action_col + 1)
                        ws.conditional_format(
                            1, 0, max_row, len(raw_headers) - 1,
                            {
                                "type": "formula",
                                "criteria": f'=ISNUMBER(SEARCH("gắn",${action_letter}2))',
                                "format": gan_fill,
                            },
                        )
                        ws.conditional_format(
                            1, 0, max_row, len(raw_headers) - 1,
                            {
                                "type": "formula",
                                "criteria": f'=ISNUMBER(SEARCH("tháo",${action_letter}2))',
                                "format": thao_fill,
                            },
                        )
                    if "has_multiple_promotions_at_position" in raw_headers and max_row:
                        flag_col = raw_headers.index("has_multiple_promotions_at_position")
                        ws.conditional_format(
                            1, flag_col, max_row, flag_col,
                            {
                                "type": "cell", "criteria": "==",
                                "value": True, "format": warning_fill,
                            },
                        )
                    ws.protect("", {"autofilter": True, "sort": True})

                if sheet_name == "POG không có CTKM":
                    ws.hide()

            for metadata_name, metadata in (
                ("POG metadata", pog_metadata),
                ("KM metadata", km_metadata),
            ):
                if metadata is None or metadata.empty:
                    continue
                metadata.to_excel(writer, sheet_name=metadata_name, index=False)
                ws = writer.sheets[metadata_name]
                ws.hide()
                ws.freeze_panes(1, 0)

        return str(output_path)

    exporter.export_final_report = export_final_report_slim
    # main_core.run_pipeline holds the same exporter module object, so replacing
    # the module callable is sufficient for all backend CTKM jobs.
    core_module.app.state.slim_output_contract_v1 = True
    core_module.app.state.ctkm_output_profile = "production-slim"
