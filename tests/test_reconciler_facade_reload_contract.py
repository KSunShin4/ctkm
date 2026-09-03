import importlib.util
from pathlib import Path
import sys

import pandas as pd

import main


def _load_reconciler_again(alias: str):
    path = Path(main.RC.__file__)
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def _promotion():
    return pd.DataFrame([
        {
            "item_id": "P1001",
            "item_name": "Sản phẩm A",
            "campaign_name": "Promo A",
            "campaign_detail": "Giảm 10%",
            "promo_from": "2026-09-01",
            "promo_to": "2026-09-30",
            "key_channel": "Offline",
            "channel": "OFFLINE",
            "program_source": "CTKM",
            "source_row_id": "CTKM:Sheet1:2",
        }
    ])


def test_reconciler_facade_uses_pristine_build_fefo_baseline_across_aliases():
    core = sys.modules["_ctkm_reconciler_core"]
    baseline = core._ctkm_reconciler_facade_baseline
    raw = baseline["build_fefo_action_frame"]

    first = core.build_fefo_action_frame
    assert first.__wrapped__ is raw

    second_module = _load_reconciler_again("_ctkm_reconciler_repeat_1")
    second = core.build_fefo_action_frame
    assert second is second_module.build_fefo_action_frame
    assert second is not first
    assert second.__wrapped__ is raw
    assert second.__wrapped__ is not first

    third_module = _load_reconciler_again("_ctkm_reconciler_repeat_2")
    third = core.build_fefo_action_frame
    assert third is third_module.build_fefo_action_frame
    assert third is not second
    assert third.__wrapped__ is raw
    assert baseline["build_fefo_action_frame"] is raw


def test_reconciler_reload_does_not_duplicate_operational_columns():
    _load_reconciler_again("_ctkm_reconciler_repeat_result")
    result = main.RC.build_fefo_action_frame(
        _promotion(),
        "2026-09",
        business_date="2026-09-10",
    )

    for column in (
        "scope_identity_key",
        "operational_promotion_key",
        "operational_task_key",
        "promotion_count_at_position",
        "has_multiple_promotions_at_position",
    ):
        assert list(result.columns).count(column) == 1
