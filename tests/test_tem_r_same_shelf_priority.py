import importlib.util
from pathlib import Path
import sys

import pandas as pd


def _module():
    module_path = Path(__file__).resolve().parents[1] / "modules" / "10_tem_r.py"
    spec = importlib.util.spec_from_file_location("tem_r_same_shelf_priority", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(location, item, stock, *, store="CONFECT", pog="CTCONF", shelf="1/5"):
    return {
        "STOREID": store,
        "POGCODE": pog,
        "FIXELID": shelf,
        "LOCATIONID": location,
        "ITEMID": item,
        "ITEMNAME": item,
        "TỒN": stock,
    }


def test_far_same_shelf_stock_is_not_rejected_by_legacy_distance_limit():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 2),
        _row(7, "P0", 0),
    ])

    plan = tem_r.build_tem_r_plan(frame, max_location_distance=1)

    assert plan.rows.loc[1, "TEM R"] == "PA"
    assert plan.rows.loc[1, "TEM_R_STATUS"] == "Tồn 0 - mã thay đã nằm liền nhóm"


def test_nearest_same_shelf_candidate_still_wins_first():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 2),
        _row(2, "P0", 0),
        _row(9, "P9", 0),
        _row(10, "PB", 2),
    ])

    plan = tem_r.build_tem_r_plan(frame, max_location_distance=1)

    assert plan.rows.loc[1, "TEM R"] == "PA"
    assert plan.rows.loc[2, "TEM R"] == "PB"


def test_realistic_confect_shelf_uses_far_stock_and_rearranges_split_group():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(2, "P08844", 34),
        _row(3, "P29216", 0),
        _row(4, "P29217", 1),
        _row(5, "P25749", 0),
        _row(6, "P25748", 0),
    ])

    plan = tem_r.build_tem_r_plan(frame, max_location_distance=1)

    # P08844 has ample store-level spare stock. The old hard ±1 rule rejected
    # locations 5 and 6; the new rule keeps the same shelf and ranks by distance
    # without excluding them.
    assert "KHÔNG CÓ SẢN PHẨM THAY THẾ" not in plan.rows["TEM R"].fillna("").tolist()

    # Initial allocation would split P08844 around P29217. Full-shelf
    # rearrangement must group equal codes contiguously while preserving counts.
    assert plan.rows["TEM R"].tolist() == [
        "P08844",
        "P08844",
        "P08844",
        "P08844",
        "P29217",
    ]
    assert plan.rows["TEM R"].tolist().count("P08844") == 4
    assert plan.rows["TEM R"].tolist().count("P29217") == 1
    assert set(plan.rows["TEM_R_STATUS"]) == {"Sắp xếp lại toàn kệ - gom mã P liền nhau"}


def test_existing_split_product_group_is_compacted_when_a_target_triggers_relayout():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 4),
        _row(2, "PB", 1),
        _row(5, "PA", 4),
        _row(6, "P0", 0),
    ])

    plan = tem_r.build_tem_r_plan(frame, max_location_distance=1)

    assert plan.rows["TEM R"].tolist() == ["PA", "PA", "PA", "PB"]
    assert plan.rows["TEM R"].tolist().count("PA") == 3
    assert plan.rows["TEM R"].tolist().count("PB") == 1
