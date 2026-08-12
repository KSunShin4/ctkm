# -*- coding: utf-8 -*-
"""Module 5: Normalizer — apply mapping, parse kieu du lieu, unpivot multi-promo."""
from __future__ import annotations
import re
from typing import Optional
import pandas as pd

DATE_FIELDS   = {"promo_from","promo_to","row_update_date"}
NUMBER_FIELDS = {"normal_price","promo_price","facing"}
STRING_FIELDS = {"item_id","item_name","promo_uom","campaign_name","campaign_detail","channel",
                 "product_type","store_id","pog_code","location_id","condition_note"}

# WHITELIST: chi cac field nay moi duoc phep co nhieu slot -> nhan dong khi unpivot.
# Field nao khac bi trung slot (do mapping sai) se KHONG nhan dong — chi rename sang
# extra__ va ghi canh bao, tranh loi nhan dong am tham lam sai so lieu.
UNPIVOTABLE_FIELDS = {"campaign_detail", "promo_price"}

def apply_mapping(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """
    Doi ten cot theo mapping. Neu nhieu cot goc cung map ve 1 canonical field,
    tu dong danh so suffix __1, __2,... (day la tin hieu cho unpivot_multi_promo).
    """
    canonical_count: dict = {}
    final_names: dict = {}
    for col in df.columns:
        target = mapping.get(col, f"extra__{col}")
        cnt = canonical_count.get(target, 0)
        canonical_count[target] = cnt + 1
        if cnt == 0:
            final_names[col] = target
        else:
            final_names[col] = f"{target}__{cnt+1}"
            if cnt == 1:
                for pc, pt in list(final_names.items()):
                    if pt == target and pc != col:
                        final_names[pc] = f"{target}__1"
                        break
    return df.rename(columns=final_names)

def _parse_date(v):
    if pd.isna(v) or v is None or str(v).strip()=="": return None
    if isinstance(v, pd.Timestamp): return v
    try: return pd.to_datetime(v, dayfirst=False, errors="raise")
    except:
        try: return pd.to_datetime(v, dayfirst=True, errors="raise")
        except: return None

def _parse_number(v):
    if pd.isna(v) or v is None or str(v).strip()=="": return None
    if isinstance(v, (int,float)): return float(v)
    cleaned = re.sub(r"[^\d.\-]","",str(v))
    try: return float(cleaned) if cleaned not in ("","-",".") else None
    except: return None

def clean_values(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        if col in DATE_FIELDS:
            df[col] = df[col].apply(_parse_date)
        elif col in NUMBER_FIELDS:
            df[col] = df[col].apply(_parse_number)
        elif col in STRING_FIELDS:
            df[col] = df[col].apply(lambda v: str(v).strip() if pd.notna(v) and str(v).strip() else None)
    if "item_id" in df.columns:
        df = df[df["item_id"].notna()].reset_index(drop=True)
    return df

def attach_source_sheet(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    df = df.copy(); df["source_sheet"] = sheet_name; return df

def attach_pog_snapshot_month(df: pd.DataFrame, month) -> pd.DataFrame:
    df = df.copy(); df["pog_snapshot_month"] = month; return df

def unpivot_multi_promo(df: pd.DataFrame, max_slots: int = 5):
    """
    Phat hien cot co suffix __N (do apply_mapping tao ra khi nhieu cot map ve 1 field),
    tach thanh nhieu dong NEU field nam trong UNPIVOTABLE_FIELDS.
    Field khac bi trung slot -> giu slot dau, day sang extra__, ghi canh bao.
    Tra ve (df_result, list_warnings).
    """
    suffix_pat = re.compile(r"^(.+)__(\d+)$")
    slot_groups: dict = {}
    for col in df.columns:
        m = suffix_pat.match(str(col))
        if m:
            fn, idx = m.group(1), int(m.group(2))
            slot_groups.setdefault(fn, {})[idx] = col

    if not slot_groups:
        return df, []

    multi = {f: s for f, s in slot_groups.items() if len(s) > 1}
    if not multi:
        return df, []

    allowed   = {f: s for f, s in multi.items() if f in UNPIVOTABLE_FIELDS}
    forbidden = {f: s for f, s in multi.items() if f not in UNPIVOTABLE_FIELDS}
    warnings = []

    df = df.copy()
    for fn, slots in forbidden.items():
        sorted_slots = sorted(slots.items())
        first_col = sorted_slots[0][1]
        df = df.rename(columns={first_col: fn})
        for idx, col in sorted_slots[1:]:
            df = df.rename(columns={col: f"extra__{fn}__{idx}"})
        warnings.append(
            f"{len(slots)} cot bi map nham vao field '{fn}' (khong nam trong UNPIVOTABLE_FIELDS). "
            f"Giu slot dau, cac slot con lai chuyen sang extra__. Kiem tra Mapping log."
        )

    if not allowed:
        return df, warnings

    used = {col for s in allowed.values() for col in s.values()}
    shared = [c for c in df.columns if c not in used]
    n = min(max(len(s) for s in allowed.values()), max_slots)

    rows_out = []
    for _, row in df.iterrows():
        added = False
        for slot_idx in range(1, n+1):
            slot, has_val = {}, False
            for fn, slots in allowed.items():
                col = slots.get(slot_idx)
                if col:
                    v = row[col]
                    slot[fn] = v
                    if pd.notna(v) and str(v).strip(): has_val = True
            if has_val:
                rows_out.append({**{c: row[c] for c in shared}, **slot})
                added = True
        if not added:
            rows_out.append({**{c: row[c] for c in shared}, **{fn: None for fn in allowed}})

    return pd.DataFrame(rows_out).reset_index(drop=True), warnings
