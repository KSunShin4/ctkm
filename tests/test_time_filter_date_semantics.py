import pandas as pd

import main


def _frame(promo_from, promo_to):
    return pd.DataFrame([
        {
            "item_id": "P1001",
            "campaign_name": "Boundary",
            "promo_from": promo_from,
            "promo_to": promo_to,
        }
    ])


def test_month_filter_treats_end_of_day_microseconds_as_same_business_date():
    frame = _frame(
        pd.Timestamp("2026-08-31 23:59:59.500000"),
        pd.Timestamp("2026-08-31 23:59:59.500000"),
    )

    relevant, operational = main.TF.filter_ctkm_by_month(frame, "2026-08")

    assert len(relevant) == 1
    assert len(operational) == 1
    assert relevant.loc[0, "_month_scope_reason"] == "ctkm_ap_dung_trong_thang"
    # Source timestamps remain byte-for-byte/value-for-value untouched.
    assert operational.loc[0, "promo_from"] == frame.loc[0, "promo_from"]
    assert operational.loc[0, "promo_to"] == frame.loc[0, "promo_to"]


def test_previous_month_end_time_still_creates_first_day_removal_scope():
    frame = _frame(
        pd.Timestamp("2026-07-01 12:34:56.123456"),
        pd.Timestamp("2026-07-31 23:59:59.999999"),
    )

    relevant, operational = main.TF.filter_ctkm_by_month(frame, "2026-08")

    assert len(relevant) == 1
    assert len(operational) == 1
    assert relevant.loc[0, "_month_scope_reason"] == "ngay_thao_trong_thang"


def test_time_filter_and_action_scope_agree_on_date_level_boundary():
    frame = _frame(
        pd.Timestamp("2026-08-31 23:59:59.500000"),
        pd.Timestamp("2026-08-31 23:59:59.500000"),
    )

    _, operational = main.TF.filter_ctkm_by_month(frame, "2026-08")
    actions = main.RC.build_fefo_action_frame(
        frame,
        "2026-08",
        business_date=pd.Timestamp("2026-08-31 08:00:00"),
    )

    assert len(operational) == 1
    assert len(actions) == 1
    assert bool(actions.loc[0, "in_report_scope"]) is True
    assert actions.loc[0, "scheduled_action"] == "gắn tem"
