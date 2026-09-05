import importlib.util
from pathlib import Path
import sys

import pandas as pd

import main


def test_import_main_installs_fidelity_contract_without_loader_side_effect():
    frame = pd.DataFrame({
        "KEY Channel": ["OFFLINE"],
        "Channel": ["COMBO ĐI SINH"],
    })
    mapping = main._ensure_channel_mapping({"KEY Channel": "channel"}, frame)

    assert mapping["KEY Channel"] == "key_channel"
    assert mapping["Channel"] == "channel"


def test_blank_clearance_campaign_is_not_inferred():
    ctkm = pd.DataFrame([{"item_id": "P1", "campaign_name": "CTKM"}])
    clearance = pd.DataFrame([{"item_id": "P2", "campaign_name": ""}])

    result = main._build_promo_action_source(ctkm, clearance)
    clearance_row = result[result["program_source"].eq("CLEARANCE")].iloc[0]

    assert clearance_row["campaign_name"] == ""


def test_reconciler_ids_distinguish_key_channel():
    rows = pd.DataFrame([
        {
            "item_id": "P1", "item_key": "P1", "campaign_name": "A",
            "campaign_detail": "x", "promo_from": "2026-09-01", "promo_to": "2026-09-10",
            "normal_price": 10, "promo_price": 9, "promo_uom": "Hộp",
            "key_channel": "OFFLINE", "channel": "COMBO", "program_source": "CTKM",
        },
        {
            "item_id": "P1", "item_key": "P1", "campaign_name": "A",
            "campaign_detail": "x", "promo_from": "2026-09-01", "promo_to": "2026-09-10",
            "normal_price": 10, "promo_price": 9, "promo_uom": "Hộp",
            "key_channel": "ONLINE", "channel": "COMBO", "program_source": "CTKM",
        },
    ])

    actions = main.RC.build_fefo_action_frame(rows, "2026-09", business_date="2026-09-05")

    assert actions["promotion_id"].nunique() == 2
