import importlib.util
from pathlib import Path
import sys

import pandas as pd


def _load_reconciler():
    path = Path(__file__).resolve().parents[1] / "modules" / "8_reconciler.py"
    spec = importlib.util.spec_from_file_location("reconciler", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_reconciler = _load_reconciler()
build_fefo_action_frame = _reconciler.build_fefo_action_frame
detect_campaign_time_overlaps = _reconciler.detect_campaign_time_overlaps


def test_build_fefo_action_frame_uses_injected_business_date():
    today = pd.Timestamp("2026-08-15")
    df = pd.DataFrame(
        [
            {
                "item_id": "P1001",
                "campaign_name": "KM 1",
                "campaign_detail": "Giảm 10%",
                "promo_from": today - pd.Timedelta(days=2),
                "promo_to": today + pd.Timedelta(days=2),
            },
            {
                "item_id": "P1002",
                "campaign_name": "KM 2",
                "campaign_detail": "Giảm 20%",
                "promo_from": today - pd.Timedelta(days=10),
                "promo_to": today - pd.Timedelta(days=2),
            },
        ]
    )

    result = build_fefo_action_frame(df, "2026-08", business_date=today)

    assert list(result["item_id"]) == ["P1001", "P1002"]
    assert list(result["action"]) == ["gắn tem", "tháo tem"]
    assert result.loc[0, "reason"] == "trong_thoi_gian_ap_dung"
    assert result.loc[1, "reason"] == "den_ngay_thao"


def test_build_fefo_action_frame_keeps_same_campaign_for_different_channels():
    today = pd.Timestamp("2026-08-15")
    df = pd.DataFrame([
        {
            "item_id": "P1001", "campaign_name": "FULL MONTH",
            "campaign_detail": "Giảm 10%", "channel": "OFFLINE",
            "promo_from": today - pd.Timedelta(days=1),
            "promo_to": today + pd.Timedelta(days=1),
        },
        {
            "item_id": "P1001", "campaign_name": "FULL MONTH",
            "campaign_detail": "Giảm 10%", "channel": "WEBAPP",
            "promo_from": today - pd.Timedelta(days=1),
            "promo_to": today + pd.Timedelta(days=1),
        },
    ])

    result = build_fefo_action_frame(df, "2026-08", business_date=today)

    assert result["channel"].tolist() == ["OFFLINE", "WEBAPP"]


def test_build_fefo_action_frame_keeps_different_campaign_details():
    today = pd.Timestamp("2026-08-15")
    df = pd.DataFrame([
        {
            "item_id": "P1001", "campaign_name": "COMBO", "channel": "OFFLINE",
            "campaign_detail": "Combo Mẹ tròn - Con vuông",
            "promo_from": today - pd.Timedelta(days=1),
            "promo_to": today + pd.Timedelta(days=1),
        },
        {
            "item_id": "P1001", "campaign_name": "COMBO", "channel": "OFFLINE",
            "campaign_detail": "Combo Đón Thiên Thần Nhỏ",
            "promo_from": today - pd.Timedelta(days=1),
            "promo_to": today + pd.Timedelta(days=1),
        },
    ])

    result = build_fefo_action_frame(df, "2026-08", business_date=today)

    assert result["campaign_detail"].tolist() == [
        "Combo Mẹ tròn - Con vuông", "Combo Đón Thiên Thần Nhỏ",
    ]


def test_build_fefo_action_frame_keeps_promo_uom_from_company_ctkm():
    today = pd.Timestamp("2026-08-15")
    df = pd.DataFrame([{
        "item_id": "P1001", "item_name": "Thuốc A", "promo_uom": "Hộp",
        "campaign_name": "FULL MONTH", "campaign_detail": "Giảm 10%",
        "promo_from": today - pd.Timedelta(days=1),
        "promo_to": today + pd.Timedelta(days=1),
    }])

    result = build_fefo_action_frame(df, "2026-08", business_date=today)

    assert result.loc[0, "promo_uom"] == "Hộp"


def test_overlap_warning_does_not_suppress_different_channels():
    period = {"promo_from": pd.Timestamp("2026-08-01"), "promo_to": pd.Timestamp("2026-08-31")}
    df = pd.DataFrame([
        {"item_id": "P1001", "campaign_name": "Store", "channel": "OFFLINE", **period},
        {"item_id": "P1001", "campaign_name": "Web", "channel": "WEBAPP", **period},
    ])

    warnings = detect_campaign_time_overlaps(df)

    assert len(warnings) == 1
    assert warnings[0].channel_a == "OFFLINE"
    assert warnings[0].channel_b == "WEBAPP"


def test_overlap_warning_keeps_channels_that_can_apply_together():
    period = {"promo_from": pd.Timestamp("2026-08-01"), "promo_to": pd.Timestamp("2026-08-31")}
    df = pd.DataFrame([
        {"item_id": "P1001", "campaign_name": "Full", "channel": "ALL CHANNEL", **period},
        {"item_id": "P1001", "campaign_name": "Store", "channel": "OFFLINE", **period},
    ])

    warnings = detect_campaign_time_overlaps(df)

    assert len(warnings) == 1
    assert warnings[0].channel_a == "ALL CHANNEL"
    assert warnings[0].channel_b == "OFFLINE"
