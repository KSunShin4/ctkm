import importlib.util
from itertools import product
from pathlib import Path
import random
import sys

import pandas as pd


def _module():
    path = Path(__file__).resolve().parents[1] / "modules" / "10_tem_r.py"
    name = "tem_r_algorithm_audit"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
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


def test_global_min_cost_assignment_avoids_pair_greedy_trap():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "P0", 0),
        _row(3, "PA", 2),
        _row(4, "P9", 0),
        _row(5, "PB", 2),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    # Pair-greedy can choose 4->PA first and then force 1->PB (distance 5).
    # Global optimum is 1->PA and 4->PB (distance 3).
    assert plan.rows.loc[0, "TEM R"] == "PA"
    assert plan.rows.loc[2, "TEM R"] == "PB"


def test_store_identity_is_case_insensitive_for_shared_capacity():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 3, store="S1", pog="G1"),
        _row(2, "P0", 0, store="S1", pog="G1"),
        _row(1, "PA", 3, store=" s1 ", pog="G2"),
        _row(2, "P9", 0, store=" s1 ", pog="G2"),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    # Stock PA=3, two original PA positions reserve two units, so only one
    # replacement is available across both case variants of the same store.
    assert plan.rows["TEM R"].eq("PA").sum() == 1
    assert plan.rows["TEM R"].eq("KHÔNG CÓ SẢN PHẨM THAY THẾ").sum() == 1


def test_shelf_identity_is_case_insensitive_for_candidate_visibility():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 2, store="S1", pog="G1", shelf="A"),
        _row(2, "P0", 0, store="s1", pog="g1", shelf=" a "),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert plan.rows.loc[1, "TEM R"] == "PA"


def test_conflicting_store_level_stock_is_quarantined_not_maxed():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 4),
        _row(2, "PA", 3),
        _row(3, "P0", 0),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert plan.rows.loc[0, "TEM_R_STATUS"] == "Tồn kho không nhất quán giữa các dòng cùng mã"
    assert plan.rows.loc[1, "TEM_R_STATUS"] == "Tồn kho không nhất quán giữa các dòng cùng mã"
    assert plan.rows.loc[2, "TEM R"] == "KHÔNG CÓ SẢN PHẨM THAY THẾ"
    assert (plan.exceptions["reason"] == "Tồn kho không nhất quán giữa các dòng cùng mã").sum() == 2


def test_stock_below_existing_pog_positions_is_not_silently_accepted():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 1),
        _row(2, "PA", 1),
        _row(3, "P0", 0),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    expected = "Tồn kho (1) nhỏ hơn số vị trí POG hiện có (2)"
    assert plan.rows.loc[0, "TEM_R_STATUS"] == expected
    assert plan.rows.loc[1, "TEM_R_STATUS"] == expected
    assert plan.rows.loc[2, "TEM R"] == "KHÔNG CÓ SẢN PHẨM THAY THẾ"


def test_duplicate_physical_shelf_coordinate_is_quarantined():
    tem_r = _module()
    frame = pd.DataFrame([
        _row(1, "PA", 2),
        _row(1, "PB", 2),
        _row(2, "P0", 0),
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert plan.rows.loc[0, "TEM_R_STATUS"] == "Trùng vị trí kệ trong file Tem R"
    assert plan.rows.loc[1, "TEM_R_STATUS"] == "Trùng vị trí kệ trong file Tem R"
    assert plan.rows.loc[2, "TEM R"] == "KHÔNG CÓ SẢN PHẨM THAY THẾ"


def _brute_objective(target_positions, source_locations, capacities):
    items = list(capacities)
    best = None
    for choices in product(items + [None], repeat=len(target_positions)):
        used = {item: 0 for item in items}
        assigned = 0
        distance = 0.0
        valid = True
        for target_pos, item in zip(target_positions, choices):
            if item is None:
                continue
            used[item] += 1
            if used[item] > capacities[item]:
                valid = False
                break
            assigned += 1
            distance += min(abs(source - target_pos) for source in source_locations[item])
        if not valid:
            continue
        score = (-assigned, distance)
        if best is None or score < best:
            best = score
    return best


def test_min_cost_helper_matches_bruteforce_on_250_small_cases():
    tem_r = _module()
    rng = random.Random(20260930)

    for _ in range(250):
        target_count = rng.randint(1, 4)
        item_count = rng.randint(1, 3)
        target_positions = rng.sample(range(1, 13), target_count)
        items = [f"P{index}" for index in range(item_count)]
        source_locations = {
            item: [rng.randint(1, 12)]
            for item in items
        }
        capacities = {
            item: rng.randint(0, 2)
            for item in items
        }
        target_indices = list(range(target_count))
        frame = pd.DataFrame({"_location": target_positions}, index=target_indices)

        proposed = tem_r._allocate_same_shelf_min_cost(
            target_indices,
            source_locations,
            capacities,
            frame,
        )
        assigned = {
            idx: item for idx, item in proposed.items()
            if item is not None
        }
        actual = (
            -len(assigned),
            sum(
                min(abs(source - target_positions[idx]) for source in source_locations[item])
                for idx, item in assigned.items()
            ),
        )
        expected = _brute_objective(target_positions, source_locations, capacities)
        assert actual == expected
