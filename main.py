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
    aliases = ("kenh ap dung", "channel", "kenh ban", "sales channel", "key channel")
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

def _process(sheet_name, df, schema_section, mapping_logs, is_fact, all_warnings, mapping_override=None):
    if mapping_override:
        result = _build_manual_mapping_result(sheet_name, mapping_override, df, schema_section)
        mapping_logs.append({**MC.mapping_result_to_dict_safe(result), "sheet_name": sheet_name})
        mapping = result.mapping
    else:
        mapping = _get_or_map(sheet_name, df, schema_section, mapping_logs)
    if is_fact:
        mapping = _ensure_channel_mapping(mapping, df)
        mapping = _ensure_promo_uom_mapping(mapping, df)
    df = NM.apply_mapping(df, mapping)
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
                 selected_output_columns=None, pog_sheet_name=None) -> PipelineResult:
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
    )

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
    )
    df_pog  = NM.attach_pog_snapshot_month(df_pog, pog_snapshot_month)

    # --- Buoc 8a: Quet overlap TRUOC khi loc thang (tren toan bo CTKM) ---
    overlap_warns = RC.detect_campaign_time_overlaps(df_ctkm_all)
    df_fefo_actions = RC.build_fefo_action_frame(df_ctkm_all, target_month, df_pog)

    # --- Buoc 6: Kiem tra lech thang + loc ---
    alignment = TF.check_snapshot_alignment(target_month, pog_snapshot_month)
    if not alignment.is_aligned:
        if fail_on_month_mismatch:
            raise ValueError(alignment.warning_message)
        warnings.append(alignment.warning_message)
    _df_all, df_ctkm_strict = TF.filter_ctkm_by_month(df_ctkm_all, target_month)

    # --- Buoc 7: Join ---
    join_result = JN.join_ctkm_pog(df_ctkm_strict, df_pog)
    if dim_frames:
        join_result = JN.apply_dimension_conditions(join_result, dim_frames)

    # --- Buoc 8b: Tong hop so lieu ---
    report = RC.build_reconciliation_report(
        join_result.df_matched, join_result.df_ctkm_only, join_result.df_pog_only, overlap_warns)

    summary = {
        "Thang bao cao":                    target_month,
        "Thang snapshot POG":               pog_snapshot_month or "(khong xac dinh duoc)",
        "So dong khop (Matched)":           report.matched_count,
        "So item duy nhat khop":            report.matched_unique_items,
        "So dong CTKM thieu vi tri ke":     report.ctkm_only_count,
        "So item CTKM thieu vi tri ke":     report.ctkm_only_unique_items,
        "  Trong do CTKM theo hoa don":     report.non_sku_ctkm_count,
        "So dong len ke thieu CTKM":        report.pog_only_count,
        "So item len ke thieu CTKM":        report.pog_only_unique_items,
        "So canh bao trung thoi gian":      len({warning.item_id for warning in overlap_warns}),
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
    )
    return PipelineResult(final, warnings, summary)


def _cli():
    p = argparse.ArgumentParser(description="Tong hop CTKM + POG theo thang.")
    p.add_argument("--ctkm",         required=True)
    p.add_argument("--pog",          required=True)
    p.add_argument("--month",        required=True, help="YYYY-MM, vd 2026-05")
    p.add_argument("--ctkm-sheet",    default=None, help="Ten sheet CTKM tong hop can xu ly")
    p.add_argument("--output",       default=None)
    p.add_argument("--strict-month", action="store_true",
                   help="Dung pipeline ngay neu lech thang POG/CTKM (mac dinh: chi canh bao)")
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
    result = run_pipeline(args.ctkm, args.pog, args.month, out, args.strict_month, args.ctkm_sheet)
    print(f"Da xuat: {result.output_filepath}")
    for w in result.warnings: print(f"CANH BAO: {w}")
    print("Tom tat:")
    for k, v in result.summary.items(): print(f"  {k}: {v}")

if __name__ == "__main__":
    _cli()
