import pandas as pd

import main


def test_real_clearance_campaign_detail_maps_without_ai():
    frame = pd.DataFrame(columns=[
        "Kênh áp dụng", "Item code", "Product Name", "Promo UoM", "Normal",
        "Promo", "Scheme detail for customer", "From", "To", "Campaign Detail",
        "Product type",
    ])

    mapping = main._infer_standard_fact_mapping(frame)

    assert mapping["Item code"] == "item_id"
    assert mapping["Campaign Detail"] == "campaign_name"
    assert mapping["Scheme detail for customer"] == "campaign_detail"
    assert mapping["From"] == "promo_from"
    assert mapping["To"] == "promo_to"
    assert mapping["Kênh áp dụng"] == "channel"


def test_monthly_campaign_wins_when_both_campaign_columns_exist():
    frame = pd.DataFrame(columns=[
        "Item code", "Scheme detail for customer", "From", "To",
        "Campaign", "Campaign Detail",
    ])

    mapping = main._infer_standard_fact_mapping(frame)

    assert mapping["Campaign"] == "campaign_name"
    assert "Campaign Detail" not in mapping


def test_real_pharmacity_pog_headers_map_deterministically_without_gemini(monkeypatch):
    frame = pd.DataFrame(columns=[
        "STOREID", "POGTYPE", "POGCODE", "ITEMID", "ITEMNAME", "FIXELNAME",
        "FIXELID", "LOCATIONID", "TOTALFACING", "TOTALUNIT", "PURCHUNIT",
        "INVENTUNIT", "PROMOTIONTYPE", "ISCHANGED", "ton",
    ])

    def gemini_must_not_run(*_args, **_kwargs):
        raise AssertionError("Standard Pharmacity POG must not call Gemini")

    monkeypatch.setattr(main.CM, "map_columns_with_gemini", gemini_must_not_run)
    logs = []
    mapping = main._get_or_map("Export", frame, main.SCHEMA["pog_fields"], logs)

    assert mapping == {
        "ITEMID": "item_id",
        "ITEMNAME": "item_name",
        "STOREID": "store_id",
        "POGCODE": "pog_code",
        "LOCATIONID": "location_id",
        "TOTALFACING": "facing",
    }
    assert logs[-1]["source"] == "standard-pog"
    assert "ton" not in mapping


def test_real_pog_multi_position_same_sku_is_preserved_not_deduplicated():
    ctkm = main.NM.clean_values(pd.DataFrame([{
        "item_id": "P30539",
        "campaign_name": "Full month",
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
    }]))
    pog = main.NM.clean_values(pd.DataFrame([
        {
            "item_id": "P30539", "store_id": "SGPMC1885",
            "pog_code": "BABY2.1885", "location_id": 4,
            "source_row_id": "POG:Export:5",
        },
        {
            "item_id": "P30539", "store_id": "SGPMC1885",
            "pog_code": "EC.PRO", "location_id": 1,
            "source_row_id": "POG:Export:356",
        },
    ]))

    joined = main.JN.join_ctkm_pog(ctkm, pog)

    assert len(joined.df_matched) == 2
    assert set(joined.df_matched["pog_code"]) == {"BABY2.1885", "EC.PRO"}
    assert set(joined.df_matched["source_row_id"]) == {
        "POG:Export:5", "POG:Export:356",
    }


def test_overlap_blocks_case_only_channel_variants_without_mutating_source():
    frame = pd.DataFrame([
        {
            "item_id": "P28807", "campaign_name": "TRADE UP",
            "promo_from": "2026-09-01", "promo_to": "2026-09-30",
            "key_channel": "Offline", "channel": "OFFLINE",
            "program_source": "CTKM", "source_sheet": "Monthly",
        },
        {
            "item_id": "P28807", "campaign_name": "PWP",
            "promo_from": "2026-09-05", "promo_to": "2026-09-20",
            "key_channel": "Offline", "channel": "Offline",
            "program_source": "CTKM", "source_sheet": "Monthly",
        },
    ])

    source_channels = frame["channel"].tolist()
    warnings = main.RC.detect_campaign_time_overlaps(frame)

    assert frame["channel"].tolist() == source_channels
    assert len(warnings) == 1
    assert warnings[0].channel_a == "OFFLINE"
    assert warnings[0].channel_b == "Offline"
    assert warnings[0].conflict_type == "blocking_conflict"
    assert warnings[0].is_blocking is True


def test_overlap_keeps_genuinely_different_channel_scopes_non_blocking():
    frame = pd.DataFrame([
        {
            "item_id": "P1", "campaign_name": "A",
            "promo_from": "2026-09-01", "promo_to": "2026-09-30",
            "key_channel": "Others", "channel": "Offline/WEB/APP",
            "program_source": "CTKM",
        },
        {
            "item_id": "P1", "campaign_name": "B",
            "promo_from": "2026-09-05", "promo_to": "2026-09-20",
            "key_channel": "All channel", "channel": "All Channel",
            "program_source": "CTKM",
        },
    ])

    warnings = main.RC.detect_campaign_time_overlaps(frame)

    assert len(warnings) == 1
    assert warnings[0].conflict_type == "potential_cross_channel_overlap"
    assert warnings[0].is_blocking is False
