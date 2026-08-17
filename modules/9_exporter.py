# -*- coding: utf-8 -*-
"""Module 9: Exporter — xuat file Excel nhieu sheet tu ket qua pipeline."""
from __future__ import annotations
import unicodedata
from pathlib import Path
from typing import Optional
import pandas as pd
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter

_BILINGUAL_HEADERS = {
    "item_id": "Mã sản phẩm (Item code / ITEMID)",
    "item_name": "Tên sản phẩm (Product Name / ITEMNAME)",
    "promo_uom": "Đơn vị thuốc (Promo UoM)",
    "item_name__ctkm": "Tên sản phẩm CTKM (Product Name)",
    "item_name__pog": "Tên sản phẩm POG (ITEMNAME)",
    "store_id": "Cửa hàng (STOREID)",
    "pog_code": "Mã kệ (POGCODE)",
    "location_id": "Vị trí kệ (LOCATIONID)",
    "facing": "Số mặt trưng bày (TOTALFACING / facing)",
    "location_status": "Tình trạng vị trí (location_status)",
    "campaign_name": "Nhóm chương trình (Campaign)",
    "campaign_detail": "Chi tiết khuyến mãi (Scheme detail for customer)",
    "promo_from": "Ngày bắt đầu (From)",
    "promo_to": "Ngày kết thúc (To)",
    "normal_price": "Giá thường (Normal)",
    "promo_price": "Giá khuyến mãi (Promo)",
    "channel": "Kênh áp dụng (Channel)",
    "program_source": "Nguồn chương trình (CTKM / Clearance)",
    "ngay_gan_tem": "Ngày bắt đầu gắn tem",
    "ngay_thao_tem": "Ngày bắt đầu tháo tem",
    "action": "Công việc (action)",
    "so_ngay_con_lai": "Số ngày còn lại (công thức)",
    "processing_status": "Đã xử lý (processing_status)",
    "processed_by": "Người thực hiện (processed_by)",
    "processed_at": "Thời gian xử lý (processed_at)",
    "staff_note": "Ghi chú tại quầy (staff_note)",
}

def _safe(df, note):
    return df if (df is not None and not df.empty) else pd.DataFrame({"Ghi chu": [note]})


def _normalize_action_text(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))

def _matches_selected_column(column_name: str, selected_fields: set[str]) -> bool:
    if not selected_fields:
        return True
    base = str(column_name).split("__", 1)[0].strip().lower()
    exact = str(column_name).strip().lower()
    return base in selected_fields or exact in selected_fields

def _filter_selected_columns(df: pd.DataFrame, selected_columns) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    selected_fields = {str(c).strip().lower() for c in (selected_columns or []) if str(c).strip()}
    if not selected_fields:
        return df

    keep = [c for c in df.columns if _matches_selected_column(c, selected_fields)]
    if "item_id" in df.columns and "item_id" not in keep:
        keep.insert(0, "item_id")
    if "channel" in df.columns and "channel" not in keep:
        keep.append("channel")
    if not keep:
        return df
    return df.loc[:, [c for c in keep if c in df.columns]].copy()


def _prepare_action_sheet(df: pd.DataFrame) -> pd.DataFrame:
    """Sap xep danh sach theo thu tu duoc si di thao tac tren ke."""
    if df is None or df.empty:
        return df
    preferred = [
        "item_id", "item_name", "promo_uom", "program_source", "store_id", "channel", "pog_code", "location_id", "facing",
        "location_status", "campaign_name", "campaign_detail", "promo_from", "promo_to",
        "ngay_gan_tem", "ngay_thao_tem", "so_ngay_con_lai", "action", "processing_status", "processed_by", "processed_at",
        "staff_note", "reason", "target_month",
        "pog_snapshot_month", "source_sheet",
    ]
    ordered = [col for col in preferred if col in df.columns]
    ordered.extend(col for col in df.columns if col not in ordered)
    result = df.loc[:, ordered].copy()
    sort_cols = [col for col in ["store_id", "pog_code", "location_id", "item_id"] if col in result.columns]
    if sort_cols:
        result = result.sort_values(sort_cols, kind="stable", na_position="last")
    return result.reset_index(drop=True)


def _add_work_tracking_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return df
    result = df.copy()
    for col in ["processing_status", "processed_by", "processed_at", "staff_note"]:
        if col not in result.columns:
            result[col] = ""
    if not result.empty:
        result["processing_status"] = "Chưa xử lý"
    return result


def _apply_bilingual_headers(ws) -> None:
    for cell in ws[1]:
        raw = str(cell.value or "")
        base = raw.split("__", 1)[0]
        exact_label = _BILINGUAL_HEADERS.get(raw)
        base_label = _BILINGUAL_HEADERS.get(base)
        if exact_label:
            cell.value = exact_label
        elif base_label:
            cell.value = base_label if raw == base else f"{base_label.split(' (', 1)[0]} ({raw})"


def _apply_alternating_shelf_colors(ws, df: pd.DataFrame | None) -> None:
    """Tô cùng màu cho một kệ và đổi màu khi chuyển sang kệ kế tiếp."""
    if ws is None or df is None or df.empty:
        return
    shelf_keys = [key for key in ("store_id", "pog_code") if key in df.columns]
    if len(shelf_keys) < 2:
        return

    colors = ("EAF3FF", "FFF4E5")
    shelf_color_index: dict[tuple[str, ...], int] = {}
    for offset, (_, row) in enumerate(df.iterrows(), start=2):
        shelf = tuple("" if pd.isna(row[key]) else str(row[key]).strip() for key in shelf_keys)
        if not all(shelf):
            continue
        if shelf not in shelf_color_index:
            shelf_color_index[shelf] = len(shelf_color_index) % len(colors)
        fill = PatternFill(fill_type="solid", fgColor=colors[shelf_color_index[shelf]])
        for column in range(1, ws.max_column + 1):
            ws.cell(row=offset, column=column).fill = fill


def _hide_technical_columns(ws, *, action_sheet: bool = False) -> None:
    technical_exact = {"reason", "target_month", "source_sheet", "pog_snapshot_month"}
    for idx, cell in enumerate(ws[1], start=1):
        header = str(cell.value or "")
        if header.startswith("extra__") or header.startswith("source_sheet__") or (
            action_sheet and header in technical_exact
        ):
            ws.column_dimensions[get_column_letter(idx)].hidden = True


def _configure_action_inputs(ws) -> None:
    headers = [str(cell.value or "") for cell in ws[1]]
    if "processing_status" not in headers:
        return
    status_col = headers.index("processing_status") + 1
    editable = [name for name in ["processing_status", "processed_by", "processed_at", "staff_note"] if name in headers]
    validation = DataValidation(
        type="list",
        formula1='"Chưa xử lý,Đã xong,Không tìm thấy,Không thực hiện được"',
        allow_blank=False,
    )
    validation.error = "Hãy chọn một trạng thái trong danh sách."
    validation.errorTitle = "Trạng thái không hợp lệ"
    ws.add_data_validation(validation)
    if ws.max_row >= 2:
        status_letter = get_column_letter(status_col)
        validation.add(f"{status_letter}2:{status_letter}{ws.max_row}")
        full_range = f"A2:{get_column_letter(ws.max_column)}{ws.max_row}"
        ws.conditional_formatting.add(
            full_range,
            FormulaRule(formula=[f'${status_letter}2="Đã xong"'],
                        fill=PatternFill(fill_type="solid", fgColor="E2F0D9")),
        )
        ws.conditional_formatting.add(
            full_range,
            FormulaRule(formula=[f'${status_letter}2="Không tìm thấy"'],
                        fill=PatternFill(fill_type="solid", fgColor="FFC7CE")),
        )

    for name in editable:
        col_idx = headers.index(name) + 1
        for row_idx in range(2, ws.max_row + 1):
            ws.cell(row=row_idx, column=col_idx).protection = Protection(locked=False)
            ws.cell(row=row_idx, column=col_idx).fill = PatternFill(fill_type="solid", fgColor="FFF2CC")
            if name == "processed_at":
                ws.cell(row=row_idx, column=col_idx).number_format = "dd/mm/yyyy hh:mm"
    ws.protection.autoFilter = True
    ws.protection.sort = True
    ws.protection.sheet = True


def _configure_confirmation_inputs(ws) -> None:
    headers = [str(cell.value or "") for cell in ws[1]]
    if "xac_nhan_ap_dung" not in headers:
        return
    confirm_col = headers.index("xac_nhan_ap_dung") + 1
    validation = DataValidation(
        type="list",
        formula1='"Chưa xác nhận,Áp dụng CTKM,Áp dụng Clearance,Áp dụng cả hai,Không áp dụng"',
        allow_blank=False,
    )
    validation.error = "Hãy chọn một trạng thái xác nhận trong danh sách."
    validation.errorTitle = "Trạng thái không hợp lệ"
    ws.add_data_validation(validation)
    if ws.max_row >= 2:
        letter = get_column_letter(confirm_col)
        validation.add(f"{letter}2:{letter}{ws.max_row}")
        for row_idx in range(2, ws.max_row + 1):
            ws.cell(row_idx, confirm_col).fill = PatternFill(fill_type="solid", fgColor="FFF2CC")
            ws.cell(row_idx, confirm_col).protection = Protection(locked=False)
        note_col = headers.index("ghi_chu_xac_nhan") + 1
        for row_idx in range(2, ws.max_row + 1):
            ws.cell(row_idx, note_col).fill = PatternFill(fill_type="solid", fgColor="FFF2CC")
            ws.cell(row_idx, note_col).protection = Protection(locked=False)
    ws.protection.autoFilter = True
    ws.protection.sort = True
    ws.protection.sheet = True


def _create_guide_sheet(workbook, df_gan, df_thao, df_ctkm_only, summary,
                        df_confirmation=None) -> None:
    ws = workbook.create_sheet("HƯỚNG DẪN", 0)
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = "1F4E78"
    ws.merge_cells("A1:F2")
    title = ws["A1"]
    title.value = "DANH SÁCH THAO TÁC TEM KHUYẾN MÃI"
    title.font = Font(size=18, bold=True, color="FFFFFF")
    title.fill = PatternFill(fill_type="solid", fgColor="1F4E78")
    title.alignment = Alignment(horizontal="center", vertical="center")

    target_month = summary.get("Thang bao cao", "") if isinstance(summary, dict) else ""
    ws["A4"] = "Tháng báo cáo"
    ws["B4"] = target_month
    ws["D4"] = "Cách sử dụng"
    ws["D4"].font = Font(bold=True, color="1F4E78")
    instructions = [
        "1. Mở sheet Gắn tem hoặc Tháo tem.",
        "2. Tự bật bộ lọc trong Excel và lọc Kênh áp dụng phù hợp; hệ thống không tự loại CTKM Online/Offline.",
        "3. Lọc tiếp theo Cửa hàng → Mã kệ → Vị trí kệ.",
        "4. Thực hiện tại quầy và cập nhật các ô màu vàng; không sửa ô dữ liệu khác.",
    ]
    for offset, instruction in enumerate(instructions, start=5):
        ws.cell(offset, 4, instruction)

    cards = [
        ("Gắn tem", len(df_gan) if df_gan is not None else 0, "E2F0D9", "Gắn tem"),
        ("Tháo tem", len(df_thao) if df_thao is not None else 0, "FCE4D6", "Tháo tem"),
        ("Thiếu vị trí kệ", len(df_ctkm_only) if df_ctkm_only is not None else 0, "FFC7CE", "CTKM thieu vi tri ke"),
        ("Xác nhận CTKM / Clearance", len(df_confirmation) if df_confirmation is not None else 0,
         "DDEBF7", "Xác nhận CTKM Clearance"),
    ]
    for row_idx, (label, count, color, target) in enumerate(cards, start=6):
        cell = ws.cell(row_idx, 1, label)
        cell.hyperlink = f"#'{target}'!A1"
        cell.style = "Hyperlink"
        cell.fill = PatternFill(fill_type="solid", fgColor=color)
        cell.font = Font(bold=True, color="1F1F1F")
        ws.cell(row_idx, 2, count).fill = PatternFill(fill_type="solid", fgColor=color)
        ws.cell(row_idx, 2).font = Font(size=14, bold=True)

    ws["A11"] = "Chú giải"
    ws["A11"].font = Font(bold=True, color="1F4E78")
    legends = [("Xanh", "Cần gắn tem", "E8F5E9"), ("Cam", "Cần tháo tem", "FFF3E0"),
               ("Đỏ", "Thiếu vị trí kệ", "FFC7CE"), ("Vàng", "Ô dược sĩ được nhập", "FFF2CC")]
    for row_idx, (label, meaning, color) in enumerate(legends, start=12):
        ws.cell(row_idx, 1, label).fill = PatternFill(fill_type="solid", fgColor=color)
        ws.cell(row_idx, 2, meaning)
    for col, width in {"A": 24, "B": 22, "C": 4, "D": 48, "E": 16, "F": 16}.items():
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A4"


def _add_remaining_days_formula(ws, df: pd.DataFrame, formula_col_name: str = "so_ngay_con_lai"):
    if df is None or df.empty:
        return
    if formula_col_name not in df.columns:
        return

    headers = [ws.cell(row=1, column=i).value for i in range(1, ws.max_column + 1)]
    try:
        col_from = headers.index("promo_from") + 1
        col_to = headers.index("promo_to") + 1
        col_formula = headers.index(formula_col_name) + 1
    except ValueError:
        return

    for row_idx in range(2, len(df) + 2):
        col_from_letter = get_column_letter(col_from)
        col_to_letter = get_column_letter(col_to)
        formula = (
            f'=IF(OR({col_from_letter}{row_idx}="",{col_to_letter}{row_idx}=""),"",'
            f'MAX(0,{col_to_letter}{row_idx}-TODAY()))'
        )
        ws.cell(row=row_idx, column=col_formula, value=formula)


def _apply_professional_style(ws, sheet_name: str, df: pd.DataFrame | None = None):
    if ws is None:
        return

    thin = Side(border_style="thin", color="D0D7DE")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")
    alt_fill = PatternFill(fill_type="solid", fgColor="F7F9FC")
    accent_fill = PatternFill(fill_type="solid", fgColor="EAF7EA")

    ws.freeze_panes = "C2" if sheet_name in {"Gắn tem", "Tháo tem"} else "A2"
    # Không ghi AutoFilter vào file xuất. Một số phiên bản Excel xử lý vùng lọc
    # do openpyxl tạo không ổn định; người dùng sẽ tự bật bộ lọc khi cần.
    ws.auto_filter.ref = None
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "1:1"
    ws.sheet_properties.outlinePr.summaryBelow = True

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border

    max_row = ws.max_row
    max_col = ws.max_column
    for row_idx in range(2, max_row + 1):
        for col_idx in range(1, max_col + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            if cell.value is None:
                continue
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            cell.border = border
            if row_idx % 2 == 0:
                cell.fill = alt_fill
            else:
                cell.fill = PatternFill(fill_type="solid", fgColor="FFFFFF")

            if isinstance(cell.value, str) and cell.value.startswith("="):
                cell.number_format = "0"

            if cell.coordinate and col_idx <= max_col:
                header = ws.cell(row=1, column=col_idx).value
                if isinstance(header, str) and header.lower() in {
                    "promo_from", "promo_to", "ngay_gan_tem", "ngay_thao_tem"
                }:
                    if isinstance(cell.value, (pd.Timestamp,)):
                        cell.number_format = "dd/mm/yyyy"
                    elif isinstance(cell.value, str):
                        try:
                            pd.to_datetime(cell.value)
                            cell.number_format = "dd/mm/yyyy"
                        except Exception:
                            pass

    if sheet_name in {"Gắn tem", "Tháo tem"}:
        ws.sheet_properties.tabColor = "2E7D32"
        action_col_idx = None
        for idx, header in enumerate([ws.cell(row=1, column=i).value for i in range(1, max_col + 1)], start=1):
            if isinstance(header, str) and header.lower() == "action":
                action_col_idx = idx
                break
        if action_col_idx:
            for row_idx in range(2, max_row + 1):
                value = ws.cell(row=row_idx, column=action_col_idx).value or ""
                if isinstance(value, str) and "gắn" in value.lower():
                    for col_idx in range(1, max_col + 1):
                        ws.cell(row=row_idx, column=col_idx).fill = PatternFill(fill_type="solid", fgColor="E8F5E9")
                elif isinstance(value, str) and "tháo" in value.lower():
                    for col_idx in range(1, max_col + 1):
                        ws.cell(row=row_idx, column=col_idx).fill = PatternFill(fill_type="solid", fgColor="FFF3E0")

        headers = [ws.cell(row=1, column=i).value for i in range(1, max_col + 1)]
        if "location_status" in headers:
            status_col_idx = headers.index("location_status") + 1
            for row_idx in range(2, max_row + 1):
                status_cell = ws.cell(row=row_idx, column=status_col_idx)
                if isinstance(status_cell.value, str) and "thiếu" in status_cell.value.lower():
                    status_cell.fill = PatternFill(fill_type="solid", fgColor="FFC7CE")
                    status_cell.font = Font(bold=True, color="9C0006")

    color_map = {
        "Tong hop": "4F81BD",
        "CTKM thieu vi tri ke": "C0504D",
        "Len ke thieu CTKM": "9BBB59",
        "Gắn tem": "2E7D32",
        "Tháo tem": "F28C00",
        "Canh bao trung thoi gian": "C79B00",
        "Xác nhận CTKM Clearance": "00A6A6",
        "Mapping log": "5B5EA6",
        "Tom tat": "6F42C1",
    }
    ws.sheet_properties.tabColor = color_map.get(sheet_name, "4F81BD")

    for col_idx in range(1, max_col + 1):
        values = [ws.cell(row=row_idx, column=col_idx).value for row_idx in range(1, max_row + 1)]
        text_values = [str(v) for v in values if v is not None]
        width = min(60, max(12, max((len(t) for t in text_values), default=10) + 2))
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    for row_idx in range(2, max_row + 1):
        ws.row_dimensions[row_idx].height = 22


def export_final_report(output_path, df_matched, df_ctkm_only, df_pog_only,
                         overlap_warnings, mapping_logs, reconciliation_summary,
                         snapshot_alignment_warning=None,
                         selected_output_columns=None,
                         df_fefo_actions=None,
                         df_ctkm_clearance_confirmation=None) -> str:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    # Luôn có Kênh áp dụng trên các sheet để dược sĩ lọc công việc tại cửa hàng.
    for frame in (df_matched, df_ctkm_only, df_pog_only):
        if frame is not None and "channel" not in frame.columns:
            frame["channel"] = ""
    if df_pog_only is not None and "channel" in df_pog_only.columns:
        # Sheet này không có bản ghi CTKM tương ứng nên không thể có kênh áp dụng.
        # Ghi rõ trạng thái thay vì để ô trống khiến người dùng tưởng thiếu cột.
        blank_channel = df_pog_only["channel"].isna() | df_pog_only["channel"].astype(str).str.strip().eq("")
        df_pog_only.loc[blank_channel, "channel"] = "KHÔNG CÓ CTKM"
    df_matched = _filter_selected_columns(df_matched, selected_output_columns)
    df_ctkm_only = _filter_selected_columns(df_ctkm_only, selected_output_columns)
    df_pog_only = _filter_selected_columns(df_pog_only, selected_output_columns)
    if df_fefo_actions is not None and not df_fefo_actions.empty:
        # Không lọc theo channel: giữ nguyên mọi kênh để người dùng tự quyết định
        # bằng bộ lọc Excel, tránh bỏ sót do tên kênh không đồng nhất trong file công ty.
        action_norm = df_fefo_actions["action"].apply(_normalize_action_text)
        df_fefo_gan = df_fefo_actions[action_norm.isin({"gan tem", "gan tem fefo"})].copy()
        df_fefo_thao = df_fefo_actions[action_norm.isin({"thao tem", "thao tem fefo", "thao rem fefo"})].copy()
    else:
        df_fefo_gan = pd.DataFrame(columns=["item_id", "item_name", "promo_uom", "program_source", "campaign_name", "campaign_detail",
                                            "promo_from", "promo_to", "channel", "source_sheet",
                                            "action", "reason", "target_month"])
        df_fefo_thao = df_fefo_gan.copy()

    for df in (df_fefo_gan, df_fefo_thao):
        if df is not None and "so_ngay_con_lai" not in df.columns:
            df["so_ngay_con_lai"] = ""

    df_fefo_gan = _prepare_action_sheet(_add_work_tracking_columns(df_fefo_gan))
    df_fefo_thao = _prepare_action_sheet(_add_work_tracking_columns(df_fefo_thao))

    if overlap_warnings:
        pair_rows = [{
            "item_id": x.item_id,
            "cap_xung_dot": f"{x.campaign_a} [{x.channel_a}] ↔ {x.campaign_b} [{x.channel_b}]",
            "thoi_gian": f"{x.period_a} ↔ {x.period_b}",
        } for x in overlap_warnings]
        grouped_rows = []
        for item_id, group in pd.DataFrame(pair_rows).groupby("item_id", sort=False):
            grouped_rows.append({
                "item_id": item_id,
                "so_cap_chuong_trinh_can_kiem_tra": len(group),
                "cac_chuong_trinh_va_kenh": " | ".join(dict.fromkeys(group["cap_xung_dot"])),
                "cac_khoang_thoi_gian": " | ".join(dict.fromkeys(group["thoi_gian"])),
            })
        df_ov = pd.DataFrame(grouped_rows)
    else:
        df_ov = pd.DataFrame({"Ghi chu": ["Khong phat hien campaign nao trung thoi gian."]})

    with pd.ExcelWriter(output_path, engine="openpyxl") as w:
        _safe(df_matched,   "Khong co dong nao co ca CTKM va vi tri ke.").to_excel(w, sheet_name="Tong hop", index=False)
        _safe(df_ctkm_only, "Khong co CTKM nao thieu vi tri ke.").to_excel(w, sheet_name="CTKM thieu vi tri ke", index=False)
        _safe(df_pog_only,  "Khong co vi tri ke nao thieu CTKM.").to_excel(w, sheet_name="Len ke thieu CTKM", index=False)
        _safe(df_fefo_gan,  "Không có CTKM cần gắn tem.").to_excel(w, sheet_name="Gắn tem", index=False)
        _safe(df_fefo_thao, "Không có CTKM cần tháo tem.").to_excel(w, sheet_name="Tháo tem", index=False)
        df_ov.to_excel(w, sheet_name="Canh bao trung thoi gian", index=False)
        _safe(
            df_ctkm_clearance_confirmation,
            "Không có dữ liệu CTKM hoặc Clearance để xác nhận.",
        ).to_excel(w, sheet_name="Xác nhận CTKM Clearance", index=False)

        _add_remaining_days_formula(w.sheets["Gắn tem"], df_fefo_gan, "so_ngay_con_lai")
        _add_remaining_days_formula(w.sheets["Tháo tem"], df_fefo_thao, "so_ngay_con_lai")

        if mapping_logs:
            rows = []
            for log in mapping_logs:
                sn = log.get("sheet_name",""); src = log.get("source","")
                low = set(log.get("low_confidence_fields",[]))
                for col, fn in log.get("mapping",{}).items():
                    rows.append({"sheet":sn,"cot_goc":col,"canonical_field":fn,
                                 "confidence":log.get("confidence",{}).get(col),
                                 "can_review": col in low, "nguon": src})
                for col in log.get("unmapped",[]):
                    rows.append({"sheet":sn,"cot_goc":col,"canonical_field":"(KHONG MAP DUOC)",
                                 "confidence":None,"can_review":True,"nguon":src})
            pd.DataFrame(rows).to_excel(w, sheet_name="Mapping log", index=False)
        else:
            pd.DataFrame({"Ghi chu":["Chua co mapping log."]}).to_excel(w, sheet_name="Mapping log", index=False)

        summary_rows = [{"Chi so": k, "Gia tri": v} for k, v in reconciliation_summary.items()]
        if snapshot_alignment_warning:
            summary_rows.append({"Chi so": "CANH BAO LECH THANG", "Gia tri": snapshot_alignment_warning})
        pd.DataFrame(summary_rows).to_excel(w, sheet_name="Tom tat", index=False)

        # Tao trang bat dau danh cho nguoi thao tac, sau khi tat ca sheet dich da co.
        _create_guide_sheet(
            w.book, df_fefo_gan, df_fefo_thao, df_ctkm_only,
            reconciliation_summary, df_ctkm_clearance_confirmation,
        )

        sheet_frames = [
            ("Tong hop", df_matched),
            ("CTKM thieu vi tri ke", df_ctkm_only),
            ("Len ke thieu CTKM", df_pog_only),
            ("Gắn tem", df_fefo_gan),
            ("Tháo tem", df_fefo_thao),
            ("Canh bao trung thoi gian", df_ov),
            ("Xác nhận CTKM Clearance", df_ctkm_clearance_confirmation),
            ("Mapping log", None),
            ("Tom tat", None),
        ]
        for sheet_name, df in sheet_frames:
            if sheet_name in w.sheets:
                _apply_professional_style(w.sheets[sheet_name], sheet_name, df)

        # Phân biệt ranh giới kệ trên mọi sheet có đủ Cửa hàng + Mã kệ.
        for sheet_name, df in sheet_frames:
            if sheet_name in w.sheets:
                _apply_alternating_shelf_colors(w.sheets[sheet_name], df)

        for action_sheet in ["Gắn tem", "Tháo tem"]:
            _configure_action_inputs(w.sheets[action_sheet])
        _configure_confirmation_inputs(w.sheets["Xác nhận CTKM Clearance"])

        # Giu ten ky thuat trong ngoac de doi chieu, chi an cot audit thay vi xoa.
        for sheet_name in [name for name, _ in sheet_frames]:
            if sheet_name not in w.sheets:
                continue
            ws = w.sheets[sheet_name]
            _hide_technical_columns(ws, action_sheet=sheet_name in {"Gắn tem", "Tháo tem"})
            if sheet_name not in {"Mapping log", "Tom tat", "Canh bao trung thoi gian"}:
                _apply_bilingual_headers(ws)

        # Thu tu uu tien cong viec tai quay; cac sheet ky thuat van duoc giu lai.
        preferred_order = [
            "HƯỚNG DẪN", "Gắn tem", "Tháo tem", "CTKM thieu vi tri ke",
            "Tong hop", "Len ke thieu CTKM", "Canh bao trung thoi gian",
            "Xác nhận CTKM Clearance", "Tom tat", "Mapping log",
        ]
        w.book._sheets = [w.book[name] for name in preferred_order if name in w.book.sheetnames]
        w.book["Mapping log"].sheet_state = "hidden"

    return str(output_path)
