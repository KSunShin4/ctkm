# -*- coding: utf-8 -*-
"""Reconciler entrypoint with source-safe business identity and overlap scope keys."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd

_CORE_NAME = "_ctkm_reconciler_core"
_CORE_PATH = Path(__file__).with_name("reconciler_core.py")

if _CORE_NAME in sys.modules:
    _core = sys.modules[_CORE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(_CORE_NAME, _CORE_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Không nạp được reconciler core: {_CORE_PATH}")
    _core = importlib.util.module_from_spec(_spec)
    sys.modules[_CORE_NAME] = _core
    _spec.loader.exec_module(_core)

for _constant in ("_BUSINESS_COLUMNS", "_PROMOTION_ID_COLUMNS"):
    _columns = getattr(_core, _constant, None)
    if isinstance(_columns, list) and "key_channel" not in _columns:
        _index = _columns.index("channel") if "channel" in _columns else len(_columns)
        _columns.insert(_index, "key_channel")

# Replacement-code fields are visible source-derived context, but deliberately
# excluded from _PROMOTION_ID_COLUMNS so existing promotion identity remains
# anchored to the source Item code 2 / Item code contract.
_business_columns = getattr(_core, "_BUSINESS_COLUMNS", None)
if isinstance(_business_columns, list):
    for _field in ("new_item_id", "item_code_transition_status"):
        if _field not in _business_columns:
            _index = _business_columns.index("item_name") if "item_name" in _business_columns else len(_business_columns)
            _business_columns.insert(_index, _field)


def _same_promotion_identity(a: dict, b: dict) -> bool:
    """Use the exact same source fields as ``promotion_id`` for equality.

    Descriptive source fields such as item_name, product_type or source_sheet may
    legitimately differ while referring to the same promotion. They remain
    preserved on their source rows, but must not make overlap detection claim
    that one stable promotion conflicts with itself.
    """
    columns = [
        column for column in _core._PROMOTION_ID_COLUMNS
        if column in a or column in b
    ]
    return all(
        _core._fingerprint_value(a.get(column))
        == _core._fingerprint_value(b.get(column))
        for column in columns
    )


def _scope_key(value):
    """Normalize only for comparison; never write this key over source values."""
    return _core._normalize_text(value)


def detect_campaign_time_overlaps(df_ctkm):
    warnings = []
    if not {"item_id", "promo_from", "promo_to"}.issubset(df_ctkm.columns):
        return warnings

    df = _core._ensure_item_key(df_ctkm)
    df["_overlap_from"] = df["promo_from"].apply(_core._parse_date)
    df["_overlap_to"] = df["promo_to"].apply(_core._parse_date)
    df = df[df["_overlap_from"].notna() & df["_overlap_to"].notna()].copy()
    if df.empty:
        return warnings
    df = df[df["item_key"].apply(_core.is_sku)]
    df = _core._ensure_source_lineage(df)

    from itertools import combinations

    for item_key, grp in df.groupby("item_key"):
        if len(grp) < 2:
            continue
        rows = grp.to_dict("records")
        for a, b in combinations(rows, 2):
            af, at = a["_overlap_from"], a["_overlap_to"]
            bf, bt = b["_overlap_from"], b["_overlap_to"]
            if not (af <= bt and bf <= at):
                continue

            # Equality and stable promotion IDs must use one contract. Otherwise
            # the pipeline can assign the same promotion_id to two rows and then
            # simultaneously report those rows as conflicting campaigns.
            if _same_promotion_identity(a, b):
                continue

            ca = _core._display_value(a.get("campaign_name"), "(không rõ)")
            cb = _core._display_value(b.get("campaign_name"), "(không rõ)")
            source_a = _core._normalize_text(a.get("program_source"))
            source_b = _core._normalize_text(b.get("program_source"))
            cross_source_clearance = (
                source_a != source_b and {source_a, source_b} == {"ctkm", "clearance"}
            )

            # Compare derived scope keys, not raw source bytes. Pharmacity files
            # contain variants such as OFFLINE/Offline and ALL CHANNEL/All Channel.
            # KEY Channel is included when present because it represents the
            # application scope independently of the raw Channel label.
            channel_a_key = _scope_key(a.get("channel"))
            channel_b_key = _scope_key(b.get("channel"))
            key_channel_a_key = _scope_key(a.get("key_channel"))
            key_channel_b_key = _scope_key(b.get("key_channel"))

            same_channel_scope = channel_a_key == channel_b_key
            if key_channel_a_key or key_channel_b_key:
                same_channel_scope = (
                    same_channel_scope and key_channel_a_key == key_channel_b_key
                )

            is_blocking = cross_source_clearance or same_channel_scope
            conflict_type = (
                "blocking_conflict" if is_blocking
                else "potential_cross_channel_overlap"
            )
            warnings.append(_core.OverlapWarning(
                str(item_key), ca, cb,
                f"{af.date()} -> {at.date()}",
                f"{bf.date()} -> {bt.date()}",
                _core._display_value(a.get("channel")),
                _core._display_value(b.get("channel")),
                _core._display_value(a.get("source_row_id"), ""),
                _core._display_value(b.get("source_row_id"), ""),
                conflict_type,
                is_blocking,
            ))
    return warnings


def _replacement_key_map(frame: pd.DataFrame) -> tuple[dict[str, str], set[str], set[str]]:
    if frame is None or frame.empty or "new_item_id" not in frame.columns:
        return {}, set(), set()

    source_values = frame.get("item_key", frame.get("item_id", pd.Series(index=frame.index, dtype=object)))
    new_values = frame.get("new_item_key", frame["new_item_id"].map(_core._item_key))
    new_to_source: dict[str, set[str]] = {}
    source_to_new: dict[str, set[str]] = {}

    for source_value, new_value in zip(source_values, new_values):
        source = _core._item_key(source_value)
        new = _core._item_key(new_value)
        if not source or not new or source == new:
            continue
        if not _core.is_sku(source) or not _core.is_sku(new):
            continue
        new_to_source.setdefault(new, set()).add(source)
        source_to_new.setdefault(source, set()).add(new)

    ambiguous_new = {key for key, values in new_to_source.items() if len(values) != 1}
    ambiguous_source = {key for key, values in source_to_new.items() if len(values) != 1}
    mapping = {}
    for new, source_values_for_new in new_to_source.items():
        if new in ambiguous_new:
            continue
        source = next(iter(source_values_for_new))
        if source in ambiguous_source:
            continue
        mapping[new] = source
    return mapping, ambiguous_new, ambiguous_source


def _prepare_fact_transition_status(frame: pd.DataFrame):
    result = frame.copy()
    mapping, ambiguous_new, ambiguous_source = _replacement_key_map(result)
    if "new_item_id" not in result.columns:
        return result, mapping

    source_values = result.get("item_key", result.get("item_id", pd.Series(index=result.index, dtype=object)))
    new_values = result.get("new_item_key", result["new_item_id"].map(_core._item_key))
    statuses = []
    for source_value, new_value in zip(source_values, new_values):
        source = _core._item_key(source_value)
        new = _core._item_key(new_value)
        if not new:
            statuses.append("")
        elif not source:
            statuses.append("Có mã mới - mã nguồn trống")
        elif source == new:
            statuses.append("Mã mới trùng mã nguồn")
        elif new in ambiguous_new or source in ambiguous_source:
            statuses.append("Mơ hồ - không tự remap")
        elif mapping.get(new) == source:
            statuses.append("Có mã mới - đối chiếu song song")
        else:
            statuses.append("Mơ hồ - không tự remap")
    result["item_code_transition_status"] = statuses
    return result, mapping


def _remap_pog_replacement_keys(df_pog: pd.DataFrame | None, mapping: dict[str, str]):
    if df_pog is None or df_pog.empty or not mapping:
        return df_pog
    result = df_pog.copy()
    if "item_key" in result.columns:
        keys = result["item_key"].map(_core._item_key)
    elif "item_id" in result.columns:
        keys = result["item_id"].map(_core._item_key)
    else:
        return result
    result["item_key"] = keys.map(lambda value: mapping.get(value, value))
    return result


def _pog_source_item_lookup(df_pog: pd.DataFrame | None) -> dict[str, object]:
    if df_pog is None or df_pog.empty or "item_id" not in df_pog.columns:
        return {}
    lookup = {}
    has_lineage = "source_row_id" in df_pog.columns
    for position, (_, row) in enumerate(df_pog.iterrows(), start=2):
        if has_lineage:
            value = row.get("source_row_id")
            if value is None or pd.isna(value) or not str(value).strip():
                row_id = f"POG:Sheet1:{position}"
            else:
                raw = str(value).strip()
                row_id = raw if raw.startswith("POG:") else f"POG:{raw}"
        else:
            row_id = f"POG:Sheet1:{position}"
        lookup[row_id] = row.get("item_id")
    return lookup


def _attach_pog_match_code_diagnostics(result: pd.DataFrame, df_pog: pd.DataFrame | None):
    lookup = _pog_source_item_lookup(df_pog)
    if "pog_source_row_id" in result.columns:
        result["matched_pog_item_id"] = result["pog_source_row_id"].map(lookup)
    else:
        result["matched_pog_item_id"] = pd.NA

    labels = []
    for _, row in result.iterrows():
        applicable = row.get("pog_applicable", True)
        if applicable is False or str(applicable).strip().lower() == "false":
            labels.append("Không áp dụng POG")
            continue
        matched = _core._item_key(row.get("matched_pog_item_id"))
        if not matched:
            labels.append("")
            continue
        source = _core._item_key(row.get("item_key")) or _core._item_key(row.get("item_id"))
        new = _core._item_key(row.get("new_item_id"))
        if new and new != source and matched == new:
            labels.append("Khớp mã mới")
        elif source and matched == source:
            labels.append("Khớp mã nguồn")
        else:
            labels.append("Khớp alias chuyển mã")
    result["pog_match_code_type"] = labels
    return result


_original_build_fefo_action_frame = _core.build_fefo_action_frame


def _attach_position_promotion_diagnostics(result):
    """Surface multiple valid promotion tasks sharing one physical POG position.

    Different channel/scoped offers remain independent promotions and tasks. This
    diagnostic does not merge, block or reschedule them; it only tells the store
    operator that several promotion rows point at the same shelf position. Exact
    source duplicates that share one promotion_id count once.
    """
    result["promotion_count_at_position"] = 0
    result["has_multiple_promotions_at_position"] = False
    required = {
        "pog_position_id", "promotion_id", "scheduled_action",
        "location_completeness", "pog_applicable",
    }
    if not required.issubset(result.columns):
        return result

    eligible = (
        result["pog_applicable"].fillna(True).astype(bool)
        & result["location_completeness"].eq("Đủ vị trí")
    )
    if "pog_position_count" in result.columns:
        eligible &= result["pog_position_count"].fillna(0).astype(int).gt(0)
    if not eligible.any():
        return result

    working = result.loc[
        eligible, ["pog_position_id", "scheduled_action", "promotion_id"]
    ].copy()
    counts = working.groupby(
        ["pog_position_id", "scheduled_action"], dropna=False
    )["promotion_id"].transform("nunique")
    result.loc[eligible, "promotion_count_at_position"] = counts.astype(int).to_numpy()
    result.loc[eligible, "has_multiple_promotions_at_position"] = counts.gt(1).to_numpy()
    return result


def build_fefo_action_frame(df_ctkm, target_month, df_pog=None, *, business_date=None,
                            overlap_warnings=None):
    """Keep calendar action and POG applicability/review as independent axes.

    POG quality never changes ``scheduled_action``. Replacement-code matching is
    technical only: source Item code 2 / Item code remains the promotion identity,
    while POG can match either that source code or an unambiguous New P code.
    """
    fact_frame, replacement_map = _prepare_fact_transition_status(df_ctkm)
    remapped_pog = _remap_pog_replacement_keys(df_pog, replacement_map)
    result = _original_build_fefo_action_frame(
        fact_frame, target_month, remapped_pog,
        business_date=business_date, overlap_warnings=overlap_warnings,
    )
    if result is None or result.empty:
        return result
    required = {
        "location_completeness", "pog_month_status",
        "location_needs_review", "location_status",
    }
    if not required.issubset(result.columns):
        return result

    unknown_month = (
        result["location_completeness"].eq("Đủ vị trí")
        & result["pog_month_status"].eq("Không rõ tháng POG")
        & result["location_needs_review"].fillna(False).astype(bool)
    )
    result.loc[unknown_month, "location_status"] = "Không rõ tháng POG"

    item_keys = result.get("item_key")
    if item_keys is None:
        item_keys = result.get("item_id")
    if item_keys is None:
        result["pog_applicable"] = True
        result = _attach_pog_match_code_diagnostics(result, df_pog)
        return _attach_position_promotion_diagnostics(result)

    bill_mask = item_keys.apply(_core.is_bill_program)
    result["pog_applicable"] = ~bill_mask
    if bill_mask.any():
        # ``location_completeness`` remains the compatibility filter used by the
        # existing exporter to decide whether a row belongs to the missing-POG
        # sheet. For invoice-level CTKM the location requirement is satisfied by
        # non-applicability, while the explicit status fields carry the meaning.
        result.loc[bill_mask, "location_completeness"] = "Đủ vị trí"
        result.loc[bill_mask, "pog_month_status"] = "Không áp dụng POG"
        result.loc[bill_mask, "location_needs_review"] = False
        result.loc[bill_mask, "location_status"] = "Không áp dụng POG"
        if "has_multiple_pog_positions" in result.columns:
            result.loc[bill_mask, "has_multiple_pog_positions"] = False
        if "pog_position_count" in result.columns:
            result.loc[bill_mask, "pog_position_count"] = 0
        if "pog_source_row_count" in result.columns:
            result.loc[bill_mask, "pog_source_row_count"] = 0
        if "pog_duplicate_status" in result.columns:
            result.loc[bill_mask, "pog_duplicate_status"] = "Không áp dụng POG"

    result = _attach_pog_match_code_diagnostics(result, df_pog)
    return _attach_position_promotion_diagnostics(result)


_core._same_campaign_row = _same_promotion_identity
_core.detect_campaign_time_overlaps = detect_campaign_time_overlaps
_core.build_fefo_action_frame = build_fefo_action_frame

for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

_same_campaign_row = _core._same_campaign_row
detect_campaign_time_overlaps = _core.detect_campaign_time_overlaps
build_fefo_action_frame = _core.build_fefo_action_frame
