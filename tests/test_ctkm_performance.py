import importlib.util
from pathlib import Path
import sys

import pandas as pd


def _performance_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "modules" / "ctkm_performance.py"
    spec = importlib.util.spec_from_file_location("ctkm_performance_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _item_key(value):
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().upper()
    return text or None


def test_fast_confirmation_preserves_relation_labels():
    perf = _performance_module()
    ctkm = pd.DataFrame([
        {
            "item_id": "P1", "campaign_name": "A",
            "promo_from": "2026-09-01", "promo_to": "2026-09-10",
            "source_sheet": "CTKM", "source_row_id": "CTKM:CTKM:2",
        },
        {
            "item_id": "P2", "campaign_name": "B",
            "promo_from": None, "promo_to": "2026-09-10",
            "source_sheet": "CTKM", "source_row_id": "CTKM:CTKM:3",
        },
        {
            "item_id": "P3", "campaign_name": "C",
            "promo_from": "2026-09-01", "promo_to": "2026-09-10",
            "source_sheet": "CTKM", "source_row_id": "CTKM:CTKM:4",
        },
    ])
    clearance = pd.DataFrame([
        {
            "item_id": "P1", "campaign_name": "Clearance exact",
            "promo_from": "2026-09-01", "promo_to": "2026-09-10",
            "source_sheet": "Clearance", "source_row_id": "CLEARANCE:Clearance:2",
        },
        {
            "item_id": "P2", "campaign_name": "Clearance P2",
            "promo_from": "2026-09-02", "promo_to": "2026-09-12",
            "source_sheet": "Clearance", "source_row_id": "CLEARANCE:Clearance:3",
        },
        {
            "item_id": "P4", "campaign_name": "Clearance only",
            "promo_from": "2026-09-01", "promo_to": "2026-09-10",
            "source_sheet": "Clearance", "source_row_id": "CLEARANCE:Clearance:4",
        },
    ])

    result = perf.build_ctkm_clearance_confirmation_fast(
        ctkm, clearance, make_item_key=_item_key
    )

    p1 = result[result["item_id"] == "P1"]
    assert set(p1["quan_he_thoi_gian"]) == {"Trùng thời gian - cần xác nhận"}

    p2_ctkm = result[
        (result["item_id"] == "P2")
        & (result["nguon_chuong_trinh"] == "CTKM")
    ].iloc[0]
    assert p2_ctkm["quan_he_thoi_gian"] == "Thiếu ngày - cần xác nhận"

    p3 = result[result["item_id"] == "P3"].iloc[0]
    p4 = result[result["item_id"] == "P4"].iloc[0]
    assert p3["trang_thai_doi_chieu"] == "Chỉ CTKM"
    assert p4["trang_thai_doi_chieu"] == "Chỉ Clearance"
    assert p3["quan_he_thoi_gian"] == "Không có nguồn còn lại để đối chiếu"
    assert p4["quan_he_thoi_gian"] == "Không có nguồn còn lại để đối chiếu"


def test_fast_confirmation_detects_overlap_without_exact_match():
    perf = _performance_module()
    ctkm = pd.DataFrame([{
        "item_id": "P1", "campaign_name": "A",
        "promo_from": "2026-09-01", "promo_to": "2026-09-10",
        "source_sheet": "CTKM",
    }])
    clearance = pd.DataFrame([{
        "item_id": "P1", "campaign_name": "B",
        "promo_from": "2026-09-05", "promo_to": "2026-09-15",
        "source_sheet": "Clearance",
    }])

    result = perf.build_ctkm_clearance_confirmation_fast(
        ctkm, clearance, make_item_key=_item_key
    )

    assert set(result["quan_he_thoi_gian"]) == {"Chồng lấn thời gian - cần xác nhận"}
