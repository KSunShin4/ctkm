import pandas as pd

import main


def _promo(**overrides):
    row = {
        "item_id": "P1001",
        "item_name": "Product A",
        "promo_uom": "Hộp",
        "key_channel": "All channel",
        "channel": "OFFLINE",
        "campaign_name": "FULL MONTH",
        "campaign_detail": "Giảm 10%",
        "promo_from": pd.Timestamp("2026-09-01"),
        "promo_to": pd.Timestamp("2026-09-30"),
        "normal_price": 100000,
        "promo_price": 90000,
        "product_type": "Medicine",
        "program_source": "CTKM",
        "source_sheet": "Monthly",
    }
    row.update(overrides)
    return row


def _actions(rows):
    return main.RC.build_fefo_action_frame(
        pd.DataFrame(rows),
        "2026-09",
        business_date=pd.Timestamp("2026-09-15"),
        overlap_warnings=[],
    )


def test_descriptive_source_differences_do_not_make_same_promotion_conflict_with_itself():
    frame = pd.DataFrame([
        _promo(item_name="Product A", product_type="Medicine", source_sheet="Monthly A"),
        _promo(item_name="Product A renamed", product_type="Other label", source_sheet="Monthly B"),
    ])

    warnings = main.RC.detect_campaign_time_overlaps(frame)
    actions = _actions(frame.to_dict("records"))

    assert warnings == []
    assert actions["promotion_id"].nunique() == 1
    # Descriptive business rows remain distinct because the source display values differ.
    assert actions["item_name"].tolist() == ["Product A", "Product A renamed"]
    assert actions["product_type"].tolist() == ["Medicine", "Other label"]


def test_campaign_detail_is_part_of_promotion_identity_and_remains_a_blocking_offer_conflict():
    frame = pd.DataFrame([
        _promo(campaign_detail="Giảm 10%"),
        _promo(campaign_detail="Mua 2 tặng 1"),
    ])

    warnings = main.RC.detect_campaign_time_overlaps(frame)
    actions = _actions(frame.to_dict("records"))

    assert len(warnings) == 1
    assert warnings[0].is_blocking is True
    assert actions["promotion_id"].nunique() == 2


def test_price_uom_and_scope_fields_each_participate_in_stable_promotion_identity():
    variants = [
        _promo(),
        _promo(promo_price=85000),
        _promo(promo_uom="Vỉ"),
        _promo(key_channel="Others"),
        _promo(channel="WEBAPP"),
    ]

    actions = _actions(variants)

    assert actions["promotion_id"].nunique() == len(variants)


def test_source_lineage_does_not_change_stable_promotion_identity():
    first = _promo(source_row_id="CTKM:Monthly:10")
    second = _promo(source_row_id="CTKM:Monthly:999")

    actions = _actions([first, second])

    assert actions["promotion_id"].nunique() == 1
    # Exact duplicate operational rows are consolidated; all lineage survives in
    # source_row_ids/source_row_count for Audit hành động and traceability.
    assert len(actions) == 1
    assert actions.loc[0, "source_row_count"] == 2
    assert set(actions.loc[0, "source_row_ids"].split(" | ")) == {
        "CTKM:Monthly:10", "CTKM:Monthly:999"
    }
    assert actions.loc[0, "duplicate_status"] == "Đã gom dòng trùng hoàn toàn"



def test_key_channel_alone_is_part_of_stable_promotion_and_task_identity():
    rows = [
        _promo(key_channel="Offline", channel="OFFLINE"),
        _promo(key_channel="Others", channel="OFFLINE"),
    ]

    actions = _actions(rows)

    assert len(actions) == 2
    assert actions["promotion_id"].nunique() == 2
    assert actions["task_id"].nunique() == 2
    assert set(actions["key_channel"]) == {"Offline", "Others"}
    assert set(actions["channel"]) == {"OFFLINE"}
