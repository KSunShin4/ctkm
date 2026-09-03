import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

import main
from modules.mapping_validation import validate_manual_mapping


def _load_main_again(alias: str):
    path = Path(main.__file__)
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def test_main_facade_reuses_immutable_core_baselines_across_module_names():
    core = sys.modules["_ctkm_main_core"]
    baseline = core._ctkm_main_facade_baseline

    assert main._original_process is baseline["process"]
    assert main._original_get_or_map is baseline["get_or_map"]
    assert main._original_build_confirmation is baseline["build_confirmation"]
    assert main._task_aligned_export is baseline["export_final_report"]

    first_process_wrapper = core._process
    first_export_wrapper = core.EX.export_final_report

    repeated = _load_main_again("_ctkm_main_repeat_contract")

    # The new facade replaces wrappers but always calls the same immutable
    # baseline. Runtime hooks may then add one hardened layer on top; they must
    # never capture the wrapper installed by the previous facade generation.
    assert repeated._original_process is baseline["process"]
    assert repeated._original_process is not first_process_wrapper
    assert repeated._original_get_or_map is baseline["get_or_map"]
    assert repeated._original_build_confirmation is baseline["build_confirmation"]
    assert repeated._task_aligned_export is baseline["export_final_report"]
    assert repeated._task_aligned_export is not first_export_wrapper

    assert core._process is repeated._process
    hardened_export = core.EX.export_final_report
    assert getattr(hardened_export, "_ctkm_export_memory_contract_v1", False)
    assert hardened_export.__wrapped__ is repeated._export_with_location_summary
    assert hardened_export is not first_export_wrapper


def test_third_facade_load_still_has_one_wrapper_layer():
    core = sys.modules["_ctkm_main_core"]
    baseline = core._ctkm_main_facade_baseline
    previous_export = core.EX.export_final_report

    repeated = _load_main_again("_ctkm_main_repeat_contract_2")

    assert repeated._original_process is baseline["process"]
    assert repeated._task_aligned_export is baseline["export_final_report"]
    hardened_export = core.EX.export_final_report
    assert getattr(hardened_export, "_ctkm_export_memory_contract_v1", False)
    assert hardened_export.__wrapped__ is repeated._export_with_location_summary
    assert hardened_export is not previous_export
    assert not getattr(
        hardened_export.__wrapped__, "_ctkm_export_memory_contract_v1", False
    )


def test_public_main_uses_shared_required_field_mapping_contract():
    assert main._validate_manual_mapping is validate_manual_mapping
    frame = pd.DataFrame(columns=[
        "Item", "Campaign", "From", "To", "Detail 1", "Detail 2",
    ])

    with pytest.raises(ValueError, match="thiếu trường bắt buộc"):
        main._validate_manual_mapping(
            {"Item": "item_id"}, frame, main.SCHEMA["fact_fields"]
        )

    accepted = main._validate_manual_mapping(
        {
            "Item": "item_id",
            "Campaign": "campaign_name",
            "From": "promo_from",
            "To": "promo_to",
            "Detail 1": "campaign_detail",
            "Detail 2": "campaign_detail",
        },
        frame,
        main.SCHEMA["fact_fields"],
    )
    assert accepted["Detail 1"] == "campaign_detail"
    assert accepted["Detail 2"] == "campaign_detail"
