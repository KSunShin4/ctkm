import importlib.util
from pathlib import Path
import sys

import pandas as pd


def _module():
    path = Path(__file__).resolve().parents[1] / "modules" / "10_tem_r.py"
    spec = importlib.util.spec_from_file_location("tem_r_store_capacity", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_store_stock_capacity_is_shared_across_shelves():
    tem_r = _module()
    frame = pd.DataFrame([
        # PA tồn cấp cửa hàng = 3. Hai vị trí PA đang có ở hai kệ giữ 2 đơn vị,
        # nên toàn cửa hàng chỉ còn đúng 1 đơn vị để làm Tem R.
        {"STOREID": "S1", "POGCODE": "G1", "FIXELID": "1/1", "LOCATIONID": 1,
         "ITEMID": "PA", "ITEMNAME": "A", "TỒN": 3},
        {"STOREID": "S1", "POGCODE": "G1", "FIXELID": "1/1", "LOCATIONID": 2,
         "ITEMID": "P0", "ITEMNAME": "Zero 1", "TỒN": 0},
        {"STOREID": "S1", "POGCODE": "G2", "FIXELID": "1/1", "LOCATIONID": 1,
         "ITEMID": "PA", "ITEMNAME": "A", "TỒN": 3},
        {"STOREID": "S1", "POGCODE": "G2", "FIXELID": "1/1", "LOCATIONID": 2,
         "ITEMID": "P9", "ITEMNAME": "Zero 2", "TỒN": 0},
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert plan.rows.loc[1, "TEM R"] == "PA"
    assert plan.rows.loc[3, "TEM R"] == "KHÔNG CÓ SẢN PHẨM THAY THẾ"
    assert plan.rows["TEM R"].eq("PA").sum() == 1
    positive_capacity = plan.audit.loc[
        plan.audit["ITEMID"].eq("PA"), "NĂNG_LỰC_CÒN_LẠI"
    ].tolist()
    assert positive_capacity == [0, 0]


def test_na_row_is_audited_but_excluded_from_allocation_layout():
    tem_r = _module()
    frame = pd.DataFrame([
        {"STOREID": "S1", "POGCODE": "G1", "FIXELID": "1/1", "LOCATIONID": 1,
         "ITEMID": "PA", "ITEMNAME": "A", "TỒN": 2},
        {"STOREID": "S1", "POGCODE": "G1", "FIXELID": "1/1", "LOCATIONID": 2,
         "ITEMID": "PX", "ITEMNAME": "Ignored", "TỒN": "#N/A"},
        {"STOREID": "S1", "POGCODE": "G1", "FIXELID": "1/1", "LOCATIONID": 3,
         "ITEMID": "P0", "ITEMNAME": "Zero", "TỒN": 0},
    ])

    plan = tem_r.build_tem_r_plan(frame, max_location_distance=2)

    assert plan.rows.loc[1, "TEM R"] == "BỎ QUA - TỒN KHO LỖI #N/A"
    assert plan.rows.loc[2, "TEM R"] == "PA"
    assert plan.exceptions.iloc[0]["ITEMID"] == "PX"


def test_no_replacement_exception_uses_real_excel_row():
    tem_r = _module()
    frame = pd.DataFrame([
        {"_excel_row": 17, "STOREID": "S1", "POGCODE": "G1", "FIXELID": "1/1",
         "LOCATIONID": 1, "ITEMID": "P0", "ITEMNAME": "Zero", "TỒN": 0},
    ])

    plan = tem_r.build_tem_r_plan(frame)

    assert plan.rows.loc[0, "TEM R"] == "KHÔNG CÓ SẢN PHẨM THAY THẾ"
    assert plan.exceptions.iloc[0]["row"] == 17
