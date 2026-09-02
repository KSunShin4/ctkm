# -*- coding: utf-8 -*-
"""Module 5: Normalizer — map columns while preserving source values verbatim."""
from __future__ import annotations
import re
from typing import Optional
import pandas as pd

DATE_FIELDS   = {"promo_from","promo_to","row_update_date"}
NUMBER_FIELDS = {"normal_price","promo_price","facing"}
STRING_FIELDS = {"item_id","item_name","promo_uom","campaign_name","campaign_detail","key_channel","channel",
                 "product_type","store_id","pog_code","location_id","condition_note"}

UNPIVOTABLE_FIELDS = {"campaign_detail", "promo_price"}
EXCEL_ERROR_VALUES = {"#N/A", "#VALUE!", "#REF!", "#DIV/0!", "#NAME?", "#NUM!", "#NULL!"}


def _parse_identifier(v):
    """Legacy helper retained for compatibility; do not use to overwrite source values."""
    if pd.isna(v) or v is None:
        return None
    text = str(v).replace("\xa0", " ").strip()
    if not text or text.upper() in EXCEL_ERROR_VALUES:
        return None
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        text = text.split(".", 1)[0]
    return text


def _preserve_item_id(v):
    """Return the source value unchanged.

    Matching/validation must use ``item_key`` instead of rewriting ``item_id``.
    """
    return v


def make_item_key(v):
    """Build a normalized technical SKU key without changing the source cell."""
    if v is None or pd.isna(v):
        return None
    if isinstance(v, str):
        text = v.strip()
        if not text or text.upper() in EXCEL_ERROR_VALUES:
            return None
    else:
        text = str(v).strip()
    # Excel may expose an integral numeric identifier as 12345.0. Normalize only
    # the technical key; the displayed/source item_id remains untouched.
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        text = text.split(".", 1)[0]
    key = text.upper()
    return key or None


def _preserve_channel(v):
    """Return KEY Channel/Channel exactly as loaded from the source workbook."""
    return v


def apply_mapping(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
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
    """Parse a value for calculations only; never write it back to a source field."""
    if pd.isna(v) or v is None or str(v).strip()=="": return None
    if isinstance(v, pd.Timestamp): return v
    try: return pd.to_datetime(v, dayfirst=False, errors="raise")
    except Exception:
        try: return pd.to_datetime(v, dayfirst=True, errors="raise")
        except Exception: return None


def _parse_number(v):
    """Parse a value for calculations only; never write it back to a source field."""
    if pd.isna(v) or v is None or str(v).strip()=="": return None
    if isinstance(v, (int,float)): return float(v)
    cleaned = re.sub(r"[^\d.\-]","",str(v))
    try: return float(cleaned) if cleaned not in ("","-",".") else None
    except Exception: return None


def clean_values(df: pd.DataFrame) -> pd.DataFrame:
    """Preserve all mapped source values and add technical matching keys only.

    Previous versions parsed dates/prices and trimmed/coerced strings in-place.
    That made exported values differ from the uploaded workbook. Business logic
    already parses dates locally where needed, so canonical source fields can and
    should remain exactly as loaded by openpyxl.
    """
    result = df.copy()
    if "item_id" in result.columns:
        result["item_key"] = result["item_id"].apply(make_item_key)
    return result.reset_index(drop=True)


def _attach_default_logical_ids(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    if "source_row_id" in result.columns:
        if "promo_slot_id" not in result.columns:
            result["promo_slot_id"] = 1
        if "logical_row_id" not in result.columns:
            result["logical_row_id"] = result["source_row_id"]
    return result


def attach_source_sheet(df: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
    df = df.copy(); df["source_sheet"] = sheet_name; return df


def attach_pog_snapshot_month(df: pd.DataFrame, month) -> pd.DataFrame:
    df = df.copy(); df["pog_snapshot_month"] = month; return df


def unpivot_multi_promo(df: pd.DataFrame, max_slots: int = 5):
    suffix_pat = re.compile(r"^(.+)__(\d+)$")
    slot_groups: dict = {}
    for col in df.columns:
        m = suffix_pat.match(str(col))
        if m:
            fn, idx = m.group(1), int(m.group(2))
            slot_groups.setdefault(fn, {})[idx] = col

    if not slot_groups:
        return _attach_default_logical_ids(df), []

    multi = {f: s for f, s in slot_groups.items() if len(s) > 1}
    if not multi:
        return _attach_default_logical_ids(df), []

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
        return _attach_default_logical_ids(df), warnings

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
                output_row = {**{c: row[c] for c in shared}, **slot}
                base_row_id = output_row.get("source_row_id")
                if pd.notna(base_row_id) and str(base_row_id).strip():
                    logical_id = f"{base_row_id}:slot-{slot_idx}"
                    output_row["source_row_id"] = logical_id
                    output_row["logical_row_id"] = logical_id
                output_row["promo_slot_id"] = slot_idx
                rows_out.append(output_row)
                added = True
        if not added:
            output_row = {**{c: row[c] for c in shared}, **{fn: None for fn in allowed}}
            output_row["promo_slot_id"] = 1
            output_row["logical_row_id"] = output_row.get("source_row_id")
            rows_out.append(output_row)

    return pd.DataFrame(rows_out).reset_index(drop=True), warnings
