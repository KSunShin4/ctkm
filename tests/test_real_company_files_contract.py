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
