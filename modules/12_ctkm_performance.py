# -*- coding: utf-8 -*-
"""Performance helpers for the CTKM pipeline without changing business semantics."""
from __future__ import annotations

import pandas as pd


def build_ctkm_clearance_confirmation_fast(df_ctkm, df_clearance, *, make_item_key):
    """Build the CTKM/Clearance confirmation sheet without whole-frame scans.

    The previous implementation filtered the complete combined DataFrame once
    per row, which approaches O(n^2). Here we build a small index by
    ``(item_key, source)`` once and compare only campaigns for the same SKU.
    """
    columns = [
        "item_id", "item_key", "item_name", "promo_uom", "campaign_name",
        "campaign_detail", "promo_from", "promo_to", "channel", "normal_price",
        "promo_price", "product_type", "source_sheet",
    ]

    def tagged(frame: pd.DataFrame, source: str) -> pd.DataFrame:
        result = frame.copy()
        existing_row_ids = (
            result["source_row_id"].copy()
            if "source_row_id" in result.columns
            else pd.Series(pd.NA, index=result.index)
        )
        for column in columns:
            if column not in result.columns:
                result[column] = pd.NA
        result["item_key"] = result["item_id"].map(make_item_key)
        result = result.loc[:, columns]
        result.insert(0, "nguon_chuong_trinh", source)

        row_ids = []
        for position, (sheet, existing) in enumerate(
            zip(result["source_sheet"], existing_row_ids), start=2,
        ):
            sheet_name = "Sheet1" if pd.isna(sheet) or not str(sheet).strip() else str(sheet)
            fallback = f"{sheet_name}:{position}"
            raw = fallback if pd.isna(existing) or not str(existing).strip() else str(existing).strip()
            row_ids.append(raw if raw.startswith(f"{source}:") else f"{source}:{raw}")
        result["source_row_id"] = row_ids
        return result

    ctkm = tagged(df_ctkm, "CTKM")
    if df_clearance is None or df_clearance.empty:
        result = ctkm
        result.insert(1, "trang_thai_doi_chieu", "Chỉ CTKM")
        result["quan_he_thoi_gian"] = "Không có nguồn còn lại để đối chiếu"
    else:
        clearance = tagged(df_clearance, "CLEARANCE")
        ctkm_items = set(ctkm["item_key"].dropna())
        clearance_items = set(clearance["item_key"].dropna())
        both = ctkm_items & clearance_items
        result = pd.concat([ctkm, clearance], ignore_index=True)
        result.insert(1, "trang_thai_doi_chieu", [
            "Có cả CTKM và Clearance" if item in both
            else ("Chỉ CTKM" if source == "CTKM" else "Chỉ Clearance")
            for item, source in zip(result["item_key"], result["nguon_chuong_trinh"])
        ])

        parsed_from = pd.to_datetime(result["promo_from"], errors="coerce")
        parsed_to = pd.to_datetime(result["promo_to"], errors="coerce")
        interval_index: dict[tuple[object, str], list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
        for item, source, start, end in zip(
            result["item_key"], result["nguon_chuong_trinh"], parsed_from, parsed_to
        ):
            if pd.isna(item) or pd.isna(start) or pd.isna(end):
                continue
            interval_index.setdefault((item, source), []).append((start, end))

        relations = []
        for item, source, row_from, row_to in zip(
            result["item_key"], result["nguon_chuong_trinh"], parsed_from, parsed_to
        ):
            if not item or item not in both:
                relations.append("Không có nguồn còn lại để đối chiếu")
                continue
            if pd.isna(row_from) or pd.isna(row_to):
                relations.append("Thiếu ngày - cần xác nhận")
                continue
            other_source = "CLEARANCE" if source == "CTKM" else "CTKM"
            relation = "Khác thời gian"
            for other_from, other_to in interval_index.get((item, other_source), ()):
                if row_from == other_from and row_to == other_to:
                    relation = "Trùng thời gian - cần xác nhận"
                    break
                if row_from <= other_to and other_from <= row_to:
                    relation = "Chồng lấn thời gian - cần xác nhận"
            relations.append(relation)
        result["quan_he_thoi_gian"] = relations

    result.insert(2, "xac_nhan_ap_dung", "Chưa xác nhận")
    result.insert(3, "ghi_chu_xac_nhan", "")
    return result.sort_values(
        ["trang_thai_doi_chieu", "item_id", "nguon_chuong_trinh", "promo_from"],
        kind="stable", na_position="last",
    ).reset_index(drop=True)
