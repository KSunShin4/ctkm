# -*- coding: utf-8 -*-
"""Reconciler entrypoint with source-safe business identity and overlap scope keys."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

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


_original_build_fefo_action_frame = _core.build_fefo_action_frame


def build_fefo_action_frame(*args, **kwargs):
    """Keep calendar action and POG applicability/review as independent axes.

    POG quality never changes ``scheduled_action``. Explicit invoice-level rows
    (``item_key == BILL``) remain valid CTKM calendar records, but POG does not
    apply to them. They therefore must not be reported as missing shelf locations.
    Source values and P-code promotions whose scheme text mentions a bill remain
    untouched and continue through normal POG matching.
    """
    result = _original_build_fefo_action_frame(*args, **kwargs)
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
        return result

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
    return result


_core._same_campaign_row = _same_promotion_identity
_core.detect_campaign_time_overlaps = detect_campaign_time_overlaps
_core.build_fefo_action_frame = build_fefo_action_frame

for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

_same_campaign_row = _core._same_campaign_row
detect_campaign_time_overlaps = _core.detect_campaign_time_overlaps
build_fefo_action_frame = _core.build_fefo_action_frame
