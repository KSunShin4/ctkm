# -*- coding: utf-8 -*-
"""Module 7: Joiner — outer join CTKM x POG theo item_id, ap dieu kien DIMENSION."""
from __future__ import annotations
from dataclasses import dataclass
import re
import pandas as pd

_SKU_KEY_PAT = re.compile(r"^P\d+$")

@dataclass
class JoinResult:
    df_matched:   pd.DataFrame
    df_ctkm_only: pd.DataFrame
    df_pog_only:  pd.DataFrame
    df_pog_review: pd.DataFrame


def _item_key(value):
    if value is None or pd.isna(value):
        return None
    key = str(value).strip().upper()
    return key or None


def _is_sku_key(value) -> bool:
    key = _item_key(value)
    return bool(key and _SKU_KEY_PAT.fullmatch(key))


def _with_item_key(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "item_key" not in result.columns:
        result["item_key"] = result["item_id"].apply(_item_key)
    else:
        result["item_key"] = result["item_key"].apply(_item_key)
    return result


def _replacement_key_map(frame: pd.DataFrame) -> tuple[dict[str, str], set[str], set[str]]:
    """Return only one-to-one new-code -> source-code aliases.

    Source ``item_id``/``item_key`` stays canonical for reconciliation identity.
    A Pharmacity replacement code is only used as an additional lookup path when
    both directions are unambiguous and both values are real P-code SKUs.
    Ambiguous/non-SKU mappings are deliberately ignored rather than silently
    connecting unrelated rows.
    """
    if frame is None or frame.empty or "new_item_key" not in frame.columns:
        return {}, set(), set()

    new_to_source: dict[str, set[str]] = {}
    source_to_new: dict[str, set[str]] = {}
    for source_key, new_key in zip(frame.get("item_key", []), frame["new_item_key"]):
        source = _item_key(source_key)
        new = _item_key(new_key)
        if not source or not new or source == new:
            continue
        if not _is_sku_key(source) or not _is_sku_key(new):
            continue
        new_to_source.setdefault(new, set()).add(source)
        source_to_new.setdefault(source, set()).add(new)

    ambiguous_new = {key for key, values in new_to_source.items() if len(values) != 1}
    ambiguous_source = {key for key, values in source_to_new.items() if len(values) != 1}
    mapping = {}
    for new, source_values in new_to_source.items():
        if new in ambiguous_new:
            continue
        source = next(iter(source_values))
        if source in ambiguous_source:
            continue
        mapping[new] = source
    return mapping, ambiguous_new, ambiguous_source


def _remap_pog_replacement_keys(source_ctkm: pd.DataFrame, source_pog: pd.DataFrame) -> pd.DataFrame:
    result = source_pog.copy()
    mapping, _ambiguous_new, _ambiguous_source = _replacement_key_map(source_ctkm)
    if not mapping or "item_key" not in result.columns:
        return result
    result["item_key"] = result["item_key"].map(
        lambda value: mapping.get(_item_key(value), _item_key(value))
    )
    return result


def _add_display_item_id(frame: pd.DataFrame, *, prefer_ctkm: bool) -> pd.DataFrame:
    result = frame.copy()
    primary = "item_id__ctkm" if prefer_ctkm else "item_id__pog"
    secondary = "item_id__pog" if prefer_ctkm else "item_id__ctkm"
    if primary in result.columns:
        result["item_id"] = result[primary]
        if secondary in result.columns:
            result["item_id"] = result["item_id"].combine_first(result[secondary])
    return result


def _pog_control_row_kind(row: pd.Series) -> str | None:
    """Recognize export control rows without touching ordinary bad POG rows.

    Pharmacity POG exports contain populated footer/control rows such as the
    ``Applied filters ... DATEID`` metadata line and a ``Total`` line. Loader
    deliberately preserves every populated source row, so reconciliation must
    classify these known controls instead of treating them as missing/real SKUs.
    Source values and lineage remain untouched for audit.
    """
    texts = []
    for value in row.tolist():
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if text:
            texts.append(text)
    lowered = [text.lower() for text in texts]

    if any("applied filters" in text or "applied filter" in text or "dateid" in text
           for text in lowered):
        return "snapshot_metadata"

    item = _item_key(row.get("item_key")) or _item_key(row.get("item_id"))
    if item == "TOTAL":
        return "summary_total"
    if item is None and any(text in {"total", "grand total", "tổng", "tong"} for text in lowered):
        return "summary_total"
    return None


def join_ctkm_pog(df_ctkm, df_pog) -> JoinResult:
    if "item_id" not in df_ctkm.columns:
        raise ValueError("df_ctkm thieu cot 'item_id'.")
    if "item_id" not in df_pog.columns:
        raise ValueError("df_pog thieu cot 'item_id'.")
    source_ctkm = _with_item_key(df_ctkm)
    source_pog = _with_item_key(df_pog)
    source_pog = _remap_pog_replacement_keys(source_ctkm, source_pog)

    # Control rows are not business POG positions and must not distort POG-only
    # counts or appear as false missing-item review errors. Keep them attached to
    # the review frame as audit metadata so exporter can preserve them separately.
    control_kind = source_pog.apply(_pog_control_row_kind, axis=1)
    control_mask = control_kind.notna()
    pog_metadata = source_pog[control_mask].copy()
    if not pog_metadata.empty:
        pog_metadata["pog_control_kind"] = control_kind[control_mask].to_numpy()
    source_pog_business = source_pog[~control_mask].copy()

    pog_review = source_pog_business[source_pog_business["item_key"].isna()].copy()
    if not pog_review.empty:
        pog_review["reason"] = "thieu_ma_san_pham_pog"
    pog_review = pog_review.reset_index(drop=True)
    pog_review.attrs["pog_metadata"] = pog_metadata.reset_index(drop=True)

    overlap = (set(source_ctkm.columns) & set(source_pog_business.columns)) - {"item_key"}
    df_c = source_ctkm.rename(columns={c: f"{c}__ctkm" for c in overlap})
    df_p = source_pog_business.rename(columns={c: f"{c}__pog" for c in overlap})
    valid_c = df_c[df_c["item_key"].notna()].copy()
    invalid_c = df_c[df_c["item_key"].isna()].copy()
    valid_p = df_p[df_p["item_key"].notna()].copy()
    merged = pd.merge(valid_c, valid_p, on="item_key", how="outer", indicator=True)

    if not invalid_c.empty:
        for column in valid_p.columns:
            if column != "item_key" and column not in invalid_c.columns:
                invalid_c[column] = pd.NA
        invalid_c["_merge"] = "left_only"
        merged = pd.concat([merged, invalid_c.reindex(columns=merged.columns)], ignore_index=True)

    matched = _add_display_item_id(
        merged[merged["_merge"] == "both"].drop(columns=["_merge"]), prefer_ctkm=True,
    ).reset_index(drop=True)
    ctkm_only = _add_display_item_id(
        merged[merged["_merge"] == "left_only"].drop(columns=["_merge"]), prefer_ctkm=True,
    ).reset_index(drop=True)
    pog_only = _add_display_item_id(
        merged[merged["_merge"] == "right_only"].drop(columns=["_merge"]), prefer_ctkm=False,
    ).reset_index(drop=True)
    return JoinResult(matched, ctkm_only, pog_only, pog_review)

def apply_dimension_conditions(join_result: JoinResult, dimension_frames: dict) -> JoinResult:
    """
    Hien chi gan co 'dimension_check_flag' cho item KHONG xuat hien trong bat ky
    dimension sheet nao (neu co). KHONG tu dong loc bo - tranh mat du lieu do ap
    sai dieu kien (chua co co che biet dimension nao rang buoc cho campaign nao).
    """
    if not dimension_frames: return join_result
    df = join_result.df_matched.copy()
    if df.empty: return join_result
    item_dims = {n: _with_item_key(d) for n, d in dimension_frames.items()
                 if "item_id" in d.columns and d["item_id"].notna().any()}
    if not item_dims: return join_result
    all_dim_items = set()
    for d in item_dims.values():
        all_dim_items |= set(d["item_key"].dropna())
    df["dimension_check_flag"] = df["item_key"].apply(
        lambda x: "" if x in all_dim_items else "khong_xuat_hien_trong_dimension_sheet"
    )
    join_result.df_matched = df.reset_index(drop=True)
    return join_result
