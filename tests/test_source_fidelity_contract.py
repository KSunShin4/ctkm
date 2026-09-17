import pandas as pd

import main


def _promotion(row_id: str, note: str):
    return {
        "item_id": "P29598",
        "item_key": "P29598",
        "item_name": "Nestle Nutren Junior Sua Bot Cho Tre (1-10Y) Lon 400G",
        "promo_uom": "Lon",
        "key_channel": None,
        "channel": "All Channel",
        "campaign_name": "Clearance Isstop 0-2",
        "campaign_detail": "Discount 67000",
        "promo_from": 46266,
        "promo_to": 46295,
        "normal_price": 353000,
        "promo_price": 286000,
        "product_type": "H&B",
        "program_source": "CLEARANCE",
        "source_sheet": "TỔNG HỢP CTKM UPDATE",
        "source_row_id": row_id,
        "source_excel_row": int(row_id.rsplit(":", 1)[-1]),
        # Representative real-file passthrough columns. These are not part of
        # action classification, but must remain exact in Audit hành động.
        "extra__NOTE - Cần lưu ý": note,
        "extra__New P code": "\xa0",
        "extra__Unit 2": "\xa0",
        "extra__RSP (+VAT)": 353000,
        "extra__Saving per unit": 67000,
        "extra__Out": 0.08,
        "extra__Support type for customer": "Cash discount amount",
        "extra__Big cat": "Health and Beauty",
        "extra__Cat 2": "Nutrition Food",
    }


def test_action_audit_restores_exact_source_passthrough_columns():
    source = pd.DataFrame([
        _promotion("CLEARANCE:TỔNG HỢP CTKM UPDATE:406", "  giữ nguyên khoảng trắng  ")
    ])

    actions = main.RC.build_fefo_action_frame(
        source,
        "2026-09",
        business_date=pd.Timestamp("2026-09-17"),
    )

    assert len(actions) == 1
    row = actions.iloc[0]
    assert row["extra__NOTE - Cần lưu ý"] == "  giữ nguyên khoảng trắng  "
    assert row["extra__New P code"] == "\xa0"
    assert row["extra__Unit 2"] == "\xa0"
    assert row["extra__RSP (+VAT)"] == 353000
    assert row["extra__Saving per unit"] == 67000
    assert row["extra__Out"] == 0.08
    assert row["extra__Support type for customer"] == "Cash discount amount"
    assert row["extra__Big cat"] == "Health and Beauty"
    assert row["extra__Cat 2"] == "Nutrition Food"


def test_different_raw_extra_values_are_not_silently_collapsed():
    source = pd.DataFrame([
        _promotion("CLEARANCE:TỔNG HỢP CTKM UPDATE:406", "NOTE A"),
        _promotion("CLEARANCE:TỔNG HỢP CTKM UPDATE:407", "NOTE B"),
    ])

    actions = main.RC.build_fefo_action_frame(
        source,
        "2026-09",
        business_date=pd.Timestamp("2026-09-17"),
    )

    assert len(actions) == 2
    assert actions["extra__NOTE - Cần lưu ý"].tolist() == ["NOTE A", "NOTE B"]
    assert actions["source_row_id"].tolist() == [
        "CLEARANCE:TỔNG HỢP CTKM UPDATE:406",
        "CLEARANCE:TỔNG HỢP CTKM UPDATE:407",
    ]


def test_exact_duplicate_raw_rows_keep_all_lineage_and_one_exact_value():
    first = _promotion("CLEARANCE:TỔNG HỢP CTKM UPDATE:406", "SAME")
    second = dict(first)
    second["source_row_id"] = "CLEARANCE:TỔNG HỢP CTKM UPDATE:407"
    second["source_excel_row"] = 407
    source = pd.DataFrame([first, second])

    actions = main.RC.build_fefo_action_frame(
        source,
        "2026-09",
        business_date=pd.Timestamp("2026-09-17"),
    )

    assert len(actions) == 1
    row = actions.iloc[0]
    assert row["extra__NOTE - Cần lưu ý"] == "SAME"
    assert row["source_row_count"] == 2
    assert set(part.strip() for part in row["source_row_ids"].split("|")) == {
        "CLEARANCE:TỔNG HỢP CTKM UPDATE:406",
        "CLEARANCE:TỔNG HỢP CTKM UPDATE:407",
    }
