# -*- coding: utf-8 -*-
"""Module 8: Reconciler — dem so lieu, phat hien campaign trung thoi gian cung item."""
from __future__ import annotations
import calendar
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo
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
    source_row_id_a: str = ""
    source_row_id_b: str = ""

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

_BUSINESS_COLUMNS = [
    "item_id", "item_name", "promo_uom", "campaign_name", "campaign_detail",
    "promo_from", "promo_to", "normal_price", "promo_price", "channel",
    "product_type", "program_source", "source_sheet",
]


def _ensure_source_lineage(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach stable, human-readable row references without removing source rows."""
    df = frame.copy()
    if "source_row_id" not in df.columns:
        ids = []
        for position, (_, row) in enumerate(df.iterrows(), start=2):
            raw_source, raw_sheet = row.get("program_source"), row.get("source_sheet")
            source = "CTKM" if pd.isna(raw_source) or not str(raw_source).strip() else str(raw_source).strip()
            sheet = "Sheet1" if pd.isna(raw_sheet) or not str(raw_sheet).strip() else str(raw_sheet).strip()
            ids.append(f"{source}:{sheet}:{position}")
        df["source_row_id"] = ids
    else:
        values = []
        for position, (_, row) in enumerate(df.iterrows(), start=2):
            value = row.get("source_row_id")
            if pd.isna(value) or not str(value).strip():
                raw_source, raw_sheet = row.get("program_source"), row.get("source_sheet")
                source = "CTKM" if pd.isna(raw_source) or not str(raw_source).strip() else str(raw_source).strip()
                sheet = "Sheet1" if pd.isna(raw_sheet) or not str(raw_sheet).strip() else str(raw_sheet).strip()
                value = f"{source}:{sheet}:{position}"
            values.append(str(value))
        df["source_row_id"] = values
    if "source_row_ids" not in df.columns:
        df["source_row_ids"] = df["source_row_id"]
    if "source_row_count" not in df.columns:
        df["source_row_count"] = 1
    if "duplicate_status" not in df.columns:
        df["duplicate_status"] = "Dòng duy nhất"
    return df


def _fingerprint_value(value):
    if pd.isna(value):
        return ("missing", "")
    if isinstance(value, (pd.Timestamp, datetime)):
        return ("datetime", pd.Timestamp(value).isoformat())
    return (type(value).__name__, str(value))


def _display_value(value, fallback="(không rõ)") -> str:
    return fallback if pd.isna(value) or not str(value).strip() else str(value)


def _collapse_exact_duplicates(frame: pd.DataFrame) -> pd.DataFrame:
    """Consolidate only byte-for-byte business duplicates and retain full lineage."""
    df = _ensure_source_lineage(frame)
    lineage = {"source_row_id", "source_row_ids", "source_row_count", "duplicate_status"}
    identity_columns = [column for column in df.columns if column not in lineage]
    groups: dict[tuple, list[int]] = {}
    for idx, row in df.iterrows():
        key = tuple((column, _fingerprint_value(row[column])) for column in identity_columns)
        groups.setdefault(key, []).append(idx)

    rows = []
    for indices in groups.values():
        first = df.loc[indices[0]].copy()
        row_ids: list[str] = []
        source_count = 0
        for idx in indices:
            row_ids.extend(
                part.strip() for part in str(df.at[idx, "source_row_ids"]).split("|") if part.strip()
            )
            count = df.at[idx, "source_row_count"]
            source_count += 1 if pd.isna(count) else int(count)
        row_ids = list(dict.fromkeys(row_ids))
        first["source_row_id"] = row_ids[0]
        first["source_row_ids"] = " | ".join(row_ids)
        first["source_row_count"] = source_count
        first["duplicate_status"] = (
            "Đã gom dòng trùng hoàn toàn" if source_count > 1 else "Dòng duy nhất"
        )
        rows.append(first.to_dict())
    return pd.DataFrame(rows, columns=df.columns).reset_index(drop=True)


def _same_campaign_row(a: dict, b: dict) -> bool:
    columns = [column for column in _BUSINESS_COLUMNS if column in a or column in b]
    return all(_fingerprint_value(a.get(column)) == _fingerprint_value(b.get(column)) for column in columns)


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
    df = df_ctkm.copy()
    df["_overlap_from"] = df["promo_from"].apply(_parse_date)
    df["_overlap_to"] = df["promo_to"].apply(_parse_date)
    df = df[df["_overlap_from"].notna() & df["_overlap_to"].notna()].copy()
    if df.empty:
        return warnings
    df = df[df["item_id"].apply(is_sku)]
    df = _ensure_source_lineage(df)

    for item_id, grp in df.groupby("item_id"):
        if len(grp) < 2: continue
        rows = grp.to_dict("records")
        for a, b in combinations(rows, 2):
            af, at = a["_overlap_from"], a["_overlap_to"]
            bf, bt = b["_overlap_from"], b["_overlap_to"]
            if af <= bt and bf <= at:
                ca = _display_value(a.get("campaign_name"), "(không rõ)")
                cb = _display_value(b.get("campaign_name"), "(không rõ)")
                # Dòng giống hệt nhau là duplicate có lineage, không phải hai campaign xung đột.
                if _same_campaign_row(a, b):
                    continue
                warnings.append(OverlapWarning(
                    str(item_id), ca, cb,
                    f"{af.date()} -> {at.date()}",
                    f"{bf.date()} -> {bt.date()}",
                    _display_value(a.get("channel")),
                    _display_value(b.get("channel")),
                    _display_value(a.get("source_row_id"), ""),
                    _display_value(b.get("source_row_id"), ""),
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


def build_fefo_action_frame(
    df_ctkm,
    target_month,
    df_pog=None,
    *,
    business_date=None,
    overlap_warnings=None,
) -> pd.DataFrame:
    """
    Phân loại hành động theo lịch rồi mới bổ sung vị trí POG. POG không bao giờ
    được dùng để suy luận trạng thái tem hoặc thay đổi ``scheduled_action``.
    """
    if df_ctkm is None or df_ctkm.empty:
        return pd.DataFrame(columns=[*_BUSINESS_COLUMNS, "scheduled_action", "action", "reason",
                                     "target_month", "business_date", "store_id", "pog_code",
                                     "location_id", "facing", "pog_snapshot_month", "location_status"])

    df = _collapse_exact_duplicates(df_ctkm)
    base_cols = _BUSINESS_COLUMNS.copy()
    for col in base_cols:
        if col not in df.columns:
            df[col] = pd.NA

    if "promo_from" not in df.columns or "promo_to" not in df.columns:
        return pd.DataFrame(columns=[*base_cols, "action", "reason", "target_month"])

    # Ngày nghiệp vụ có thể inject để test và chạy lại báo cáo ổn định.
    if business_date is None:
        business_date = pd.Timestamp(datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date())
    else:
        business_date = _parse_date(business_date)
        if pd.isna(business_date):
            raise ValueError("business_date không hợp lệ")
        business_date = business_date.normalize()
    month_start, month_end = _get_month_bounds(target_month)

    def _classify(row):
        promo_from = _parse_date(row.get("promo_from"))
        promo_to = _parse_date(row.get("promo_to"))
        if pd.isna(promo_from) or pd.isna(promo_to):
            return "review", "thieu_thong_tin_ngay"
        promo_from = promo_from.normalize()
        promo_to = promo_to.normalize()
        if promo_from > promo_to:
            return "review", "ngay_bat_dau_sau_ngay_ket_thuc"
        attach_date = promo_from
        remove_date = promo_to + pd.Timedelta(days=1)
        if business_date < attach_date:
            return "chờ gắn tem", "chua_den_ngay_gan"
        if attach_date <= business_date <= promo_to:
            return "gắn tem", "trong_thoi_gian_ap_dung"
        if business_date >= remove_date:
            return "tháo tem", "den_ngay_thao"
        return "review", "khong_xac_dinh_duoc"

    df["scheduled_action"], df["reason"] = zip(*df.apply(_classify, axis=1))
    df["action"] = df["scheduled_action"]  # Backward-compatible export/API field.
    df["target_month"] = target_month
    df["business_date"] = business_date
    df["ngay_gan_tem"] = df["promo_from"].apply(_parse_date).dt.normalize()
    # CTKM con hieu luc het ngay promo_to; thao tem tu dau ngay ke tiep.
    df["ngay_thao_tem"] = df["promo_to"].apply(_parse_date).dt.normalize() + pd.Timedelta(days=1)

    def _scope(row):
        promo_from = _parse_date(row.get("promo_from"))
        promo_to = _parse_date(row.get("promo_to"))
        if pd.isna(promo_from) or pd.isna(promo_to):
            return True, "thieu_ngay_giu_de_review"
        promo_from, promo_to = promo_from.normalize(), promo_to.normalize()
        if promo_from > promo_to:
            return True, "ngay_khong_hop_le_giu_de_review"
        remove_date = promo_to + pd.Timedelta(days=1)
        if promo_from <= month_end and promo_to >= month_start:
            return True, "ctkm_ap_dung_trong_thang"
        if month_start <= remove_date <= month_end:
            return True, "ngay_thao_trong_thang"
        return False, "ngoai_pham_vi_thang_bao_cao"

    scope = df.apply(_scope, axis=1)
    df["in_report_scope"] = [value[0] for value in scope]
    df["report_scope_reason"] = [value[1] for value in scope]

    if overlap_warnings is None:
        overlap_warnings = detect_campaign_time_overlaps(df)
    conflicts: dict[str, list[str]] = {}
    for warning in overlap_warnings or []:
        detail = (
            f"{warning.campaign_a} [{warning.channel_a}] ↔ "
            f"{warning.campaign_b} [{warning.channel_b}]"
        )
        for row_id in (warning.source_row_id_a, warning.source_row_id_b):
            if row_id:
                conflicts.setdefault(row_id, []).append(detail)
    for idx, row in df.iterrows():
        lineage_ids = {
            value.strip() for value in str(row["source_row_ids"]).split("|") if value.strip()
        }
        details = list(dict.fromkeys(
            detail for row_id in lineage_ids for detail in conflicts.get(row_id, [])
        ))
        if details:
            df.at[idx, "scheduled_action"] = "review"
            df.at[idx, "action"] = "review"
            df.at[idx, "reason"] = "xung_dot_thoi_gian: " + " | ".join(details)

    out_cols = [c for c in base_cols if c in df.columns] + [
        "source_row_id", "source_row_ids", "source_row_count", "duplicate_status",
        "ngay_gan_tem", "ngay_thao_tem", "scheduled_action", "action", "reason",
        "target_month", "business_date", "in_report_scope", "report_scope_reason",
    ]
    actions = df.loc[:, out_cols].reset_index(drop=True)

    location_cols = ["store_id", "pog_code", "location_id", "facing", "pog_snapshot_month"]
    if df_pog is None or df_pog.empty or "item_id" not in df_pog.columns:
        for col in location_cols:
            actions[col] = pd.NA
        actions["pog_source_row_id"] = pd.NA
        actions["pog_position_count"] = 0
        actions["pog_month_status"] = "Không có snapshot POG"
        actions["location_status"] = "Không tìm thấy SKU trong POG"
        actions["task_id"] = [f"TASK-{idx:06d}" for idx in range(1, len(actions) + 1)]
        return actions

    available = [col for col in location_cols if col in df_pog.columns]
    locations = df_pog.loc[:, ["item_id", *available]].copy().reset_index(drop=True)
    if "source_row_id" in df_pog.columns:
        locations["pog_source_row_id"] = df_pog["source_row_id"].reset_index(drop=True).map(
            lambda value: str(value) if str(value).startswith("POG:") else f"POG:{value}"
        )
    else:
        locations["pog_source_row_id"] = [f"POG:Sheet1:{idx}" for idx in range(2, len(locations) + 2)]
    locations["pog_position_count"] = locations.groupby("item_id", dropna=False)["item_id"].transform("size")
    actions = actions.merge(locations, on="item_id", how="left", indicator="_pog_match")
    for col in location_cols:
        if col not in actions.columns:
            actions[col] = pd.NA

    required_location = ["store_id", "pog_code", "location_id"]
    for column in required_location:
        if column not in actions.columns:
            actions[column] = pd.NA

    def _location_state(row):
        if row["_pog_match"] != "both":
            return "Không tìm thấy SKU trong POG", "Không có snapshot POG"
        snapshot = row.get("pog_snapshot_month")
        month_status = (
            "POG lệch tháng"
            if pd.notna(snapshot) and str(snapshot).strip() and str(snapshot).strip() != target_month
            else "POG đúng tháng" if pd.notna(snapshot) and str(snapshot).strip()
            else "Không rõ tháng POG"
        )
        complete = all(pd.notna(row[col]) and str(row[col]).strip() for col in required_location)
        if not complete:
            return "Thiếu một phần thông tin vị trí", month_status
        if month_status == "POG lệch tháng":
            return "POG lệch tháng", month_status
        if int(row.get("pog_position_count") or 0) > 1:
            return "Nhiều vị trí POG", month_status
        return "Đủ vị trí", month_status

    states = actions.apply(_location_state, axis=1)
    actions["location_status"] = [state[0] for state in states]
    actions["pog_month_status"] = [state[1] for state in states]
    actions["pog_position_count"] = actions["pog_position_count"].fillna(0).astype(int)
    actions["task_id"] = [f"TASK-{idx:06d}" for idx in range(1, len(actions) + 1)]
    actions = actions.drop(columns=["_pog_match"])
    return actions.loc[:, [
        *out_cols, *location_cols, "pog_source_row_id", "pog_position_count",
        "pog_month_status", "location_status", "task_id",
    ]].reset_index(drop=True)


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
