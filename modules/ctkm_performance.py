# -*- coding: utf-8 -*-
"""Drop-in CTKM performance, fidelity and presentation patches."""
from __future__ import annotations

import sys

import pandas as pd

from modules.item_code_identity import build_transition_identity
from modules.mapping_validation import validate_manual_mapping


USER_ACTION_COLUMNS = [
    "key_channel", "channel", "item_id", "item_name", "promo_uom",
    "pog_code", "location_id", "facing",
    "scheduled_action", "action", "ngay_gan_tem", "ngay_thao_tem", "so_ngay_con_lai",
    "campaign_name", "campaign_detail", "promo_from", "promo_to",
    "normal_price", "promo_price", "product_type",
    "store_id", "program_source",
    "location_completeness", "location_status", "location_needs_review", "reason",
    "processing_status", "processed_by", "processed_at", "staff_note",
]

TECHNICAL_ACTION_COLUMNS = [
    "task_id", "task_ids", "promotion_id", "pog_position_id", "item_key",
    "scope_identity_key", "operational_promotion_key", "operational_task_key",
    "new_item_key", "transition_match_key",
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
        for column in (selected_columns or []) if str(column).strip()
    }
    if not selected_fields:
        return df

    def matches(column_name: str) -> bool:
        base = str(column_name).split("__", 1)[0].strip().lower()
        exact = str(column_name).strip().lower()
        return base in selected_fields or exact in selected_fields

    keep = [column for column in df.columns if matches(column)]
    pinned = [column for column in ("key_channel", "channel", "item_id") if column in df.columns]
    keep = [column for column in keep if column not in pinned]
    return df.loc[:, [*pinned, *[column for column in keep if column in df.columns]]].copy()


def _lineage_parts(value) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [part.strip() for part in str(value).split("|") if part.strip()]


def _unique_lineage(group: pd.DataFrame, plural: str, singular: str) -> list[str]:
    values: list[str] = []
    if plural in group.columns:
        for value in group[plural]:
            values.extend(_lineage_parts(value))
    if singular in group.columns:
        for value in group[singular]:
            values.extend(_lineage_parts(value))
    return list(dict.fromkeys(values))


def _usable_key(value) -> str | None:
    if value is None or pd.isna(value) or not str(value).strip():
        return None
    return str(value).strip()


def unique_work_tracking_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Return one editable row per operational task, retaining source task IDs.

    ``task_id`` remains the source-faithful stable identity. When the only
    difference is Channel/KEY Channel formatting, reconciler emits one shared
    ``operational_task_key``. Interactive sheets consolidate on that derived key;
    Audit hành động still keeps every original task/source row.
    """
    if df is None:
        return df
    result = df.copy()
    if "task_id" in result.columns and "task_ids" not in result.columns:
        result["task_ids"] = result["task_id"]

    if not result.empty and "task_id" in result.columns:
        groups: dict[tuple[str, object], list[object]] = {}
        for position, (idx, row) in enumerate(result.iterrows()):
            operational = _usable_key(row.get("operational_task_key"))
            task = _usable_key(row.get("task_id"))
            if operational:
                key = ("operational", operational)
            elif task:
                key = ("task", task)
            else:
                key = ("row", position)
            groups.setdefault(key, []).append(idx)

        rows = []
        for key, indices in groups.items():
            group = result.loc[indices]
            first = group.iloc[0].copy()
            if key[0] != "row" and len(group) > 1:
                source_ids = _unique_lineage(group, "source_row_ids", "source_row_id")
                if source_ids:
                    if "source_row_id" in result.columns:
                        first["source_row_id"] = source_ids[0]
                    if "source_row_ids" in result.columns:
                        first["source_row_ids"] = " | ".join(source_ids)
                    if "source_row_count" in result.columns:
                        first["source_row_count"] = len(source_ids)

                pog_ids = _unique_lineage(group, "pog_source_row_ids", "pog_source_row_id")
                if pog_ids:
                    if "pog_source_row_id" in result.columns:
                        first["pog_source_row_id"] = pog_ids[0]
                    if "pog_source_row_ids" in result.columns:
                        first["pog_source_row_ids"] = " | ".join(pog_ids)
                    if "pog_source_row_count" in result.columns:
                        first["pog_source_row_count"] = len(pog_ids)

                task_ids = list(dict.fromkeys(
                    key for key in group["task_id"].map(_usable_key).tolist() if key
                ))
                if "task_ids" in result.columns:
                    first["task_ids"] = " | ".join(task_ids)
                if "duplicate_status" in result.columns:
                    if len(task_ids) > 1 and key[0] == "operational":
                        first["duplicate_status"] = (
                            "Đã gom task khác ID nhưng cùng phạm vi vận hành; xem Audit hành động"
                        )
                    else:
                        first["duplicate_status"] = (
                            "Đã gom cùng task_id từ nhiều dòng nguồn; xem Audit hành động"
                        )
            rows.append(first.to_dict())
        result = pd.DataFrame(rows, columns=result.columns).reset_index(drop=True)

    for column in ["processing_status", "processed_by", "processed_at", "staff_note"]:
        if column not in result.columns:
            result[column] = ""
    if not result.empty:
        result["processing_status"] = "Chưa xử lý"
    return result


def align_task_summary_with_work_rows(summary: dict, df_fefo_actions: pd.DataFrame | None) -> dict:
    if not isinstance(summary, dict) or df_fefo_actions is None:
        return summary
    actions = df_fefo_actions.copy()
    if "in_report_scope" in actions.columns:
        actions = actions[actions["in_report_scope"].fillna(False).astype(bool)].copy()
    tasks = unique_work_tracking_rows(actions)
    scheduled = tasks.get(
        "scheduled_action", tasks.get("action", pd.Series(index=tasks.index, dtype=object)),
    )
    sources = tasks.get("program_source", pd.Series(index=tasks.index, dtype=object))
    if "So dong tem tu Clearance" in summary:
        summary["So dong tem tu Clearance"] = int(sources.eq("CLEARANCE").sum())
    if "So dong cho gan" in summary:
        summary["So dong cho gan"] = int(scheduled.eq("chờ gắn tem").sum())
    if "So dong can review" in summary:
        summary["So dong can review"] = int(scheduled.eq("review").sum())
    return summary


def hide_technical_columns(ws, *, get_column_letter, original_hide=None, action_sheet=False) -> None:
    if callable(original_hide):
        original_hide(ws, action_sheet=action_sheet)
    if ws is None or ws.max_row < 1:
        return
    technical = set(TECHNICAL_ACTION_COLUMNS)
    for index, cell in enumerate(ws[1], start=1):
        if str(cell.value or "").strip() in technical:
            ws.column_dimensions[get_column_letter(index)].hidden = True


def build_ctkm_clearance_confirmation_fast(df_ctkm, df_clearance, *, make_item_key):
    """Compare Monthly/Clearance by safe product-transition identity."""
    columns = [
        "item_id", "item_key", "new_item_id", "new_item_key",
        "item_code_transition_status", "transition_match_key",
        "item_name", "promo_uom", "key_channel", "channel",
        "campaign_name", "campaign_detail", "promo_from", "promo_to", "normal_price",
        "promo_price", "product_type", "source_sheet",
    ]
    transition_frames = [df_ctkm.copy()]
    if df_clearance is not None and not df_clearance.empty:
        transition_frames.append(df_clearance.copy())
    transition_input = pd.concat(transition_frames, ignore_index=True, sort=False)
    identity = build_transition_identity(
        transition_input,
        key_func=make_item_key,
        is_sku=lambda value: bool(
            value and str(value).upper().startswith("P") and str(value)[1:].isdigit()
        ),
    )

    def tagged(frame: pd.DataFrame, source: str) -> pd.DataFrame:
        result = frame.copy()
        existing_row_ids = (
            result["source_row_id"].copy()
            if "source_row_id" in result.columns else pd.Series(pd.NA, index=result.index)
        )
        for column in columns:
            if column not in result.columns:
                result[column] = pd.NA
        result["item_key"] = result["item_id"].map(make_item_key)
        result["new_item_key"] = result["new_item_id"].map(make_item_key)
        result["transition_match_key"] = result["item_key"].map(
            lambda value: identity.canonical(value, key_func=make_item_key)
        )
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
        ctkm_items = set(ctkm["transition_match_key"].dropna())
        clearance_items = set(clearance["transition_match_key"].dropna())
        both = ctkm_items & clearance_items
        result = pd.concat([ctkm, clearance], ignore_index=True)
        result.insert(1, "trang_thai_doi_chieu", [
            "Có cả CTKM và Clearance" if item in both
            else ("Chỉ CTKM" if source == "CTKM" else "Chỉ Clearance")
            for item, source in zip(result["transition_match_key"], result["nguon_chuong_trinh"])
        ])

        parsed_from = pd.to_datetime(result["promo_from"], errors="coerce")
        parsed_to = pd.to_datetime(result["promo_to"], errors="coerce")
        interval_index: dict[tuple[object, str], list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
        for item, source, start, end in zip(
            result["transition_match_key"], result["nguon_chuong_trinh"], parsed_from, parsed_to
        ):
            if pd.isna(item) or pd.isna(start) or pd.isna(end):
                continue
            interval_index.setdefault((item, source), []).append((start, end))

        relations = []
        for item, source, row_from, row_to in zip(
            result["transition_match_key"], result["nguon_chuong_trinh"], parsed_from, parsed_to
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
        ["trang_thai_doi_chieu", "transition_match_key", "item_id", "nguon_chuong_trinh", "promo_from"],
        kind="stable", na_position="last",
    ).reset_index(drop=True)


def build_promo_action_source_without_inference(df_ctkm: pd.DataFrame,
                                                df_clearance: pd.DataFrame | None) -> pd.DataFrame:
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
    return pd.concat([ctkm, clearance], ignore_index=True)


def install_performance_patches(main_mod) -> None:
    if getattr(main_mod, "_ctkm_performance_patched", False):
        return
    original_overlap = main_mod.RC.detect_campaign_time_overlaps
    original_hide = main_mod.EX._hide_technical_columns
    original_export = main_mod.EX.export_final_report

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
            ws, get_column_letter=main_mod.EX.get_column_letter,
            original_hide=original_hide, action_sheet=action_sheet,
        )

    def export_with_task_summary(*args, **kwargs):
        summary = kwargs.get("reconciliation_summary")
        if summary is None and len(args) > 6:
            summary = args[6]
        actions = kwargs.get("df_fefo_actions")
        align_task_summary_with_work_rows(summary, actions)
        return original_export(*args, **kwargs)

    for constant_name in ("_BUSINESS_COLUMNS", "_PROMOTION_ID_COLUMNS"):
        columns = getattr(main_mod.RC, constant_name, None)
        if isinstance(columns, list) and "key_channel" not in columns:
            channel_index = columns.index("channel") if "channel" in columns else len(columns)
            columns.insert(channel_index, "key_channel")

    main_mod._validate_manual_mapping = validate_manual_mapping
    main_mod._build_ctkm_clearance_confirmation = confirmation
    main_mod._build_promo_action_source = build_promo_action_source_without_inference
    main_mod._ensure_channel_mapping = channel_mapping
    main_mod.RC.detect_campaign_time_overlaps = overlap
    main_mod.EX._prepare_action_sheet = prepare_action_sheet_user_first
    main_mod.EX._filter_selected_columns = filter_selected_columns_keep_channels
    main_mod.EX._add_work_tracking_columns = unique_work_tracking_rows
    main_mod.EX._hide_technical_columns = hide_columns
    main_mod.EX.export_final_report = export_with_task_summary
    main_mod.EX._BILINGUAL_HEADERS["key_channel"] = "KEY Channel"
    main_mod.EX._BILINGUAL_HEADERS["channel"] = "Channel"
    main_mod.EX._BILINGUAL_HEADERS["promo_uom"] = "Đơn vị sản phẩm (Promo UoM)"

    # Install the presentation-only layer last so it wraps the already-hardened
    # exporter without changing reconciliation/business logic.
    from modules import ctkm_output_layout
    ctkm_output_layout.install_output_layout(main_mod, sys.modules[__name__])

    main_mod._ctkm_performance_patched = True
