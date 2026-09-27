# -*- coding: utf-8 -*-
"""
main.py — Orchestrator pipeline tong hop CTKM + POG.

CACH DUNG (CLI):
    python main.py --ctkm file_ctkm.xlsx --pog file_pog.xlsx --month 2026-05

CACH DUNG (tu code / frontend):
    from main import run_pipeline
    result = run_pipeline(ctkm_filepath=..., pog_filepath=..., target_month="2026-05",
                          output_path=..., fail_on_month_mismatch=False)
    print(result.output_filepath, result.warnings, result.summary)
"""
from __future__ import annotations
import argparse, importlib.util, sys, types, unicodedata
from dataclasses import dataclass, field as dc_field
from pathlib import Path
import pandas as pd

_ROOT = Path(__file__).resolve().parent
_MDIR = _ROOT / "modules"

try:
    from dotenv import load_dotenv; load_dotenv(_ROOT / ".env")
except ImportError: pass

def _boot():
    if "modules" not in sys.modules:
        pkg = types.ModuleType("modules")
        pkg.__path__ = [str(_MDIR)]
        sys.modules["modules"] = pkg

def _imp(filename, alias):
    full = f"modules.{alias}"
    spec = importlib.util.spec_from_file_location(full, _MDIR / filename)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    setattr(sys.modules["modules"], alias, mod)
    spec.loader.exec_module(mod)
    return mod

_boot()
cfg  = _imp("config_loader.py",       "config_loader")
L    = _imp("1_loader.py",            "loader")
SC   = _imp("2_sheet_classifier.py",  "classifier")
CM   = _imp("3_column_mapper.py",     "column_mapper")
MC   = _imp("4_mapping_cache.py",     "mapping_cache")
NM   = _imp("5_normalizer.py",        "normalizer")
TF   = _imp("6_time_filter.py",       "time_filter")
JN   = _imp("7_joiner.py",            "joiner")
RC   = _imp("8_reconciler.py",        "reconciler")
EX   = _imp("9_exporter.py",          "exporter")

SCHEMA = cfg.CANONICAL_SCHEMA

@dataclass
class PipelineResult:
    output_filepath: str
    warnings: list = dc_field(default_factory=list)
    summary:  dict = dc_field(default_factory=dict)

def list_ctkm_sheet_names(wb_ctkm):
    return [name for name, sheet in wb_ctkm.sheets.items() if not sheet.df.empty]

def _select_primary_ctkm_sheet(wb_ctkm, selected_sheet_name: str | None = None):
    """
    CTKM workbook thuong co 1 sheet tong hop chinh va nhieu sheet phu.
    Neu nguoi dung da chon sheet cu the thi dung dung sheet do.
    Neu khong co chon va chi co 1 sheet co du lieu, tu dong lay sheet do.
    Neu co nhieu sheet, bat nguoi dung chon ro rang thay vi ngam lay ngau nhien.
    """
    preferred_names = [
        "tổng hợp ctkm update",
        "tong hop ctkm update",
        "tổng hợp ctkm",
        "tong hop ctkm",
        "sheet1",
    ]

    non_empty = [(name, sheet) for name, sheet in wb_ctkm.sheets.items() if not sheet.df.empty]
    if not non_empty:
        raise ValueError("Khong tim thay sheet CTKM nao co du lieu trong file CTKM.")

    if selected_sheet_name:
        wanted = selected_sheet_name.strip().lower()
        for name, sheet in non_empty:
            if name.strip().lower() == wanted:
                return name, sheet
        available = ", ".join(name for name, _ in non_empty)
        raise ValueError(
            f"Khong tim thay sheet CTKM '{selected_sheet_name}'. Sheet co san: {available}"
        )

    if len(non_empty) == 1:
        return non_empty[0]

    for preferred in preferred_names:
        for name, sheet in non_empty:
            if preferred in name.strip().lower():
                return name, sheet

    available = ", ".join(name for name, _ in non_empty)
    raise ValueError(
        "Workbook CTKM co nhieu sheet co du lieu. Hay chon 1 sheet tong hop de tiep tuc: "
        f"{available}"
    )

def _get_or_map(sheet_name, df, schema_section, mapping_logs):
    cols = list(df.columns)
    prompt_version = cfg.GEMINI_CONFIG.get("prompt_version", "column-mapping-v2")
    cached = MC.get_cached_mapping(cols, schema_section, prompt_version)
    if cached:
        cached["source"] = "cache"
        entry = {**cached, "sheet_name": sheet_name}
        mapping_logs.append(entry)
        return cached["mapping"]
    result = CM.map_columns_with_gemini(sheet_name, df, schema_section)
    rdict  = MC.mapping_result_to_dict_safe(result)
    rdict["source"] = "gemini"
    MC.save_mapping(cols, MC.mapping_result_to_dict_safe(result), schema_section, prompt_version)
    mapping_logs.append({**rdict, "sheet_name": sheet_name})
    return result.mapping

def _validate_manual_mapping(mapping, df, schema_section):
    if not isinstance(mapping, dict):
        raise ValueError("Mapping thu cong phai la JSON object.")
    source_columns = {str(col) for col in df.columns}
    allowed_fields = {
        name for name, meta in schema_section.items() if not meta.get("auto_filled", False)
    }
    unknown_sources = sorted(set(mapping) - source_columns)
    invalid_targets = sorted({target for target in mapping.values() if target not in allowed_fields})
    if unknown_sources:
        raise ValueError(f"Mapping co cot nguon khong ton tai: {unknown_sources}")
    if invalid_targets:
        raise ValueError(f"Mapping co canonical field khong hop le: {invalid_targets}")
    return dict(mapping)

def _build_manual_mapping_result(sheet_name, mapping, df, schema_section):
    mapping = _validate_manual_mapping(mapping, df, schema_section)
    cols = list(df.columns)
    confidence = {col: 1.0 for col in mapping.keys()}
    unmapped = [col for col in cols if col not in mapping]
    return CM.ColumnMappingResult(
        sheet_name=sheet_name,
        mapping=mapping,
        confidence=confidence,
        unmapped=unmapped,
        low_confidence_fields=[],
        raw_response="manual-override",
        source="manual",
    )

def preview_mapping(sheet_name, df, schema_section, mapping_logs=None):
    local_logs = [] if mapping_logs is None else mapping_logs
    result_mapping = _get_or_map(sheet_name, df, schema_section, local_logs)
    return result_mapping, local_logs

def _normalized_header(value) -> str:
    text = unicodedata.normalize("NFD", str(value).strip().lower())
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).split())

def _ensure_channel_mapping(mapping: dict, df: pd.DataFrame) -> dict:
    """Nhận diện chắc chắn cột kênh khi mapping tay/Gemini bỏ sót."""
    mapping = dict(mapping)
    # File CTKM công ty có thể có đồng thời ``KEY Channel`` và
    # ``Channel``. KEY Channel mới là phạm vi áp dụng (ALL/OFFLINE/ONLINE),
    # còn Channel có thể chứa nhóm chương trình như COMBO ĐI SINH.
    # Vì vậy cột có nghĩa “áp dụng” phải được ưu tiên; tên
    # ``Channel`` trần chỉ là phương án cuối cùng.
    aliases = ("kenh ap dung", "key channel", "sales channel", "kenh ban", "channel")
    normalized_columns = {_normalized_header(column): column for column in df.columns}
    for alias in aliases:
        if alias in normalized_columns:
            preferred_source = normalized_columns[alias]
            # Ưu tiên Kênh áp dụng/Channel thay cho Sub channel nếu AI map nhầm.
            mapping = {source: target for source, target in mapping.items() if target != "channel"}
            mapping[preferred_source] = "channel"
            break
    return mapping

def _ensure_promo_uom_mapping(mapping: dict, df: pd.DataFrame) -> dict:
    """Luôn lấy đơn vị thuốc từ cột Promo UoM của file CTKM công ty."""
    mapping = dict(mapping)
    aliases = ("promo uom", "promotion uom", "promo unit", "don vi ctkm", "dvt ctkm")
    normalized_columns = {_normalized_header(column): column for column in df.columns}
    for alias in aliases:
        if alias in normalized_columns:
            preferred_source = normalized_columns[alias]
            mapping = {source: target for source, target in mapping.items() if target != "promo_uom"}
            mapping[preferred_source] = "promo_uom"
            break
    return mapping

def _infer_standard_fact_mapping(df: pd.DataFrame) -> dict:
    """Map cac cot CTKM/Clearance chuan cua cong ty ma khong can goi AI."""
    aliases = {
        "item code": "item_id", "item code 2": "item_id", "itemid": "item_id",
        "product name": "item_name", "itemname": "item_name",
        "promo uom": "promo_uom", "campaign": "campaign_name",
        "scheme detail for customer": "campaign_detail",
        "from": "promo_from", "to": "promo_to",
        "kenh ap dung": "channel", "key channel": "channel", "channel": "channel",
        "normal": "normal_price", "promo": "promo_price",
        "product type": "product_type",
    }
    mapping = {}
    claimed_targets = set()
    for column in df.columns:
        target = aliases.get(_normalized_header(column))
        if target and target not in claimed_targets:
            mapping[column] = target
            claimed_targets.add(target)
    required = {"item_id", "campaign_name", "promo_from", "promo_to"}
    return mapping if required.issubset(claimed_targets) else {}

def _build_ctkm_clearance_confirmation(df_ctkm: pd.DataFrame,
                                       df_clearance: pd.DataFrame | None) -> pd.DataFrame:
    """Tao danh sach de nguoi dung xac nhan CTKM va Clearance trong cung mot sheet."""
    columns = [
        "item_id", "item_key", "item_name", "promo_uom", "campaign_name", "campaign_detail",
        "promo_from", "promo_to", "channel", "normal_price", "promo_price",
        "product_type", "source_sheet",
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
        result["item_key"] = result["item_id"].apply(NM.make_item_key)
        result = result.loc[:, columns]
        result.insert(0, "nguon_chuong_trinh", source)
        row_ids = []
        for position, (sheet, existing) in enumerate(
            zip(result["source_sheet"], existing_row_ids), start=2,
        ):
            fallback = f"{'Sheet1' if pd.isna(sheet) or not str(sheet).strip() else str(sheet)}:{position}"
            raw = fallback if pd.isna(existing) or not str(existing).strip() else str(existing).strip()
            row_ids.append(raw if raw.startswith(f"{source}:") else f"{source}:{raw}")
        result["source_row_id"] = row_ids
        return result

    ctkm = tagged(df_ctkm, "CTKM")
    if df_clearance is None or df_clearance.empty:
        result = ctkm
        result.insert(1, "trang_thai_doi_chieu", "Chỉ CTKM")
    else:
        clearance = tagged(df_clearance, "CLEARANCE")
        ctkm_items = set(ctkm["item_key"].dropna())
        clearance_items = set(clearance["item_key"].dropna())
        both = ctkm_items & clearance_items
        result = pd.concat([ctkm, clearance], ignore_index=True)
        item_keys = result["item_key"]
        result.insert(1, "trang_thai_doi_chieu", [
            "Có cả CTKM và Clearance" if item in both
            else ("Chỉ CTKM" if source == "CTKM" else "Chỉ Clearance")
            for item, source in zip(item_keys, result["nguon_chuong_trinh"])
        ])

    def time_relation(row):
        both_items = both if df_clearance is not None and not df_clearance.empty else set()
        item = row.get("item_key")
        if not item or item not in both_items:
            return "Không có nguồn còn lại để đối chiếu"
        other_source = "CLEARANCE" if row["nguon_chuong_trinh"] == "CTKM" else "CTKM"
        candidates = result[
            result["item_key"].eq(item)
            & result["nguon_chuong_trinh"].eq(other_source)
        ]
        row_from = pd.to_datetime(row.get("promo_from"), errors="coerce")
        row_to = pd.to_datetime(row.get("promo_to"), errors="coerce")
        if pd.isna(row_from) or pd.isna(row_to):
            return "Thiếu ngày - cần xác nhận"
        relation = "Khác thời gian"
        for _, candidate in candidates.iterrows():
            other_from = pd.to_datetime(candidate.get("promo_from"), errors="coerce")
            other_to = pd.to_datetime(candidate.get("promo_to"), errors="coerce")
            if pd.isna(other_from) or pd.isna(other_to):
                continue
            if row_from == other_from and row_to == other_to:
                return "Trùng thời gian - cần xác nhận"
            if row_from <= other_to and other_from <= row_to:
                relation = "Chồng lấn thời gian - cần xác nhận"
        return relation

    result["quan_he_thoi_gian"] = result.apply(time_relation, axis=1)

    result.insert(2, "xac_nhan_ap_dung", "Chưa xác nhận")
    result.insert(3, "ghi_chu_xac_nhan", "")
    return result.sort_values(
        ["trang_thai_doi_chieu", "item_id", "nguon_chuong_trinh", "promo_from"],
        kind="stable", na_position="last",
    ).reset_index(drop=True)


def _build_promo_action_source(df_ctkm: pd.DataFrame,
                               df_clearance: pd.DataFrame | None) -> pd.DataFrame:
    """Giữ đầy đủ CTKM và Clearance; không loại dữ liệu chỉ vì trùng SKU."""
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
    if "campaign_name" not in clearance.columns:
        clearance["campaign_name"] = "CLEARANCE"
    else:
        blank_campaign = (
            clearance["campaign_name"].isna()
            | clearance["campaign_name"].astype(str).str.strip().eq("")
        )
        clearance.loc[blank_campaign, "campaign_name"] = "CLEARANCE"
    return pd.concat([ctkm, clearance], ignore_index=True)

def _process(sheet_name, df, schema_section, mapping_logs, is_fact, all_warnings,
             mapping_override=None, mapping_source=None,
             source_excel_rows=None, source_prefix=None):
    df = df.copy()
    excel_rows = list(source_excel_rows or range(2, len(df) + 2))
    if len(excel_rows) != len(df):
        raise ValueError(f"Không khớp lineage dòng Excel cho sheet '{sheet_name}'.")
    log_index = None
    if mapping_override:
        result = _build_manual_mapping_result(sheet_name, mapping_override, df, schema_section)
        mapping = result.mapping
        log_entry = {
            **MC.mapping_result_to_dict_safe(result),
            "source": mapping_source or getattr(result, "source", None) or "manual",
            "sheet_name": sheet_name,
        }
    else:
        before_logs = len(mapping_logs)
        mapping = _get_or_map(sheet_name, df, schema_section, mapping_logs)
        if len(mapping_logs) > before_logs:
            log_index = len(mapping_logs) - 1
        log_entry = None
    if is_fact:
        mapping = _ensure_channel_mapping(mapping, df)
        mapping = _ensure_promo_uom_mapping(mapping, df)

    # Mapping log must describe the mapping that was actually applied after all
    # deterministic fidelity corrections, while preserving the true provenance.
    final_unmapped = [str(column) for column in df.columns if column not in mapping]
    if log_entry is not None:
        log_entry["mapping"] = dict(mapping)
        log_entry["unmapped"] = final_unmapped
        confidence = dict(log_entry.get("confidence") or {})
        for source in mapping:
            confidence.setdefault(source, 1.0)
        log_entry["confidence"] = confidence
        mapping_logs.append(log_entry)
    elif log_index is not None:
        mapping_logs[log_index]["mapping"] = dict(mapping)
        mapping_logs[log_index]["unmapped"] = final_unmapped
        confidence = dict(mapping_logs[log_index].get("confidence") or {})
        for source in mapping:
            confidence.setdefault(source, 1.0)
        mapping_logs[log_index]["confidence"] = confidence
    df = NM.apply_mapping(df, mapping)
    df["source_excel_row"] = excel_rows
    source_label = f"{source_prefix}:" if source_prefix else ""
    df["source_row_id"] = [f"{source_label}{sheet_name}:{row}" for row in excel_rows]
    df = NM.clean_values(df)
    if is_fact:
        df, unpivot_warns = NM.unpivot_multi_promo(df)
        for w in unpivot_warns:
            all_warnings.append(f"[Sheet '{sheet_name}'] {w}")
    df = NM.attach_source_sheet(df, sheet_name)
    return df

def run_pipeline(ctkm_filepath, pog_filepath, target_month, output_path,
                 fail_on_month_mismatch=False, ctkm_sheet_name=None,
                 ctkm_mapping_override=None, pog_mapping_override=None,
                 selected_output_columns=None, pog_sheet_name=None,
                 clearance_filepath=None, clearance_sheet_name=None,
                 clearance_mapping_override=None,
                 business_date=None,
                 ctkm_mapping_source=None, pog_mapping_source=None,
                 clearance_mapping_source=None) -> PipelineResult:
    warnings, mapping_logs = [], []

    # --- Buoc 1: Load ---
    wb_ctkm = L.load_workbook_raw(
        ctkm_filepath, is_pog_file=False,
        selected_sheet_names=[ctkm_sheet_name] if ctkm_sheet_name else None,
    )
    wb_pog  = L.load_workbook_raw(
        pog_filepath, is_pog_file=True,
        selected_sheet_names=[pog_sheet_name] if pog_sheet_name else None,
    )
    if not wb_pog.sheets:
        raise ValueError(f"File POG '{pog_filepath}' khong co sheet nao co du lieu.")
    pog_snapshot_month = wb_pog.pog_snapshot_month

    # --- Buoc 2-4: Chi xu ly 1 sheet CTKM tong hop chinh ---
    primary_ctkm_name, primary_ctkm_sheet = _select_primary_ctkm_sheet(wb_ctkm, ctkm_sheet_name)
    if len(list_ctkm_sheet_names(wb_ctkm)) > 1:
        warnings.append(
            f"Chi xu ly sheet CTKM tong hop chinh '{primary_ctkm_name}', bo qua cac sheet phu con lai."
        )
    df_ctkm_all = _process(
        primary_ctkm_name,
        primary_ctkm_sheet.df,
        SCHEMA["fact_fields"],
        mapping_logs,
        True,
        warnings,
        mapping_override=ctkm_mapping_override,
        mapping_source=ctkm_mapping_source,
        source_excel_rows=primary_ctkm_sheet.source_excel_rows,
        source_prefix="CTKM",
    )
    df_ctkm_all["program_source"] = "CTKM"

    df_clearance_all = None
    if clearance_filepath:
        wb_clearance = L.load_workbook_raw(
            clearance_filepath, is_pog_file=False,
            selected_sheet_names=[clearance_sheet_name] if clearance_sheet_name else None,
        )
        clearance_name, clearance_sheet = _select_primary_ctkm_sheet(
            wb_clearance, clearance_sheet_name
        )
        inferred_clearance = (
            {} if clearance_mapping_override else _infer_standard_fact_mapping(clearance_sheet.df)
        )
        clearance_override = clearance_mapping_override or inferred_clearance
        effective_clearance_source = (
            clearance_mapping_source
            or ("standard-fact" if inferred_clearance else None)
        )
        df_clearance_all = _process(
            clearance_name,
            clearance_sheet.df,
            SCHEMA["fact_fields"],
            mapping_logs,
            True,
            warnings,
            mapping_override=clearance_override or None,
            mapping_source=effective_clearance_source,
            source_excel_rows=clearance_sheet.source_excel_rows,
            source_prefix="CLEARANCE",
        )
        df_clearance_all["program_source"] = "CLEARANCE"

    dim_frames = {}

    # --- Chuan hoa POG ---
    pog_sn  = pog_sheet_name or next(iter(wb_pog.sheets))
    df_pog  = _process(
        pog_sn,
        wb_pog.sheets[pog_sn].df,
        SCHEMA["pog_fields"],
        mapping_logs,
        False,
        warnings,
        mapping_override=pog_mapping_override,
        mapping_source=pog_mapping_source,
        source_excel_rows=wb_pog.sheets[pog_sn].source_excel_rows,
        source_prefix="POG",
    )
    df_pog  = NM.attach_pog_snapshot_month(df_pog, pog_snapshot_month)

    # Danh sach thao tac tem phai gom ca Clearance, ke ca cac ma P khong co
    # trong file CTKM Monthly. Giu program_source de nguoi dung biet nguon.
    df_promo_for_actions = _build_promo_action_source(
        df_ctkm_all, df_clearance_all
    )

    # --- Buoc 8a: Quet overlap va tao thao tac tem tren CTKM + Clearance ---
    overlap_warns = RC.detect_campaign_time_overlaps(df_promo_for_actions)
    df_fefo_actions = RC.build_fefo_action_frame(
        df_promo_for_actions, target_month, df_pog,
        business_date=business_date, overlap_warnings=overlap_warns,
    )

    # --- Buoc 6: Kiem tra lech thang + loc ---
    alignment = TF.check_snapshot_alignment(target_month, pog_snapshot_month)
    if not alignment.is_aligned:
        if fail_on_month_mismatch:
            raise ValueError(alignment.warning_message)
        warnings.append(alignment.warning_message)
    _df_ctkm_relevant, df_ctkm_strict = TF.filter_ctkm_by_month(df_ctkm_all, target_month)
    if df_clearance_all is not None:
        _df_clearance_relevant, df_clearance_strict = TF.filter_ctkm_by_month(
            df_clearance_all, target_month
        )
    else:
        df_clearance_strict = None
    df_confirmation = _build_ctkm_clearance_confirmation(
        df_ctkm_all, df_clearance_all
    )

    # --- Buoc 7: Join ---
    join_result = JN.join_ctkm_pog(df_ctkm_strict, df_pog)
    if dim_frames:
        join_result = JN.apply_dimension_conditions(join_result, dim_frames)

    # --- Buoc 8b: Tong hop so lieu ---
    report = RC.build_reconciliation_report(
        join_result.df_matched, join_result.df_ctkm_only, join_result.df_pog_only, overlap_warns)

    if "in_report_scope" in df_fefo_actions.columns:
        actions_in_scope = df_fefo_actions[df_fefo_actions["in_report_scope"].fillna(False)].copy()
    else:
        actions_in_scope = df_fefo_actions
    location_issue_mask = ~actions_in_scope.get(
        "location_completeness",
        actions_in_scope.get("location_status", pd.Series("Đủ vị trí", index=actions_in_scope.index)),
    ).eq("Đủ vị trí")
    location_issues = actions_in_scope[location_issue_mask]
    location_review_mask = actions_in_scope.get(
        "location_needs_review", location_issue_mask,
    ).fillna(False).astype(bool)
    location_reviews = actions_in_scope[location_review_mask]
    effective_business_date = (
        df_fefo_actions["business_date"].dropna().iloc[0]
        if "business_date" in df_fefo_actions.columns and not df_fefo_actions["business_date"].dropna().empty
        else pd.to_datetime(business_date).normalize()
        if business_date is not None
        else pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).normalize()
    )
    unique_location_key = "item_key" if "item_key" in location_issues.columns else "item_id"

    summary = {
        "Thang bao cao":                    target_month,
        "Ngay nghiep vu":                   effective_business_date,
        "Thang snapshot POG":               pog_snapshot_month or "(khong xac dinh duoc)",
        "So dong khop (Matched)":           report.matched_count,
        "So item duy nhat khop":            report.matched_unique_items,
        "So dong CTKM thieu vi tri ke":     len(location_issues),
        "So item CTKM thieu vi tri ke":     location_issues[unique_location_key].nunique() if unique_location_key in location_issues else 0,
        "  Trong do CTKM theo hoa don":     report.non_sku_ctkm_count,
        "So dong CTKM thieu ma san pham":   report.missing_item_ctkm_count,
        "So dong CTKM sai dinh dang ma":    report.invalid_item_ctkm_count,
        "So dong POG khong co CTKM phu hop": report.pog_only_count,
        "So item POG khong co CTKM phu hop": report.pog_only_unique_items,
        "So canh bao trung thoi gian":      len({warning.item_id for warning in overlap_warns}),
        "So dong Clearance":                0 if df_clearance_strict is None else len(df_clearance_strict),
        "So item trung CTKM va Clearance":  0 if df_clearance_strict is None else len(
            set(df_ctkm_strict["item_key"].dropna())
            & set(df_clearance_strict["item_key"].dropna())
        ),
        "So dong tem tu Clearance":         int(
            (actions_in_scope.get("program_source", pd.Series(dtype=str)) == "CLEARANCE").sum()
        ),
        "So dong cho gan":                  int((actions_in_scope.get("scheduled_action", pd.Series(dtype=str)) == "chờ gắn tem").sum()),
        "So dong can review":               int((actions_in_scope.get("scheduled_action", pd.Series(dtype=str)) == "review").sum()),
        "So dong can kiem tra vi tri":       len(location_reviews),
    }

    # --- Buoc 9: Export ---
    final = EX.export_final_report(
        output_path=output_path,
        df_matched=join_result.df_matched,
        df_ctkm_only=join_result.df_ctkm_only,
        df_pog_only=join_result.df_pog_only,
        overlap_warnings=overlap_warns,
        mapping_logs=mapping_logs,
        reconciliation_summary=summary,
        snapshot_alignment_warning=alignment.warning_message,
        selected_output_columns=selected_output_columns,
        df_fefo_actions=df_fefo_actions,
        df_ctkm_clearance_confirmation=df_confirmation,
        df_pog_review=join_result.df_pog_review,
    )
    return PipelineResult(final, warnings, summary)


def _cli():
    p = argparse.ArgumentParser(description="Tong hop CTKM + POG theo thang.")
    p.add_argument("--ctkm",         required=True)
    p.add_argument("--pog",          required=True)
    p.add_argument("--month",        required=True, help="YYYY-MM, vd 2026-05")
    p.add_argument("--ctkm-sheet",    default=None, help="Ten sheet CTKM tong hop can xu ly")
    p.add_argument("--clearance",      default=None, help="File Clearance tuy chon")
    p.add_argument("--clearance-sheet", default=None, help="Ten sheet Clearance can xu ly")
    p.add_argument("--output",       default=None)
    p.add_argument("--strict-month", action="store_true",
                   help="Dung pipeline ngay neu lech thang POG/CTKM (mac dinh: chi canh bao)")
    p.add_argument("--business-date", default=None,
                   help="Ngay nghiep vu YYYY-MM-DD (mac dinh: ngay hien tai theo gio VN)")
    args = p.parse_args()
    if not args.ctkm_sheet:
        wb_ctkm = L.load_workbook_raw(args.ctkm, is_pog_file=False)
        sheet_names = list_ctkm_sheet_names(wb_ctkm)
        if len(sheet_names) > 1:
            print("CTKM workbook co nhieu sheet co du lieu:")
            for idx, name in enumerate(sheet_names, start=1):
                print(f"  {idx}. {name}")
            choice = input("Chon sheet can tong hop (nhap so thu tu hoac ten sheet): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(sheet_names):
                args.ctkm_sheet = sheet_names[int(choice) - 1]
            else:
                args.ctkm_sheet = choice
    out = args.output or str(_ROOT/"output"/f"tong_hop_ctkm_{args.month}.xlsx")
    result = run_pipeline(
        args.ctkm, args.pog, args.month, out, args.strict_month, args.ctkm_sheet,
        pog_sheet_name=None, clearance_filepath=args.clearance,
        clearance_sheet_name=args.clearance_sheet, business_date=args.business_date,
    )
    print(f"Da xuat: {result.output_filepath}")
    for w in result.warnings: print(f"CANH BAO: {w}")
    print("Tom tat:")
    for k, v in result.summary.items(): print(f"  {k}: {v}")

if __name__ == "__main__":
    _cli()
