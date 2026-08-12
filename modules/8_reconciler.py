# -*- coding: utf-8 -*-
"""Module 8: Reconciler — dem so lieu, phat hien campaign trung thoi gian cung item."""
from __future__ import annotations
import calendar
import re
import unicodedata
from dataclasses import dataclass, field as dc_field
from itertools import combinations
import pandas as pd

_SKU_PAT = re.compile(r"^[Pp]\d+$")

def is_sku(item_id) -> bool:
    return bool(_SKU_PAT.match(str(item_id).strip())) if item_id else False

@dataclass
class OverlapWarning:
    item_id: str
    campaign_a: str
    campaign_b: str
    period_a: str
    period_b: str
    channel_a: str = "(không rõ)"
    channel_b: str = "(không rõ)"

@dataclass
class ReconciliationReport:
    matched_count: int
    ctkm_only_count: int
    pog_only_count: int
    matched_unique_items: int
    ctkm_only_unique_items: int
    pog_only_unique_items: int
    non_sku_ctkm_count: int = 0
    overlap_warnings: list = dc_field(default_factory=list)

def detect_campaign_time_overlaps(df_ctkm) -> list:
    """
    Quet tung item_id co >= 2 dong CTKM, kiem tra cap nao co khoang thoi gian chong nhau.
    CHI xet item_id dung dinh dang SKU (P#####). Cac CTKM theo hoa don (item_id="Bill"...)
    bi bo qua de tranh false positive (nhieu chuong trinh hoa don chay song song la hop le).
    Goi ham nay TRUOC khi join voi POG (de tranh nhieu dong do 1-nhieu lam nhieu ket qua).
    """
    warnings = []
    if not {"item_id","promo_from","promo_to"}.issubset(df_ctkm.columns):
        return warnings
    df = df_ctkm[df_ctkm["promo_from"].notna() & df_ctkm["promo_to"].notna()].copy()
    df = df[df["item_id"].apply(is_sku)]
    # De-duplicate truoc: voi cung item+campaign+from+to, chi giu 1 dong (tranh false positive
    # do unpivot tao nhieu dong co cung thoi gian nhung khac campaign_detail)
    dedup_cols = [
        c for c in ["item_id", "campaign_name", "promo_from", "promo_to", "channel"]
        if c in df.columns
    ]
    df = df.drop_duplicates(subset=dedup_cols)

    def channel_scope(value) -> set[str]:
        text = _normalize_text(value)
        if not text:
            return {"unknown"}
        scopes: set[str] = set()
        if "all channel" in text:
            scopes.update({"offline", "online", "mkp"})
            if "except mkp" in text:
                scopes.discard("mkp")
        if "offline" in text or "store" in text:
            scopes.add("offline")
        if any(token in text for token in ("online", "web", "app", "tiktok")):
            scopes.add("online")
        if "mkp" in text or "marketplace" in text:
            scopes.add("mkp")
        return scopes or {"unknown"}

    def channels_can_overlap(a, b) -> bool:
        scope_a, scope_b = channel_scope(a), channel_scope(b)
        return "unknown" in scope_a or "unknown" in scope_b or bool(scope_a & scope_b)

    for item_id, grp in df.groupby("item_id"):
        if len(grp) < 2: continue
        rows = grp.to_dict("records")
        for a, b in combinations(rows, 2):
            af, at = a["promo_from"], a["promo_to"]
            bf, bt = b["promo_from"], b["promo_to"]
            if af <= bt and bf <= at and channels_can_overlap(a.get("channel"), b.get("channel")):
                ca = str(a.get("campaign_name") or "(khong ro)")
                cb = str(b.get("campaign_name") or "(khong ro)")
                # Bo qua neu cung ten campaign & cung thoi gian (chinh la cung 1 chuong trinh)
                if ca == cb and af == bf and at == bt:
                    continue
                warnings.append(OverlapWarning(
                    str(item_id), ca, cb,
                    f"{af.date()} -> {at.date()}",
                    f"{bf.date()} -> {bt.date()}",
                    str(a.get("channel") or "(không rõ)"),
                    str(b.get("channel") or "(không rõ)"),
                ))
    return warnings

def _get_month_bounds(target_month):
    try:
        y, m = map(int, target_month.split("-"))
    except Exception as exc:
        raise ValueError(f"target_month phai dang 'YYYY-MM', nhan duoc: {target_month!r}") from exc
    start = pd.Timestamp(year=y, month=m, day=1)
    end = pd.Timestamp(year=y, month=m, day=calendar.monthrange(y, m)[1], hour=23, minute=59, second=59)
    return start, end


def _normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _parse_date(value):
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, pd.Timestamp):
        return value
    try:
        return pd.to_datetime(value, errors="coerce")
    except Exception:
        return pd.NaT


def build_fefo_action_frame(df_ctkm, target_month, df_pog=None) -> pd.DataFrame:
    """
    Phan loai moi dong CTKM thanh hanh dong gan/thao tem theo thoi han khuyen mai,
    sau do bo sung tat ca vi tri ke POG cua tung san pham (neu co).
    - Neu promo dang ap dung hom nay -> gan tem.
    - Neu promo da het han truoc hom nay -> thao tem.
    - Neu promo chua bat dau -> cho gan tem, khong dua vao sheet thao tem.
    - Neu thieu ngay -> can review.
    """
    if df_ctkm is None or df_ctkm.empty:
        return pd.DataFrame(columns=["item_id", "item_name", "promo_uom", "campaign_name", "campaign_detail",
                                     "promo_from", "promo_to", "channel", "source_sheet",
                                     "action", "reason", "target_month", "store_id", "pog_code",
                                     "location_id", "facing", "pog_snapshot_month", "location_status"])

    df = df_ctkm.copy()
    base_cols = ["item_id", "item_name", "promo_uom", "campaign_name", "campaign_detail", "promo_from", "promo_to", "channel", "source_sheet"]
    for col in base_cols:
        if col not in df.columns:
            df[col] = pd.NA

    if "promo_from" not in df.columns or "promo_to" not in df.columns:
        return pd.DataFrame(columns=[*base_cols, "action", "reason", "target_month"])

    today = pd.Timestamp.today().normalize()

    def _classify(row):
        promo_from = _parse_date(row.get("promo_from"))
        promo_to = _parse_date(row.get("promo_to"))
        if pd.isna(promo_from) or pd.isna(promo_to):
            return "review", "thieu_thong_tin_ngay"
        if promo_to < today:
            return "tháo tem", "promo_het_han_truoc_hom_nay"
        if promo_from > today:
            return "chờ gắn tem", "promo_bat_dau_sau_hom_nay"
        if promo_from <= today and promo_to >= today:
            return "gắn tem", "promo_dang_ap_dung_hom_nay"
        return "review", "khong_xac_dinh_duoc"

    df["action"], df["reason"] = zip(*df.apply(_classify, axis=1))
    df["target_month"] = target_month

    # Cùng mã/chương trình/thời gian nhưng khác kênh hoặc khác chi tiết ưu đãi
    # là các thao tác riêng; không được gộp mất trong danh sách Gắn/Tháo tem.
    dedup_cols = [
        c for c in [
            "item_id", "promo_uom", "campaign_name", "campaign_detail",
            "promo_from", "promo_to", "channel",
        ]
        if c in df.columns
    ]
    if len(dedup_cols) >= 2:
        df = df.drop_duplicates(subset=dedup_cols)

    out_cols = [c for c in base_cols if c in df.columns] + ["action", "reason", "target_month"]
    actions = df.loc[:, out_cols].reset_index(drop=True)

    location_cols = ["store_id", "pog_code", "location_id", "facing", "pog_snapshot_month"]
    if df_pog is None or df_pog.empty or "item_id" not in df_pog.columns:
        for col in location_cols:
            actions[col] = pd.NA
        actions["location_status"] = "thiếu vị trí kệ"
        return actions

    available = [col for col in location_cols if col in df_pog.columns]
    locations = df_pog.loc[:, ["item_id", *available]].copy()
    locations = locations.drop_duplicates()
    actions = actions.merge(locations, on="item_id", how="left")
    for col in location_cols:
        if col not in actions.columns:
            actions[col] = pd.NA

    location_markers = [col for col in ["store_id", "pog_code", "location_id"] if col in actions.columns]
    has_location = pd.Series(False, index=actions.index)
    for col in location_markers:
        has_location |= actions[col].notna() & actions[col].astype(str).str.strip().ne("")
    actions["location_status"] = has_location.map({True: "đã có vị trí kệ", False: "thiếu vị trí kệ"})
    return actions.loc[:, [*out_cols, *location_cols, "location_status"]].reset_index(drop=True)


def build_reconciliation_report(df_matched, df_ctkm_only, df_pog_only, overlap_warnings) -> ReconciliationReport:
    def _uniq(df):
        return df["item_id"].nunique() if not df.empty and "item_id" in df.columns else 0
    non_sku = 0
    if not df_ctkm_only.empty and "item_id" in df_ctkm_only.columns:
        non_sku = int((~df_ctkm_only["item_id"].apply(is_sku)).sum())
    return ReconciliationReport(
        len(df_matched), len(df_ctkm_only), len(df_pog_only),
        _uniq(df_matched), _uniq(df_ctkm_only), _uniq(df_pog_only),
        non_sku, overlap_warnings,
    )
