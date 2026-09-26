# -*- coding: utf-8 -*-
"""Module 8: Reconciler — dem so lieu, phat hien campaign trung thoi gian cung item."""
from __future__ import annotations
import calendar
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field as dc_field
from itertools import combinations
import pandas as pd

_SKU_PAT = re.compile(r"^[Pp]\d+$")

def is_sku(item_id) -> bool:
    """Return whether a scalar item code follows the current P-number convention."""
    if item_id is None:
        return False
    try:
        if bool(pd.isna(item_id)):
            return False
    except (TypeError, ValueError):
        return False
    text = str(item_id).strip()
    return bool(text and _SKU_PAT.fullmatch(text))


def is_bill_program(item_id) -> bool:
    """Recognize only the explicit invoice-level convention; do not infer it."""
    return _item_key(item_id) == "BILL"

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
    conflict_type: str = "blocking_conflict"
    is_blocking: bool = True

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
    missing_item_ctkm_count: int = 0
    invalid_item_ctkm_count: int = 0

_BUSINESS_COLUMNS = [
    "item_id", "item_key", "item_name", "promo_uom", "campaign_name", "campaign_detail",
    "promo_from", "promo_to", "normal_price", "promo_price", "channel",
    "product_type", "program_source", "source_sheet",
]

_PROMOTION_ID_COLUMNS = [
    "program_source", "item_key", "campaign_name", "campaign_detail",
    "promo_from", "promo_to", "normal_price", "promo_price", "promo_uom",
    "key_channel", "channel",
]

_POG_POSITION_ID_COLUMNS = [
    "item_key", "store_id", "pog_code", "location_id", "facing", "pog_snapshot_month",
]


def _item_key(value):
    if value is None or pd.isna(value):
        return None
    key = str(value).strip().upper()
    return key or None


def _ensure_item_key(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    if "item_key" in df.columns:
        df["item_key"] = df["item_key"].apply(_item_key)
    else:
        df["item_key"] = df.get("item_id", pd.Series(index=df.index, dtype=object)).apply(_item_key)
    return df


def _canonical_value(value):
    """Serialize business values consistently for deterministic identifiers."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(value, ".15g")
    return str(value)


def _stable_id(prefix: str, values: list) -> str:
    payload = json.dumps(
        [_canonical_value(value) for value in values],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"{prefix}-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24].upper()}"


def _attach_task_ids(actions: pd.DataFrame) -> pd.DataFrame:
    result = actions.copy()
    result["pog_position_id"] = result.apply(
        lambda row: _stable_id(
            "POGPOS", [row.get(column) for column in _POG_POSITION_ID_COLUMNS],
        ),
        axis=1,
    )
    result["task_id"] = result.apply(
        lambda row: _stable_id("TASK", [
            row.get("promotion_id"), row.get("scheduled_action"), row.get("pog_position_id"),
        ]),
        axis=1,
    )
    return result


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
    lineage = {
        "source_row_id", "source_row_ids", "source_row_count", "duplicate_status",
        "source_excel_row", "logical_row_id", "promo_slot_id",
    }
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
    df = _ensure_item_key(df_ctkm)
    df["_overlap_from"] = df["promo_from"].apply(_parse_date)
    df["_overlap_to"] = df["promo_to"].apply(_parse_date)
    df = df[df["_overlap_from"].notna() & df["_overlap_to"].notna()].copy()
    if df.empty:
        return warnings
    df = df[df["item_key"].apply(is_sku)]
    df = _ensure_source_lineage(df)

    for item_key, grp in df.groupby("item_key"):
        if len(grp) < 2: continue
        rows = grp.to_dict("records")
        for a, b in combinations(rows, 2):
            af, at = a["_overlap_from"], a["_overlap_to"]
            bf, bt = b["_overlap_from"], b["_overlap_to"]
            if af <= bt and bf <= at:
                ca = _display_value(a.get("campaign_name"), "(không rõ)")
                cb = _display_value(b.get("campaign_name"), "(không rõ)")
                if _same_campaign_row(a, b):
                    continue
                channel_a = a.get("channel")
                channel_b = b.get("channel")
                raw_channels_differ = _fingerprint_value(channel_a) != _fingerprint_value(channel_b)
                source_a = _normalize_text(a.get("program_source"))
                source_b = _normalize_text(b.get("program_source"))
                cross_source_clearance = (
                    source_a != source_b and {source_a, source_b} == {"ctkm", "clearance"}
                )
                is_blocking = cross_source_clearance or not raw_channels_differ
                conflict_type = (
                    "blocking_conflict" if is_blocking
                    else "potential_cross_channel_overlap" if raw_channels_differ
                    else "potential_overlap"
                )
                warnings.append(OverlapWarning(
                    str(item_key), ca, cb,
                    f"{af.date()} -> {at.date()}",
                    f"{bf.date()} -> {bt.date()}",
                    _display_value(a.get("channel")),
                    _display_value(b.get("channel")),
                    _display_value(a.get("source_row_id"), ""),
                    _display_value(b.get("source_row_id"), ""),
                    conflict_type,
                    is_blocking,
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
    Phân loại hành động theo lịch rồi mới bổ sung vị trí POG. POG và cảnh báo
    overlap không bao giờ được dùng để thay đổi ``scheduled_action``.
    """
    if df_ctkm is None or df_ctkm.empty:
        return pd.DataFrame(columns=[*_BUSINESS_COLUMNS, "scheduled_action", "action", "reason",
                                     "target_month", "business_date", "store_id", "pog_code",
                                     "location_id", "facing", "pog_snapshot_month", "location_status"])

    df = _collapse_exact_duplicates(_ensure_item_key(df_ctkm))
    base_cols = _BUSINESS_COLUMNS.copy()
    for col in base_cols:
        if col not in df.columns:
            df[col] = pd.NA

    if "promo_from" not in df.columns or "promo_to" not in df.columns:
        return pd.DataFrame(columns=[*base_cols, "action", "reason", "target_month"])

    if business_date is None:
        business_date = pd.Timestamp(datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date())
    else:
        business_date = _parse_date(business_date)
        if pd.isna(business_date):
            raise ValueError("business_date không hợp lệ")
        business_date = business_date.normalize()
    month_start, month_end = _get_month_bounds(target_month)

    def _classify(row):
        if _item_key(row.get("item_key")) is None:
            return "review", "thieu_ma_san_pham"
        if not is_sku(row.get("item_key")) and not is_bill_program(row.get("item_key")):
            return "review", "ma_san_pham_khong_hop_le"
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
    df["action"] = df["scheduled_action"]
    df["target_month"] = target_month
    df["business_date"] = business_date
    df["ngay_gan_tem"] = df["promo_from"].apply(_parse_date).dt.normalize()
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

    # ``overlap_warnings`` is intentionally not allowed to alter action. The
    # public reconciler facade attaches review metadata independently.
    _ = overlap_warnings

    out_cols = [c for c in base_cols if c in df.columns] + [
        "source_row_id", "source_row_ids", "source_row_count", "duplicate_status",
        "ngay_gan_tem", "ngay_thao_tem", "scheduled_action", "action", "reason",
        "target_month", "business_date", "in_report_scope", "report_scope_reason",
    ]
    for technical_column in ("source_excel_row", "logical_row_id", "promo_slot_id"):
        if technical_column in df.columns:
            out_cols.append(technical_column)
    actions = df.loc[:, out_cols].reset_index(drop=True)
    actions["promotion_id"] = actions.apply(
        lambda row: _stable_id("PROMO", [row.get(column) for column in _PROMOTION_ID_COLUMNS]),
        axis=1,
    )

    location_cols = ["store_id", "pog_code", "location_id", "facing", "pog_snapshot_month"]
    if df_pog is None or df_pog.empty or "item_id" not in df_pog.columns:
        for col in location_cols:
            actions[col] = pd.NA
        actions["pog_source_row_id"] = pd.NA
        actions["pog_source_row_ids"] = pd.NA
        actions["pog_source_row_count"] = 0
        actions["pog_duplicate_status"] = "Không có dòng POG"
        actions["pog_position_count"] = 0
        actions["pog_month_status"] = "Không có snapshot POG"
        actions["location_completeness"] = "Không tìm thấy SKU trong POG"
        actions["has_multiple_pog_positions"] = False
        actions["location_needs_review"] = True
        actions["location_status"] = actions["location_completeness"]
        return _attach_task_ids(actions)

    pog = _ensure_item_key(df_pog)
    pog = pog[pog["item_key"].notna()].copy().reset_index(drop=True)
    for col in location_cols:
        if col not in pog.columns:
            pog[col] = pd.NA
    if "source_row_id" in pog.columns:
        pog["pog_source_row_id"] = pog["source_row_id"].map(
            lambda value: str(value) if str(value).startswith("POG:") else f"POG:{value}"
        )
    else:
        pog["pog_source_row_id"] = [f"POG:Sheet1:{idx}" for idx in range(2, len(pog) + 2)]

    position_key = ["item_key", *location_cols]
    location_rows = []
    for _, group in pog.groupby(position_key, dropna=False, sort=False):
        first = group.iloc[0].copy()
        row_ids = list(dict.fromkeys(group["pog_source_row_id"].astype(str).tolist()))
        first["pog_source_row_id"] = row_ids[0]
        first["pog_source_row_ids"] = " | ".join(row_ids)
        first["pog_source_row_count"] = len(group)
        first["pog_duplicate_status"] = (
            "Đã gom dòng POG trùng hoàn toàn" if len(group) > 1 else "Dòng POG duy nhất"
        )
        location_rows.append(first)
    locations = pd.DataFrame(location_rows)
    if locations.empty:
        return build_fefo_action_frame(
            df_ctkm, target_month, None, business_date=business_date,
            overlap_warnings=overlap_warnings,
        )
    locations["pog_position_count"] = locations.groupby("item_key")["item_key"].transform("size")
    keep_location_cols = [
        "item_key", *location_cols, "pog_source_row_id", "pog_source_row_ids",
        "pog_source_row_count", "pog_duplicate_status", "pog_position_count",
    ]
    actions = actions.merge(locations.loc[:, keep_location_cols], on="item_key", how="left", indicator="_pog_match")
    for col in location_cols:
        if col not in actions.columns:
            actions[col] = pd.NA

    required_location = ["store_id", "pog_code", "location_id"]
    for column in required_location:
        if column not in actions.columns:
            actions[column] = pd.NA

    def _location_state(row):
        if row["_pog_match"] != "both":
            return "Không tìm thấy SKU trong POG", "Không có snapshot POG", False, True
        snapshot = row.get("pog_snapshot_month")
        month_status = (
            "POG lệch tháng"
            if pd.notna(snapshot) and str(snapshot).strip() and str(snapshot).strip() != target_month
            else "POG đúng tháng" if pd.notna(snapshot) and str(snapshot).strip()
            else "Không rõ tháng POG"
        )
        complete = all(pd.notna(row[col]) and str(row[col]).strip() for col in required_location)
        if not complete:
            completeness = "Thiếu một phần thông tin vị trí"
        else:
            completeness = "Đủ vị trí"
        multiple = int(row.get("pog_position_count") or 0) > 1
        needs_review = completeness != "Đủ vị trí" or month_status in {"POG lệch tháng", "Không rõ tháng POG"}
        return completeness, month_status, multiple, needs_review

    states = actions.apply(_location_state, axis=1)
    actions["location_completeness"] = [state[0] for state in states]
    actions["pog_month_status"] = [state[1] for state in states]
    actions["has_multiple_pog_positions"] = [state[2] for state in states]
    actions["location_needs_review"] = [state[3] for state in states]
    actions["location_status"] = actions.apply(
        lambda row: (
            "POG lệch tháng" if row["pog_month_status"] == "POG lệch tháng"
            else "Nhiều vị trí POG" if row["has_multiple_pog_positions"] and row["location_completeness"] == "Đủ vị trí"
            else row["location_completeness"]
        ), axis=1,
    )
    actions["pog_position_count"] = actions["pog_position_count"].fillna(0).astype(int)
    actions["pog_source_row_count"] = actions["pog_source_row_count"].fillna(0).astype(int)
    actions = _attach_task_ids(actions)
    actions = actions.drop(columns=["_pog_match"])
    return actions.loc[:, [
        *out_cols, "promotion_id", *location_cols, "pog_source_row_id", "pog_source_row_ids",
        "pog_source_row_count", "pog_duplicate_status", "pog_position_count",
        "location_completeness", "has_multiple_pog_positions", "pog_month_status",
        "location_needs_review", "location_status", "pog_position_id", "task_id",
    ]].reset_index(drop=True)


def build_reconciliation_report(df_matched, df_ctkm_only, df_pog_only, overlap_warnings) -> ReconciliationReport:
    def _uniq(df):
        key = "item_key" if "item_key" in df.columns else "item_id"
        return df[key].nunique() if not df.empty and key in df.columns else 0
    bill_count = 0
    missing_count = 0
    invalid_count = 0
    if not df_ctkm_only.empty:
        raw_keys = (
            df_ctkm_only["item_key"]
            if "item_key" in df_ctkm_only.columns
            else df_ctkm_only.get("item_id", pd.Series(index=df_ctkm_only.index, dtype=object))
        )
        item_keys = raw_keys.apply(_item_key)
        missing_mask = item_keys.isna()
        bill_mask = item_keys.apply(is_bill_program)
        sku_mask = item_keys.apply(is_sku)
        bill_count = int(bill_mask.sum())
        missing_count = int(missing_mask.sum())
        invalid_count = int((~missing_mask & ~bill_mask & ~sku_mask).sum())
    return ReconciliationReport(
        matched_count=len(df_matched),
        ctkm_only_count=len(df_ctkm_only),
        pog_only_count=len(df_pog_only),
        matched_unique_items=_uniq(df_matched),
        ctkm_only_unique_items=_uniq(df_ctkm_only),
        pog_only_unique_items=_uniq(df_pog_only),
        non_sku_ctkm_count=bill_count,
        overlap_warnings=overlap_warnings,
        missing_item_ctkm_count=missing_count,
        invalid_item_ctkm_count=invalid_count,
    )
