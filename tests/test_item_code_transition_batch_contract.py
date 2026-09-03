import pandas as pd

import main
from modules.item_code_identity import build_transition_identity


def _promotion(item_id, *, new_item_id=None, source="CTKM", campaign="A", channel="Offline"):
    return {
        "item_id": item_id,
        "item_key": main.NM.make_item_key(item_id),
        "new_item_id": new_item_id,
        "new_item_key": main.NM.make_item_key(new_item_id),
        "item_name": f"Product {item_id}",
        "promo_uom": "Hop",
        "key_channel": "Offline",
        "channel": channel,
        "campaign_name": campaign,
        "campaign_detail": "Discount",
        "promo_from": pd.Timestamp("2026-09-01"),
        "promo_to": pd.Timestamp("2026-09-30"),
        "normal_price": 100000,
        "promo_price": 90000,
        "product_type": "H&B",
        "program_source": source,
        "source_sheet": "Monthly" if source == "CTKM" else "Clearance",
        "source_row_id": f"{source}:{item_id}:{campaign}",
        "in_report_scope": True,
    }


def _pog(item_id):
    return {
        "item_id": item_id,
        "store_id": "S1",
        "pog_code": "A",
        "location_id": "1",
        "facing": 1,
        "pog_snapshot_month": "2026-09",
        "source_row_id": f"POG:{item_id}",
    }


def test_overlap_detects_direct_new_code_row_as_same_transition_product():
    frame = pd.DataFrame([
        _promotion("P1001", new_item_id="P9001", campaign="Legacy offer"),
        _promotion("P9001", source="CLEARANCE", campaign="Direct new-code offer"),
    ])

    warnings = main.RC.detect_campaign_time_overlaps(frame)

    assert len(warnings) == 1
    assert warnings[0].item_id == "P1001"
    assert warnings[0].is_blocking is True
    assert warnings[0].conflict_type == "blocking_conflict"
    assert {warnings[0].source_row_id_a, warnings[0].source_row_id_b} == {
        "CTKM:P1001:Legacy offer",
        "CLEARANCE:P9001:Direct new-code offer",
    }


def test_ctkm_clearance_confirmation_compares_safe_old_and_new_codes_as_one_product():
    ctkm = pd.DataFrame([
        _promotion("P1001", new_item_id="P9001", campaign="Monthly"),
    ])
    clearance = pd.DataFrame([
        _promotion("P9001", source="CLEARANCE", campaign="Clearance"),
    ])

    confirmation = main._build_ctkm_clearance_confirmation(ctkm, clearance)

    assert set(confirmation["trang_thai_doi_chieu"]) == {"Có cả CTKM và Clearance"}
    assert set(confirmation["transition_match_key"]) == {"P1001"}
    assert set(confirmation["quan_he_thoi_gian"]) == {"Trùng thời gian - cần xác nhận"}
    assert set(confirmation["item_id"]) == {"P1001", "P9001"}
    assert confirmation.loc[
        confirmation["nguon_chuong_trinh"].eq("CTKM"), "new_item_id"
    ].iloc[0] == "P9001"


def test_ambiguous_many_to_one_transition_is_not_auto_compared_across_sources():
    ctkm = pd.DataFrame([
        _promotion("P1001", new_item_id="P9001", campaign="A"),
        _promotion("P1002", new_item_id="P9001", campaign="B"),
    ])
    clearance = pd.DataFrame([
        _promotion("P9001", source="CLEARANCE", campaign="C"),
    ])

    identity = build_transition_identity(
        pd.concat([ctkm, clearance], ignore_index=True),
        key_func=main.NM.make_item_key,
        is_sku=main.RC.is_sku,
    )
    assert "P9001" in identity.ambiguous_keys
    assert identity.comparison_map == {}

    confirmation = main._build_ctkm_clearance_confirmation(ctkm, clearance)
    statuses = dict(zip(confirmation["item_id"], confirmation["trang_thai_doi_chieu"]))
    assert statuses["P1001"] == "Chỉ CTKM"
    assert statuses["P1002"] == "Chỉ CTKM"
    assert statuses["P9001"] == "Chỉ Clearance"

    warnings = main.RC.detect_campaign_time_overlaps(
        pd.concat([ctkm, clearance], ignore_index=True)
    )
    assert warnings == []


def test_transition_identity_aligns_location_cross_source_matched_and_pog_coverage_metrics():
    actions = pd.DataFrame([
        {
            **_promotion("P1001", new_item_id="P9001", campaign="Monthly"),
            "location_completeness": "Không tìm thấy SKU trong POG",
        },
        {
            **_promotion("P9001", source="CLEARANCE", campaign="Clearance"),
            "location_completeness": "Không tìm thấy SKU trong POG",
        },
    ])
    matched = pd.DataFrame([
        {"item_id": "P9001", "item_key": "P9001"},
        {"item_id": "P1001", "item_key": "P1001"},
    ])
    pog_only = pd.DataFrame([
        {"item_id": "P9001", "item_key": "P9001"},
    ])
    summary = {
        "So dong CTKM thieu vi tri ke": 2,
        "So item CTKM thieu vi tri ke": 2,
        "So item trung CTKM va Clearance": 0,
        "So item duy nhat khop": 2,
        "So dong POG khong co CTKM phu hop": 1,
        "So item POG khong co CTKM phu hop": 1,
    }

    main._align_location_summary_with_program_sources(summary, actions)
    main._align_cross_source_summary(summary, actions)
    main._align_matched_unique_summary(summary, matched, actions)
    main._align_pog_promotion_coverage_summary(summary, matched, pog_only, actions)

    assert summary["So dong KM thieu vi tri POG"] == 2
    assert summary["So item KM thieu vi tri POG"] == 1
    assert summary["So item CTKM Monthly thieu vi tri POG"] == 1
    assert summary["So item Clearance thieu vi tri POG"] == 1
    assert summary["So item trung CTKM va Clearance"] == 1
    assert summary["So item duy nhat khop"] == 1

    assert summary["So dong POG khong co KM phu hop"] == 0
    assert summary["So item POG khong co KM phu hop"] == 0
    assert summary["So item POG co KM phu hop"] == 1
    assert summary["So item POG tong hop de doi chieu KM"] == 1
    assert summary["So dong POG khong co CTKM phu hop"] == 0
    assert summary["So item POG khong co CTKM phu hop"] == 0


def test_chain_transition_is_rejected_consistently_by_helper_joiner_and_actions():
    frame = pd.DataFrame([
        _promotion("P1001", new_item_id="P9001", campaign="A"),
        _promotion("P9001", new_item_id="P9999", campaign="B"),
    ])
    identity = build_transition_identity(
        frame, key_func=main.NM.make_item_key, is_sku=main.RC.is_sku,
    )

    assert "P9001" in identity.ambiguous_keys
    assert identity.comparison_map == {}
    assert identity.pog_alias_map == {}

    pog = pd.DataFrame([_pog("P9999")])
    joined = main.JN.join_ctkm_pog(frame, pog)
    assert joined.df_matched.empty
    assert len(joined.df_ctkm_only) == 2
    assert len(joined.df_pog_only) == 1

    actions = main.RC.build_fefo_action_frame(
        frame,
        "2026-09",
        pog,
        business_date=pd.Timestamp("2026-09-15"),
        overlap_warnings=[],
    )
    assert set(actions["item_code_transition_status"]) == {"Mơ hồ - không tự remap"}
    assert set(actions["location_completeness"]) == {"Không tìm thấy SKU trong POG"}
    assert set(actions["matched_pog_item_id"].dropna()) == set()
