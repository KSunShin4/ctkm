import pandas as pd

import main


def _fact(item_id, campaign):
    return {
        "item_id": item_id,
        "item_name": f"Name {item_id}",
        "campaign_name": campaign,
        "promo_from": pd.Timestamp("2026-08-01"),
        "promo_to": pd.Timestamp("2026-08-31"),
    }


def test_confirmation_distinguishes_ctkm_clearance_and_overlap():
    ctkm = pd.DataFrame([_fact("P1", "Monthly"), _fact("P2", "Monthly")])
    clearance = pd.DataFrame([_fact("P2", "Clearance"), _fact("P3", "Clearance")])

    result = main._build_ctkm_clearance_confirmation(ctkm, clearance)

    statuses = result.groupby("item_id")["trang_thai_doi_chieu"].first().to_dict()
    assert statuses == {
        "P1": "Chỉ CTKM",
        "P2": "Có cả CTKM và Clearance",
        "P3": "Chỉ Clearance",
    }
    assert set(result["nguon_chuong_trinh"]) == {"CTKM", "CLEARANCE"}
    assert set(result["xac_nhan_ap_dung"]) == {"Chưa xác nhận"}
    assert set(result.loc[result["item_id"] == "P2", "quan_he_thoi_gian"]) == {
        "Trùng thời gian - cần xác nhận"
    }
    assert result["source_row_id"].nunique() == len(result)


def test_standard_clearance_headers_are_mapped_without_ai():
    frame = pd.DataFrame(columns=[
        "Kênh áp dụng", "Item code", "Product Name", "Promo UoM", "Normal",
        "Promo", "Scheme detail for customer", "From", "To", "Campaign",
    ])

    mapping = main._infer_standard_fact_mapping(frame)

    assert mapping["Item code"] == "item_id"
    assert mapping["Campaign"] == "campaign_name"
    assert mapping["From"] == "promo_from"
    assert mapping["To"] == "promo_to"
    assert mapping["Kênh áp dụng"] == "channel"


def test_fefo_actions_keep_clearance_only_items_and_source():
    promotions = pd.DataFrame([
        {
            **_fact("P1", "Monthly"),
            "program_source": "CTKM",
        },
        {
            **_fact("P999", "Clearance"),
            "program_source": "CLEARANCE",
        },
    ])

    actions = main.RC.build_fefo_action_frame(
        promotions, "2026-08", business_date=pd.Timestamp("2026-08-15"),
    )

    assert set(actions["item_id"]) == {"P1", "P999"}
    clearance_row = actions.loc[actions["item_id"] == "P999"].iloc[0]
    assert clearance_row["program_source"] == "CLEARANCE"
    assert clearance_row["ngay_gan_tem"] == pd.Timestamp("2026-08-01")
    assert clearance_row["ngay_thao_tem"] == pd.Timestamp("2026-09-01")


def test_action_source_keeps_clearance_when_sku_also_exists_in_ctkm_and_preserves_blank_campaign():
    ctkm = pd.DataFrame([_fact("P1", "Monthly"), _fact("P2", "Monthly")])
    clearance = pd.DataFrame([
        _fact("P2", None),
        _fact("p3", None),
    ])

    result = main._build_promo_action_source(ctkm, clearance)

    assert list(result["item_id"]) == ["P1", "P2", "P2", "p3"]
    clearance_rows = result[result["program_source"].eq("CLEARANCE")]
    assert clearance_rows["campaign_name"].isna().all()
    assert clearance_rows["item_id"].tolist() == ["P2", "p3"]


def test_invalid_promotion_period_is_never_put_in_attach_or_remove_list():
    invalid = pd.DataFrame([{
        **_fact("P4", "Invalid"),
        "promo_from": pd.Timestamp("2026-08-31"),
        "promo_to": pd.Timestamp("2026-08-01"),
        "program_source": "CLEARANCE",
    }])

    actions = main.RC.build_fefo_action_frame(
        invalid, "2026-08", business_date=pd.Timestamp("2026-08-15"),
    )

    assert actions.iloc[0]["action"] == "review"
    assert actions.iloc[0]["reason"] == "ngay_bat_dau_sau_ngay_ket_thuc"
