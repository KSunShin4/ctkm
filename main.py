# -*- coding: utf-8 -*-
"""Public CTKM orchestrator entrypoint with fidelity contract installed eagerly."""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import sys

_CORE_NAME = "_ctkm_main_core"
_CORE_PATH = Path(__file__).with_name("main_core.py")

if _CORE_NAME in sys.modules:
    _core = sys.modules[_CORE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(_CORE_NAME, _CORE_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Không nạp được CTKM core: {_CORE_PATH}")
    _core = importlib.util.module_from_spec(_spec)
    sys.modules[_CORE_NAME] = _core
    _spec.loader.exec_module(_core)

# Install fidelity/correctness before exposing run_pipeline or helper functions.
# This makes `from main import run_pipeline` behave the same as backend/CLI.
_performance = importlib.import_module("modules.ctkm_performance")
_performance.install_performance_patches(_core)

# Standard company-file inference must obey the same two-channel contract even
# when this helper is used directly, before _process/_ensure_channel_mapping.
_original_infer_standard_fact_mapping = _core._infer_standard_fact_mapping
_original_get_or_map = _core._get_or_map


def _infer_standard_fact_mapping(df):
    mapping = _original_infer_standard_fact_mapping(df)

    # Real Clearance exports use "Campaign Detail" as the campaign label while
    # "Scheme detail for customer" remains the promotion/detail text. Only use
    # this fallback when a plain Campaign column is absent, so Monthly workbooks
    # that contain both columns keep their existing semantics unchanged.
    if not mapping:
        normalized_columns = {
            _core._normalized_header(column): column for column in df.columns
        }
        campaign_detail_source = normalized_columns.get("campaign detail")
        if "campaign" not in normalized_columns and campaign_detail_source is not None:
            inference_frame = df.rename(columns={campaign_detail_source: "Campaign"})
            mapping = _original_infer_standard_fact_mapping(inference_frame)
            if "Campaign" in mapping:
                campaign_target = mapping.pop("Campaign")
                mapping[campaign_detail_source] = campaign_target

    if not mapping:
        return mapping
    return _performance.preserve_both_channel_mappings(
        mapping, df, normalize_header=_core._normalized_header,
    )


def _infer_standard_pog_mapping(df):
    """Map the stable Pharmacity POG export headers without Gemini.

    The uploaded store export uses exact business headers such as STOREID,
    POGCODE, ITEMID, LOCATIONID and TOTALFACING. These names are unambiguous, so
    routing them through Gemini adds failure/quota risk without adding meaning.
    Unrecognized source columns are deliberately left unmapped; normalizer will
    preserve them as ``extra__...`` columns for audit/source fidelity.
    """
    normalized_columns = {}
    for column in df.columns:
        normalized_columns.setdefault(_core._normalized_header(column), column)

    aliases = {
        "item_id": ("itemid", "item id", "item code"),
        "item_name": ("itemname", "item name", "product name"),
        "store_id": ("storeid", "store id"),
        "pog_code": ("pogcode", "pog code"),
        "location_id": ("locationid", "location id"),
        "facing": ("totalfacing", "total facing", "facing"),
    }
    mapping = {}
    for target, target_aliases in aliases.items():
        for alias in target_aliases:
            source = normalized_columns.get(alias)
            if source is not None:
                mapping[source] = target
                break

    # Do not bypass Gemini/cache for a vaguely similar workbook. ITEMID+STOREID
    # together identify the standard POG shape used by the real Pharmacity file.
    if not {"item_id", "store_id"}.issubset(set(mapping.values())):
        return {}
    return mapping


def _get_or_map(sheet_name, df, schema_section, mapping_logs):
    is_pog_schema = (
        "store_id" in schema_section
        and "pog_code" in schema_section
        and "campaign_name" not in schema_section
    )
    if is_pog_schema:
        mapping = _infer_standard_pog_mapping(df)
        if mapping:
            result = _core._build_manual_mapping_result(
                sheet_name, mapping, df, schema_section
            )
            entry = _core.MC.mapping_result_to_dict_safe(result)
            entry["source"] = "standard-pog"
            mapping_logs.append({**entry, "sheet_name": sheet_name})
            return result.mapping
    return _original_get_or_map(sheet_name, df, schema_section, mapping_logs)


_core._infer_standard_fact_mapping = _infer_standard_fact_mapping
_core._infer_standard_pog_mapping = _infer_standard_pog_mapping
_core._get_or_map = _get_or_map

for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

if __name__ == "__main__":
    _core._cli()
