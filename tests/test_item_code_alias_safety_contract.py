import pandas as pd

import main


BUSINESS_DATE = pd.Timestamp("2026-09-15")


def _row(old_code, new_code, campaign):
    return {
        "KEY Channel": "All channel",
        "Channel": "ALL CHANNEL",
        "Item code 1 (NEW)": new_code,
        "Item code 2": old_code,
        "Product Name": f"Product {old_code}",
        "Promo UoM": "Hop",
        "Normal": 100000,
        "Promo": 90000,
        "Scheme detail for customer": "Discount 10%",
        "From": pd.Timestamp("2026-09-01"),
        "To": pd.Timestamp("2026-09-30"),
        "Campaign": campaign,
        "Product type": "H&B",
    }


def _process(rows):
    raw = pd.DataFrame(rows)
    mapping = main._infer_standard_fact_mapping(raw)
    return main._process(
        "TỔNG HỢP CTKM UPDATE",
        raw,
        main.SCHEMA["fact_fields"],
        [],
        True,
        [],
        mapping_override=mapping,
        source_excel_rows=list(range(3, 3 + len(raw))),
        source_prefix="CTKM",
    )


def _pog(item_id):
    return {
        "item_id": item_id,
        "store_id": "S1",
        "pog_code": "A",
        "location_id": "1",
        "facing": 1,
        "pog_snapshot_month": "2026-09",
        "source_row_id": "POG:Export:10",
    }


def test_replacement_code_that_is_also_direct_source_code_is_not_used_as_alias():
    processed = _process([
        _row("P1001", "P9001", "Legacy-code promotion"),
        _row("P9001", None, "Direct new-code promotion"),
    ])
    pog = pd.DataFrame([_pog("P9001")])

    joined = main.JN.join_ctkm_pog(processed, pog)

    # P9001 belongs to the direct P9001 promotion. It must not be stolen by the
    # P1001 -> P9001 migration alias.
    assert len(joined.df_matched) == 1
    assert joined.df_matched.loc[0, "item_id__ctkm"] == "P9001"
    assert joined.df_matched.loc[0, "item_id__pog"] == "P9001"
    assert len(joined.df_ctkm_only) == 1
    assert joined.df_ctkm_only.loc[0, "item_id"] == "P1001"
    assert joined.df_pog_only.empty

    actions = main.RC.build_fefo_action_frame(
        processed, "2026-09", pog, business_date=BUSINESS_DATE,
    )
    by_item = actions.set_index("item_id")
    assert by_item.loc["P1001", "item_code_transition_status"] == "Mơ hồ - không tự remap"
    assert by_item.loc["P1001", "location_completeness"] == "Không tìm thấy SKU trong POG"
    assert by_item.loc["P9001", "location_completeness"] == "Đủ vị trí"
    assert by_item.loc["P9001", "matched_pog_item_id"] == "P9001"
    assert by_item.loc["P9001", "pog_match_code_type"] == "Khớp mã nguồn"


def test_non_sku_replacement_text_is_never_used_as_pog_alias():
    processed = _process([
        _row("P1001", "REVIEW NOTE", "Promotion A"),
    ])
    pog = pd.DataFrame([_pog("REVIEW NOTE")])

    joined = main.JN.join_ctkm_pog(processed, pog)
    assert joined.df_matched.empty
    assert len(joined.df_ctkm_only) == 1
    assert len(joined.df_pog_only) == 1

    actions = main.RC.build_fefo_action_frame(
        processed, "2026-09", pog, business_date=BUSINESS_DATE,
    )
    assert actions.loc[0, "item_id"] == "P1001"
    assert actions.loc[0, "new_item_id"] == "REVIEW NOTE"
    assert actions.loc[0, "item_code_transition_status"] == "Mơ hồ - không tự remap"
    assert actions.loc[0, "location_completeness"] == "Không tìm thấy SKU trong POG"
