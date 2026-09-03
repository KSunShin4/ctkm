import importlib.util
from pathlib import Path
import sys

import main


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
    # baseline. It must never capture the wrapper installed by the first import.
    assert repeated._original_process is baseline["process"]
    assert repeated._original_process is not first_process_wrapper
    assert repeated._original_get_or_map is baseline["get_or_map"]
    assert repeated._original_build_confirmation is baseline["build_confirmation"]
    assert repeated._task_aligned_export is baseline["export_final_report"]
    assert repeated._task_aligned_export is not first_export_wrapper

    assert core._process is repeated._process
    assert core.EX.export_final_report is repeated._export_with_location_summary


def test_third_facade_load_still_has_one_wrapper_layer():
    core = sys.modules["_ctkm_main_core"]
    baseline = core._ctkm_main_facade_baseline

    repeated = _load_main_again("_ctkm_main_repeat_contract_2")

    assert repeated._original_process is baseline["process"]
    assert repeated._task_aligned_export is baseline["export_final_report"]
