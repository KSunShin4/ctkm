import importlib.util
from pathlib import Path
import sys

import pandas as pd
import pytest

from backend import main_api
from backend.contract_suite import CONTRACT_ORDER, install_contract_suite, verify_contract_suite
from modules.facade_contracts import registered_post_facade_hooks


def _load_main_again(alias: str):
    source = sys.modules.get("ctkm_main") or sys.modules.get("main")
    assert source is not None
    path = Path(source.__file__)
    spec = importlib.util.spec_from_file_location(alias, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def test_backend_suite_has_one_verified_installation_order_and_is_idempotent():
    verify_contract_suite(main_api)
    assert main_api.app.state.contract_suite_v1 is True
    assert main_api.app.state.contract_installation_order == CONTRACT_ORDER

    queue_before = main_api._heavy_queue
    mapper_before = main_api._main_mod._core._get_or_map
    routes_before = {
        (method, route.path): route.endpoint
        for route in main_api.app.routes
        for method in (getattr(route, "methods", None) or set())
    }

    install_contract_suite(main_api)

    assert main_api._heavy_queue is queue_before
    assert main_api._main_mod._core._get_or_map is mapper_before
    routes_after = {
        (method, route.path): route.endpoint
        for route in main_api.app.routes
        for method in (getattr(route, "methods", None) or set())
    }
    assert routes_after == routes_before


def test_suite_verifier_detects_route_clobbering():
    target = next(
        route for route in main_api.app.routes
        if route.path == "/api/preview/{job_id}" and "GET" in route.methods
    )
    original_endpoint = target.endpoint
    original_call = target.dependant.call

    def accidental_override(*_args, **_kwargs):
        return None

    try:
        target.endpoint = accidental_override
        target.dependant.call = accidental_override
        with pytest.raises(RuntimeError, match="bị ghi đè"):
            verify_contract_suite(main_api)
    finally:
        target.endpoint = original_endpoint
        target.dependant.call = original_call

    verify_contract_suite(main_api)


def test_main_reload_reapplies_mapping_hardening_without_mutating_baseline():
    core = main_api._main_mod._core
    baseline = core._ctkm_main_facade_baseline
    baseline_mapper = baseline["get_or_map"]

    assert not getattr(baseline_mapper, "_ctkm_mapping_result_contract_v1", False)
    assert getattr(core._get_or_map, "_ctkm_mapping_result_contract_v1", False)
    hooks = registered_post_facade_hooks(core)
    assert hooks == (
        "mapping-result-contract-v1",
        "backend-contract-suite-verify-v1",
    )

    repeated = _load_main_again("_ctkm_main_facade_suite_repeat")

    assert baseline["get_or_map"] is baseline_mapper
    assert repeated._original_get_or_map is baseline_mapper
    assert getattr(core._get_or_map, "_ctkm_mapping_result_contract_v1", False)
    assert repeated._get_or_map is core._get_or_map
    assert core._ctkm_main_last_post_facade_hooks == hooks
    assert main_api.app.state.registered_main_facade_hooks == hooks

    control_only = pd.DataFrame([
        {
            "Item code 2": None,
            "Campaign": "Grand Total",
            "From": None,
            "To": None,
        }
    ])
    with pytest.raises(ValueError, match="subtotal/Total/control"):
        repeated._get_or_map(
            "Detail",
            control_only,
            repeated.SCHEMA["fact_fields"],
            [],
        )


def test_third_main_reload_replaces_not_stacks_mapping_contract():
    core = main_api._main_mod._core
    first_hardened = core._get_or_map
    first_raw = first_hardened.__wrapped__

    repeated = _load_main_again("_ctkm_main_facade_suite_repeat_2")
    second_hardened = core._get_or_map

    assert second_hardened is repeated._get_or_map
    assert second_hardened is not first_hardened
    assert getattr(second_hardened, "_ctkm_mapping_result_contract_v1", False)
    # A facade rebuild starts from its immutable raw baseline-derived wrapper;
    # the new hardening layer must never wrap the previous hardening layer.
    assert second_hardened.__wrapped__ is not first_hardened
    assert not getattr(second_hardened.__wrapped__, "_ctkm_mapping_result_contract_v1", False)
    assert first_raw is not first_hardened
