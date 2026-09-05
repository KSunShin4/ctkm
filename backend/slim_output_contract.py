# -*- coding: utf-8 -*-
"""Render-only slim workbook export for heavy CTKM jobs.

The normal CLI/library exporter remains unchanged and can still emit the full
technical workbook. The backend installs this contract so production jobs write
only the sheets needed for store operations and action audit, avoiding the cost
of creating/styling diagnostic sheets that are not used at the counter.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

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
    "Audit hành động",
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
        location_review = location_issues.copy()

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
    """Keep Audit useful without the expensive per-cell body styling pass."""
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
        width = getattr(exporter, "_COLUMN_WIDTHS", {}).get(header, min(30, max(12, len(header) + 2)))
        ws.column_dimensions[exporter.get_column_letter(index)].width = width
    exporter._apply_bilingual_headers(ws)


def _trim_guide_to_slim_profile(workbook) -> None:
    """Remove cards linking to diagnostic sheets omitted by the slim profile."""
    ws = workbook["HƯỚNG DẪN"]
    rows_to_delete = []
    for row_idx in range(1, ws.max_row + 1):
        if ws.cell(row_idx, 1).value in {"POG cần review", "Xác nhận CTKM / Clearance"}:
            rows_to_delete.append(row_idx)
    for row_idx in reversed(rows_to_delete):
        ws.delete_rows(row_idx, 1)
    ws["D10"] = "Bản production slim: các sheet diagnostic không được tạo để giảm thời gian và RAM khi chạy trên Render."


def install_slim_output_contract(core_module) -> None:
    if getattr(core_module.app.state, "slim_output_contract_v1", False):
        return

    main_mod = core_module._main_mod
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
        del df_matched, df_ctkm_only, df_pog_only, overlap_warnings, mapping_logs
        del snapshot_alignment_warning, selected_output_columns
        del df_ctkm_clearance_confirmation, df_pog_review

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        align_task_summary_with_work_rows(reconciliation_summary, df_fefo_actions)
        total, gan, thao, wait, review, location_issues, location_review, audit = _prepare_frames(
            exporter, df_fefo_actions
        )

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            total.to_excel(writer, sheet_name="TỔNG HỢP - TEM", index=False)
            exporter._safe(gan, "Không có CTKM cần gắn tem.").to_excel(
                writer, sheet_name="Gắn tem", index=False
            )
            exporter._safe(thao, "Không có CTKM cần tháo tem.").to_excel(
                writer, sheet_name="Tháo tem", index=False
            )
            exporter._safe(wait, "Không có CTKM đang chờ đến ngày gắn.").to_excel(
                writer, sheet_name="Chờ gắn", index=False
            )
            exporter._safe(review, "Không có CTKM cần review.").to_excel(
                writer, sheet_name="Cần review", index=False
            )
            exporter._safe(
                location_issues, "Không có công việc nào cần kiểm tra vị trí POG."
            ).to_excel(writer, sheet_name="CTKM thieu vi tri ke", index=False)
            exporter._safe(
                location_review, "Không có vị trí POG nào cần review."
            ).to_excel(writer, sheet_name="POG cần kiểm tra", index=False)
            exporter._safe(audit, "Không có dữ liệu hành động để audit.").to_excel(
                writer, sheet_name="Audit hành động", index=False
            )

            business_date = (
                reconciliation_summary.get("Ngay nghiep vu")
                if isinstance(reconciliation_summary, dict) else None
            )
            for sheet_name, frame in (
                ("Gắn tem", gan), ("Tháo tem", thao),
                ("Chờ gắn", wait), ("Cần review", review),
            ):
                exporter._add_remaining_days_formula(
                    writer.sheets[sheet_name], frame, business_date, "so_ngay_con_lai"
                )

            exporter._create_guide_sheet(
                writer.book, gan, thao, wait, review, location_issues,
                reconciliation_summary, None, location_review, None,
            )
            _trim_guide_to_slim_profile(writer.book)

            styled_frames = (
                ("TỔNG HỢP - TEM", total),
                ("Gắn tem", gan), ("Tháo tem", thao),
                ("Chờ gắn", wait), ("Cần review", review),
                ("CTKM thieu vi tri ke", location_issues),
                ("POG cần kiểm tra", location_review),
            )
            for sheet_name, frame in styled_frames:
                ws = writer.sheets[sheet_name]
                exporter._apply_professional_style(ws, sheet_name, frame)
                if sheet_name != "TỔNG HỢP - TEM":
                    exporter._apply_alternating_shelf_colors(ws, frame)
                exporter._hide_technical_columns(
                    ws, action_sheet=sheet_name in {"Gắn tem", "Tháo tem", "Chờ gắn", "Cần review"}
                )
                exporter._apply_bilingual_headers(ws)

            for sheet_name in ("Gắn tem", "Tháo tem", "Chờ gắn", "Cần review"):
                exporter._configure_action_inputs(writer.sheets[sheet_name])

            _lightweight_audit_style(writer.sheets["Audit hành động"], exporter)

            writer.book._sheets = [
                writer.book[name] for name in SLIM_SHEET_ORDER if name in writer.book.sheetnames
            ]

        return str(output_path)

    exporter.export_final_report = export_final_report_slim
    # main_core.run_pipeline holds the same exporter module object, so replacing
    # the module callable is sufficient for all backend CTKM jobs.
    core_module.app.state.slim_output_contract_v1 = True
    core_module.app.state.ctkm_output_profile = "production-slim"
