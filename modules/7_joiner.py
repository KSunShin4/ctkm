# -*- coding: utf-8 -*-
"""Module 7: Joiner — outer join CTKM x POG theo item_id, ap dieu kien DIMENSION."""
from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

@dataclass
class JoinResult:
    df_matched:   pd.DataFrame
    df_ctkm_only: pd.DataFrame
    df_pog_only:  pd.DataFrame

def join_ctkm_pog(df_ctkm, df_pog) -> JoinResult:
    if "item_id" not in df_ctkm.columns:
        raise ValueError("df_ctkm thieu cot 'item_id'.")
    if "item_id" not in df_pog.columns:
        raise ValueError("df_pog thieu cot 'item_id'.")
    overlap = (set(df_ctkm.columns) & set(df_pog.columns)) - {"item_id"}
    df_c = df_ctkm.rename(columns={c: f"{c}__ctkm" for c in overlap})
    df_p = df_pog.rename(columns={c:  f"{c}__pog"  for c in overlap})
    merged = pd.merge(df_c, df_p, on="item_id", how="outer", indicator=True)
    matched   = merged[merged["_merge"]=="both"].drop(columns=["_merge"]).reset_index(drop=True)
    ctkm_only = merged[merged["_merge"]=="left_only"].drop(columns=["_merge"]).reset_index(drop=True)
    pog_only  = merged[merged["_merge"]=="right_only"].drop(columns=["_merge"]).reset_index(drop=True)
    return JoinResult(matched, ctkm_only, pog_only)

def apply_dimension_conditions(join_result: JoinResult, dimension_frames: dict) -> JoinResult:
    """
    Hien chi gan co 'dimension_check_flag' cho item KHONG xuat hien trong bat ky
    dimension sheet nao (neu co). KHONG tu dong loc bo - tranh mat du lieu do ap
    sai dieu kien (chua co co che biet dimension nao rang buoc cho campaign nao).
    """
    if not dimension_frames: return join_result
    df = join_result.df_matched.copy()
    if df.empty: return join_result
    item_dims = {n: d for n, d in dimension_frames.items()
                 if "item_id" in d.columns and d["item_id"].notna().any()}
    if not item_dims: return join_result
    all_dim_items = set()
    for d in item_dims.values():
        all_dim_items |= set(d["item_id"].dropna().astype(str).str.strip())
    df["dimension_check_flag"] = df["item_id"].astype(str).str.strip().apply(
        lambda x: "" if x in all_dim_items else "khong_xuat_hien_trong_dimension_sheet"
    )
    join_result.df_matched = df.reset_index(drop=True)
    return join_result
