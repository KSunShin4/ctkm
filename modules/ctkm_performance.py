# -*- coding: utf-8 -*-
"""Drop-in CTKM performance, fidelity and presentation patches.

Source workbook values are immutable. Normalization used for matching or business
logic is kept in technical keys/local variables and never written back over source
fields such as item_id, campaign, dates, prices, UoM, KEY Channel or Channel.
"""
from __future__ import annotations

import pandas as pd


USER_ACTION_COLUMNS = [
    "item_id", "item_name", "promo_uom", "program_source", "key_channel", "channel",
    "campaign_name", "campaign_detail", "promo_from", "promo_to",
    "normal_price", "promo_price", "product_type",
    "store_id", "pog_code", "location_id", "facing",
    "ngay_gan_tem", "ngay_thao_tem", "so_ngay_con_lai",
    "scheduled_action", "action", "location_completeness", "location_status",
    "location_needs_review", "reason",
    "processing_status", "processed_by", "processed_at", "staff_note",
]

TECHNICAL_ACTION_COLUMNS = [
    "task_id", "promotion_id", "pog_position_id", "item_key",
    "target_month", "business_date", "pog_snapshot_month", "pog_position_count",
    "source_sheet", "source_row_id", "source_row_ids", "source_row_count",
    "duplicate_status", "pog_source_row_id", "pog_source_row_ids",
    "pog_source_row_count", "pog_duplicate_status", "source_excel_row",
    "logical_row_id", "promo_slot_id",
]


def preserve_both_channel_mappings(mapping: dict, df: pd.DataFrame, *, normalize_header) -> dict:
    """Keep KEY Channel and Channel as two independent source fields."""
    result = dict(mapping)
    normalized_columns = {normalize_header(column): column for column in df.columns}
    key_source = normalized_columns.get("key channel")
    raw_source = normalized_columns.get("channel")
    apply_source = normalized_columns.get("kenh ap dung")

    for source in (key_source, raw_source):
        if source is not None:
            result.pop(source, None)

    if key_source is not None:
        result = {source: target for source, target in result.items() if target != "key_channel"}
        result[key_source] = "key_channel"

    if raw_source is not None:
        result = {source: target for source, target in result.items() if target != "channel"}
        result[raw_source] = "channel"
    elif apply_source is not None:
        result = {source: target for source, target in result.items() if target != "channel"}
        result[apply_source] = "channel"

    return result


def prepare_action_sheet_user_first(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    ordered = [column for column in USER_ACTION_COLUMNS if column in df.columns]
    middle = [
        column for column in df.columns
        if column not in ordered and column not in TECHNICAL_ACTION_COLUMNS
    ]
    technical = [column for column in TECHNICAL_ACTION_COLUMNS if column in df.columns]
    result = df.loc[:, [*ordered, *middle, *technical]].copy()
    sort_cols = [
        column for column in ("store_id", "pog_code", "location_id", "item_id")
        if column in result.columns
    ]
    if sort_cols:
        result = result.sort_values(sort_cols, kind="stable", na_position="last")
    return result.reset_index(drop=True)


def filter_selected_columns_keep_channels(df: pd.DataFrame, selected_columns) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    selected_fields = {
        str(column).strip().lower()
        for column in (selected_columns or [])
        if str(column).strip()
    }
    if not selected_fields:
        return df

    def matches(column_name: str) -> bool:
        base = str(column_name).split("__", 1)[0].strip().lower()
        exact = str(column_name).strip().lower()
        return base in selected_fields or exact in selected_fields

    keep = [column for column in df.columns if matches(column)]
    for column in ("item_id", "key_channel", "channel"):
        if column in df.columns and column not in keep:
            keep.append(column)
    return df.loc[:, [column for column in keep if column in df.columns]].copy()


def hide_technical_columns(ws, *, get_column_letter, original_hide=None, action_sheet=False) -> None:
    if callable(original_hide):
        original_hide(ws, action_sheet=action_sheet)
    if ws is None or ws.max_row < 1:
        return
    technical = set(TECHNICAL_ACTION_COLUMNS)
    for index, cell in enumerate(ws[1], start=1):
        header = str(cell.value or "").strip()
        if header in technical:
            ws.column_dimensions[get_column_letter(index)].hidden = True


def build_ctkm_clearance_confirmation_fast(df_ctkm, df_clearance, *, make_item_key):
    columns = [
        "item_id", "item_key", "item_name", "promo_uom", "key_channel", "channel",
        "campaign_name", "campaign_detail", "promo_from", "promo_to", "normal_price",
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
            if pd.isna(item) or item not in both:
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


def build_promo_action_source_without_inference(df_ctkm: pd.DataFrame,
                                                df_clearance: pd.DataFrame | None) -> pd.DataFrame:
    """Combine CTKM/Clearance without inventing or overwriting any source value."""
    ctkm = df_ctkm.copy()
    ctkm["program_source"] = "CTKM"
    if "source_row_id" in ctkm.columns:
        ctkm["source_row_id"] = ctkm["source_row_id"].map(
            lambda value: str(value) if str(value).startswith("CTKM:") else f"CTKM:{value}"
        )
    if df_clearance is None or df_clearance.empty:
        return ctkm

    clearance = df_clearance.copy()
    clearance["program_source"] = "CLEARANCE"
    if "source_row_id" in clearance.columns:
        clearance["source_row_id"] = clearance["source_row_id"].map(
            lambda value: str(value) if str(value).startswith("CLEARANCE:") else f"CLEARANCE:{value}"
        )
    # Deliberately do NOT fill blank campaign_name with "CLEARANCE". A blank
    # source value stays blank and will be classified into review by reconciler.
    return pd.concat([ctkm, clearance], ignore_index=True)


def install_performance_patches(main_mod) -> None:
    if getattr(main_mod, "_ctkm_performance_patched", False):
        return

    original_overlap = main_mod.RC.detect_campaign_time_overlaps
    original_hide = main_mod.EX._hide_technical_columns

    def confirmation(df_ctkm, df_clearance):
        return build_ctkm_clearance_confirmation_fast(
            df_ctkm, df_clearance, make_item_key=main_mod.NM.make_item_key,
        )

    def overlap(frame):
        collapse = getattr(main_mod.RC, "_collapse_exact_duplicates", None)
        prepared = collapse(frame) if callable(collapse) else frame
        return original_overlap(prepared)

    def channel_mapping(mapping, df):
        return preserve_both_channel_mappings(
            mapping, df, normalize_header=main_mod._normalized_header
        )

    def hide_columns(ws, *, action_sheet=False):
        return hide_technical_columns(
            ws,
            get_column_letter=main_mod.EX.get_column_letter,
            original_hide=original_hide,
            action_sheet=action_sheet,
        )

    # KEY Channel participates in duplicate identity and stable promotion IDs,
    # but its source value is never normalized/rewritten.
    for constant_name in ("_BUSINESS_COLUMNS", "_PROMOTION_ID_COLUMNS"):
        columns = getattr(main_mod.RC, constant_name, None)
        if isinstance(columns, list) and "key_channel" not in columns:
            channel_index = columns.index("channel") if "channel" in columns else len(columns)
            columns.insert(channel_index, "key_channel")

    main_mod._build_ctkm_clearance_confirmation = confirmation
    main_mod._build_promo_action_source = build_promo_action_source_without_inference
    main_mod._ensure_channel_mapping = channel_mapping
    main_mod.RC.detect_campaign_time_overlaps = overlap
    main_mod.EX._prepare_action_sheet = prepare_action_sheet_user_first
    main_mod.EX._filter_selected_columns = filter_selected_columns_keep_channels
    main_mod.EX._hide_technical_columns = hide_columns
    main_mod.EX._BILINGUAL_HEADERS["key_channel"] = "Phạm vi áp dụng (KEY Channel)"
    main_mod.EX._BILINGUAL_HEADERS["channel"] = "Kênh chương trình (Channel)"
    main_mod._ctkm_performance_patched = True
