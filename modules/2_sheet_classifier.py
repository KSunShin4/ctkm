# -*- coding: utf-8 -*-
"""Module 2: Sheet Classifier — phan loai FACT vs DIMENSION bang rule tuong minh."""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Literal
import pandas as pd
from .config_loader import SHEET_ROLE_RULES

Role = Literal["FACT","DIMENSION"]
_DATE_PAIRS = [("from","to"),("tu ngay","den ngay"),("ngay bat dau","ngay ket thuc"),("start","end")]
_CAMPAIGN_KW = ["campaign","chuong trinh","chương trình","ctkm","promotion","scheme"]

@dataclass
class SheetClassification:
    sheet_name: str
    role: Role
    reason: str
    needs_review: bool = False

def _norm(s): return str(s).strip().lower()

def classify_sheet(sheet_name: str, df: pd.DataFrame) -> SheetClassification:
    cols = list(df.columns)
    norm_cols = [_norm(c) for c in cols]
    has_date_pair = any(any(l in c for c in norm_cols) and any(r in c for c in norm_cols)
                        for l,r in _DATE_PAIRS)
    has_campaign  = any(any(kw in c for kw in _CAMPAIGN_KW) for c in norm_cols)
    signals = sum([has_date_pair, has_campaign])
    min_req = SHEET_ROLE_RULES["fact_rules"]["min_signals_required"]
    if signals >= min_req:
        reasons = []
        if has_date_pair: reasons.append("co cap cot ngay bat dau/ket thuc")
        if has_campaign:  reasons.append("co tu khoa campaign trong ten cot")
        return SheetClassification(sheet_name, "FACT", "; ".join(reasons))
    if len(cols) <= 4 and not has_date_pair:
        return SheetClassification(sheet_name, "DIMENSION",
                                   f"it cot ({len(cols)}) va khong co cap ngay ro rang")
    return SheetClassification(sheet_name, "FACT",
                               "khong ro rang — mac dinh FACT, CAN KIEM TRA LAI", needs_review=True)

def classify_all_sheets(sheets: dict) -> dict:
    return {name: classify_sheet(name, df) for name, df in sheets.items()}
