import importlib.util
from pathlib import Path
import random
import sys

import pandas as pd


def _module():
    path = Path(__file__).resolve().parents[1] / "modules" / "10_tem_r.py"
    spec = importlib.util.spec_from_file_location("tem_r_adversarial_hardening", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _row(location, item, stock, *, store="S1", pog="G1", shelf="1/1"):
    return {
        "STOREID": store,
        "POGCODE": pog,
        "FIXELID": shelf,
        "LOCATIONID": location,
        "ITEMID": item,
        "ITEMNAME": item,
        "TỒN": stock,
    }


def _final_representative(row):
    tem = row["TEM R"]
    if not pd.isna(tem):
        text = str(tem)
        if not text.startswith("KHÔNG CÓ") and not text.startswith("BỎ QUA"):
            return text.strip().upper()
        return None
    if row["TEM_R_STATUS"] == "Còn tồn - không cần Tem R":
        return str(row["ITEMID"]).strip().upper()
    return None


def test_native_positions_cannot_all_claim_one_stock_unit():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 1),
        _row(2, "PA", 1),
        _row(3, "PB", 2),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    final = [_final_representative(row) for _, row in plan.rows.iterrows()]
    assert final.count("PA") == 1
    assert final.count("PB") == 2
    assert plan.rows.loc[1, "TEM R"] == "PB"


def test_conflicting_store_stock_is_quarantined_instead_of_taking_max():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 2),
        _row(2, "PA", 10),
        _row(3, "P0", 0),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert plan.rows.loc[0, "TEM R"] == tem_r.STOCK_CONFLICT_MARKER
    assert plan.rows.loc[1, "TEM R"] == tem_r.STOCK_CONFLICT_MARKER
    assert plan.rows.loc[2, "TEM R"] == "KHÔNG CÓ SẢN PHẨM THAY THẾ"
    assert plan.rows["TEM R"].eq("PA").sum() == 0
    assert plan.exceptions["reason"].str.contains("Tồn kho mâu thuẫn").sum() == 2


def test_store_keys_are_case_insensitive_for_one_shared_capacity_pool():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 2, store="S1", pog="G1"),
        _row(2, "P0", 0, store="S1", pog="G1"),
        _row(1, "PA", 2, store="s1", pog="G2"),
        _row(2, "P9", 0, store="s1", pog="G2"),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert plan.rows["TEM R"].eq("PA").sum() == 0
    assert plan.rows.loc[1, "TEM R"] == "KHÔNG CÓ SẢN PHẨM THAY THẾ"
    assert plan.rows.loc[3, "TEM R"] == "KHÔNG CÓ SẢN PHẨM THAY THẾ"


def test_invalid_stock_row_still_reserves_native_position_capacity():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 2),
        _row(2, "PA", None),
        _row(3, "P0", 0),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert str(plan.rows.loc[1, "TEM R"]).startswith("BỎ QUA")
    assert plan.rows.loc[2, "TEM R"] == "KHÔNG CÓ SẢN PHẨM THAY THẾ"
    assert plan.rows["TEM R"].eq("PA").sum() == 0


def test_duplicate_physical_location_is_quarantined_not_guessed_as_extra_facing():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 2),
        _row(1, "PA", 2),
        _row(2, "P0", 0),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert plan.rows.loc[0, "TEM R"] == tem_r.DUPLICATE_POSITION_MARKER
    assert plan.rows.loc[1, "TEM R"] == tem_r.DUPLICATE_POSITION_MARKER
    assert plan.rows.loc[2, "TEM R"] == "KHÔNG CÓ SẢN PHẨM THAY THẾ"
    assert plan.rows["TEM R"].eq("PA").sum() == 0


def test_invalid_row_blocks_full_shelf_rearrangement():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 3),
        _row(2, "PX", None),
        _row(3, "PB", 1),
        _row(4, "P0", 0),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert plan.rows.loc[3, "TEM R"] == "PA"
    assert plan.rows["TEM_R_STATUS"].fillna("").str.contains(
        "Sắp xếp lại toàn kệ"
    ).sum() == 0


def test_seeded_random_layouts_never_exceed_stock_or_cross_shelf():
    tem_r = _module()
    rng = random.Random(20260930)
    items = ["PA", "PB", "PC", "PD"]

    for _ in range(300):
        stock = {item: rng.randint(0, 5) for item in items}
        rows = []
        shelf_sources = {}
        for pog in ("G1", "G2"):
            count = rng.randint(1, 5)
            locations = sorted(rng.sample(range(1, 10), count))
            for location in locations:
                item = rng.choice(items)
                store = "s1" if rng.random() < 0.35 else "S1"
                rows.append(_row(
                    location,
                    item,
                    stock[item],
                    store=store,
                    pog=pog,
                ))
                shelf_sources.setdefault(("S1", pog, "1/1"), set()).add(item)

        frame = pd.DataFrame(rows)
        plan = tem_r.build_tem_r_plan(frame)

        assigned = {item: 0 for item in items}
        for _, row in plan.rows.iterrows():
            representative = _final_representative(row)
            if representative in assigned:
                assigned[representative] += 1
                group = (
                    str(row["STOREID"]).strip().upper(),
                    str(row["POGCODE"]).strip().upper(),
                    str(row["FIXELID"]).strip().upper(),
                )
                assert representative in shelf_sources[group]

        for item in items:
            assert assigned[item] <= stock[item], (
                item,
                assigned[item],
                stock[item],
                plan.rows[[
                    "STOREID", "POGCODE", "FIXELID", "LOCATIONID",
                    "ITEMID", "TỒN", "TEM R", "TEM_R_STATUS",
                ]].to_dict("records"),
            )


def test_facade_delegates_to_core_without_recursive_rebinding():
    tem_r = _module()

    assert tem_r._core.build_tem_r_plan is not tem_r.build_tem_r_plan

    frame = pd.DataFrame([
        _row(1, "PA", 2),
        _row(2, "P0", 0),
    ])
    plan = tem_r.build_tem_r_plan(frame)
    assert plan.rows.loc[1, "TEM R"] == "PA"


def test_shared_store_spare_goes_to_globally_nearest_target_not_first_shelf():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 3, pog="G1"),
        _row(9, "P0", 0, pog="G1"),
        _row(10, "PA", 3, pog="G2"),
        _row(11, "P9", 0, pog="G2"),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert plan.rows.loc[1, "TEM R"] == "KHÔNG CÓ SẢN PHẨM THAY THẾ"
    assert plan.rows.loc[3, "TEM R"] == "PA"


def test_placeholder_business_keys_are_quarantined():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 2, store="NAN"),
        _row(2, "P0", 0, store="NAN"),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert plan.exceptions["reason"].str.contains("Thiếu mã cửa hàng").all()
    assert plan.rows["TEM R"].isna().all()


def test_boolean_location_is_not_accepted_as_location_one():
    tem_r = _module()
    frame = pd.DataFrame([
        {
            "STOREID": "S1",
            "POGCODE": "G1",
            "FIXELID": "1/1",
            "LOCATIONID": True,
            "ITEMID": "PA",
            "ITEMNAME": "A",
            "TỒN": 2,
        },
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert plan.exceptions.iloc[0]["reason"] == "Thiếu hoặc sai vị trí kệ"
