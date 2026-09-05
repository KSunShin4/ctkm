import pandas as pd

import main
from modules.channel_scope import scope_identity_key, scope_overlap_relation
from modules.ctkm_performance import unique_work_tracking_rows


BUSINESS_DATE = pd.Timestamp("2026-09-15")


def _promo(*, key_channel, channel, campaign="Campaign A", source="CTKM", detail="Discount 10%"):
    return {
        "item_id": "P1001",
        "item_key": "P1001",
        "item_name": "Product P1001",
        "promo_uom": "Hop",
        "program_source": source,
        "key_channel": key_channel,
        "channel": channel,
        "campaign_name": campaign,
        "campaign_detail": detail,
        "promo_from": pd.Timestamp("2026-09-01"),
        "promo_to": pd.Timestamp("2026-09-30"),
        "normal_price": 100000,
        "promo_price": 90000,
        "product_type": "H&B",
        "source_sheet": "Monthly" if source == "CTKM" else "Clearance",
        "source_row_id": f"{source}:{key_channel}:{channel}:{campaign}",
    }


def _pog():
    return pd.DataFrame([{
        "item_id": "P1001",
        "item_key": "P1001",
        "store_id": "S1",
        "pog_code": "A",
        "location_id": "1",
        "facing": 1,
        "pog_snapshot_month": "2026-09",
        "source_row_id": "POG:Export:10",
    }])


def test_scope_relation_contract_for_pharmacity_key_channel():
    assert scope_overlap_relation("Offline", "OFFLINE", "OFFLINE", "Offline ") == "same"
    assert scope_overlap_relation("All channel", "All Channel", "Offline", "Offline") == "intersects"
    assert scope_overlap_relation("Offline", "Offline", "Online", "MKP") == "disjoint"
    assert scope_overlap_relation("Others", "COMBO A", "Others", "COMBO A ") == "same"
    assert scope_overlap_relation("Others", "COMBO A", "Others", "COMBO B") == "unknown"
    assert scope_identity_key("Offline", "OFFLINE ") == scope_identity_key("OFFLINE", "offline")


def test_all_channel_intersection_remains_warning_not_automatic_block():
    frame = pd.DataFrame([
        _promo(key_channel="All channel", channel="All Channel", campaign="Offer A"),
        _promo(key_channel="Offline", channel="Offline", campaign="Offer B", detail="PWP"),
    ])
    warnings = main.RC.detect_campaign_time_overlaps(frame)
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning.is_blocking is False
    assert warning.conflict_type == "potential_cross_channel_overlap"
    assert warning.scope_relation == "intersects"


def test_offline_online_overlap_is_visible_but_not_blocking_within_same_source():
    frame = pd.DataFrame([
        _promo(key_channel="Offline", channel="Offline", campaign="Store offer"),
        _promo(key_channel="Online", channel="MKP", campaign="Online offer"),
    ])
    warnings = main.RC.detect_campaign_time_overlaps(frame)
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning.is_blocking is False
    assert warning.scope_relation == "disjoint"


def test_meaningful_others_subchannels_are_not_operationally_deduped():
    frame = pd.DataFrame([
        _promo(key_channel="Others", channel="COMBO A"),
        _promo(key_channel="Others", channel="COMBO B"),
    ])
    actions = main.RC.build_fefo_action_frame(
        frame, "2026-09", _pog(), business_date=BUSINESS_DATE,
    )
    assert actions["scope_identity_key"].nunique() == 2
    assert actions["operational_task_key"].nunique() == 2
    assert len(unique_work_tracking_rows(actions)) == 2
