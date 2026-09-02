# -*- coding: utf-8 -*-
"""Module 6: Time Filter — loc CTKM theo overlap thang, doi chieu pog_snapshot_month."""
from __future__ import annotations
import calendar
from dataclasses import dataclass
from typing import Optional
import pandas as pd

@dataclass
class SnapshotAlignmentCheck:
    target_month: str
    pog_snapshot_month: Optional[str]
    is_aligned: bool
    warning_message: Optional[str] = None

def _parse_ym(ym):
    try:
        y, m = ym.split("-"); return int(y), int(m)
    except Exception as e:
        raise ValueError(f"target_month phai dang 'YYYY-MM', nhan duoc: {ym!r}") from e

def get_month_bounds(target_month):
    y, m = _parse_ym(target_month)
    start = pd.Timestamp(year=y, month=m, day=1)
    end   = pd.Timestamp(year=y, month=m, day=calendar.monthrange(y,m)[1], hour=23, minute=59, second=59)
    return start, end

def check_snapshot_alignment(target_month, pog_snapshot_month) -> SnapshotAlignmentCheck:
    if pog_snapshot_month is None:
        return SnapshotAlignmentCheck(target_month, None, False,
            "Khong trich xuat duoc thang snapshot tu file POG (khong tim thay dong 'Applied filters'). "
            "Khong the xac nhan file POG co dung thang bao cao hay khong.")
    if target_month != pog_snapshot_month:
        return SnapshotAlignmentCheck(target_month, pog_snapshot_month, False,
            f"LECH THANG: bao cao thang {target_month} nhung file POG la snapshot thang "
            f"{pog_snapshot_month}. Vi tri ke co the da thay doi. Hay upload dung file POG "
            f"cua thang {target_month}, hoac xac nhan ban muon dung snapshot {pog_snapshot_month}.")
    return SnapshotAlignmentCheck(target_month, pog_snapshot_month, True)

def filter_ctkm_by_month(df_ctkm, target_month):
    """
    Tra ve (df_all_relevant, df_strict_match).
    df_strict_match: CHI dong overlap thuc su -> dung lam input cho join.
    df_all_relevant: them ca dong thieu thong tin ngay (de khong mat du lieu am tham).
    """
    required = {"promo_from", "promo_to"}
    missing_cols = sorted(required - set(df_ctkm.columns))
    if missing_cols:
        available = ", ".join(map(str, df_ctkm.columns[:20]))
        raise ValueError(
            "File CTKM sau khi map cot khong co du cot ngay can thiet: "
            f"{', '.join(missing_cols)}. "
            "Kiem tra lai file da chon co phai la CTKM tong hop hay khong. "
            f"Cac cot dang co: {available}"
        )
    ms, me = get_month_bounds(target_month)
    df = df_ctkm.copy()
    promo_from = pd.to_datetime(df["promo_from"], errors="coerce")
    promo_to = pd.to_datetime(df["promo_to"], errors="coerce")
    has_dates = promo_from.notna() & promo_to.notna()
    valid_period = has_dates & (promo_from <= promo_to)
    overlap = valid_period & (promo_from <= me) & (promo_to >= ms)
    remove_date = promo_to + pd.Timedelta(days=1)
    removal_in_month = valid_period & remove_date.between(ms, me, inclusive="both")
    missing = ~has_dates
    invalid_period = has_dates & ~valid_period
    operational = overlap | removal_in_month
    relevant = operational | missing | invalid_period

    df_strict = df[operational].copy().reset_index(drop=True)
    relevant_index = df.index[relevant]
    df_all = df.loc[relevant_index].copy().reset_index(drop=True)
    df_all["_missing_date_info"] = missing.loc[relevant_index].to_numpy()
    df_all["_month_scope_reason"] = [
        "thieu_ngay_giu_de_review" if missing.at[idx]
        else "ngay_khong_hop_le_giu_de_review" if invalid_period.at[idx]
        else "ngay_thao_trong_thang" if removal_in_month.at[idx] and not overlap.at[idx]
        else "ctkm_ap_dung_trong_thang"
        for idx in relevant_index
    ]
    return df_all, df_strict
