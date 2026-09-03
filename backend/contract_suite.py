# -*- coding: utf-8 -*-
"""Install and verify the FastAPI compatibility contracts as one ordered suite."""
from __future__ import annotations

from modules.facade_contracts import (
    register_post_facade_hook,
    registered_post_facade_hooks,
)
from modules.mapping_validation import validate_manual_mapping

from backend import input_contract
from backend.runtime_contract import install_runtime_contract
from backend.input_contract import install_input_contract
from backend.mapping_result_contract import install_mapping_result_contract
from backend.gemini_availability_contract import install_gemini_availability_contract
from backend.tem_r_resource_contract import install_tem_r_resource_contract
from backend.auxiliary_workflows_contract import install_auxiliary_workflows_contract
from backend.expiration_api_contract import install_expiration_api_contract
from backend.final_output_contract import install_final_output_contract
from backend.preview_contract import install_preview_contract


CONTRACT_ORDER = (
    "runtime",
    "input",
    "mapping-result",
    "gemini-availability",
    "tem-r-resource",
    "auxiliary-workflows",
    "expiration-api",
    "final-output",
    "preview",
)

_STATE_FLAGS = {
    "runtime": "runtime_contract_v1",
    "input": "input_contract_v1",
    "mapping-result": "mapping_result_contract_v1",
    "gemini-availability": "gemini_availability_contract_v1",
    "tem-r-resource": "tem_r_resource_contract_v1",
    "auxiliary-workflows": "auxiliary_workflows_contract_v1",
    "expiration-api": "expiration_api_contract_v1",
    "final-output": "final_output_contract_v1",
    "preview": "visible_preview_contract",
}

_ROUTE_BINDINGS = (
    ("GET", "/api/health", "health"),
    ("GET", "/api/download/{job_id}", "download_result"),
    ("GET", "/api/jobs", "list_jobs"),
    ("POST", "/api/jobs/ctkm", "enqueue_ctkm"),
    ("POST", "/api/jobs/tem-r", "enqueue_tem_r"),
    ("POST", "/api/tem-r", "run_tem_r"),
    ("POST", "/api/inspect-tem-r", "inspect_tem_r_file"),
    ("POST", "/api/check-expiration", "check_expiration"),
    ("GET", "/api/preview/{job_id}", "preview_result"),
)


def _route_for(core_module, method: str, path: str):
    matches = [
        route for route in core_module.app.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", None) or set())
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"FastAPI contract cần đúng 1 route {method} {path}, hiện có {len(matches)}"
        )
    return matches[0]


def _install_health_contract(core_module) -> None:
    if getattr(core_module.app.state, "contract_health_v1", False):
        return

    original_health = core_module.health

    def health():
        payload = original_health()
        result = dict(payload) if isinstance(payload, dict) else {"status": "ok"}
        main_core = getattr(core_module._main_mod, "_core", None)
        result.update({
            "contract_suite": "v1",
            "contracts_ok": True,
            "contract_order": list(CONTRACT_ORDER),
            "main_facade_hooks": (
                list(registered_post_facade_hooks(main_core))
                if main_core is not None else []
            ),
        })
        return result

    route = _route_for(core_module, "GET", "/api/health")
    route.endpoint = health
    dependant = getattr(route, "dependant", None)
    if dependant is not None:
        dependant.call = health
    core_module.health = health
    core_module.app.state.contract_health_v1 = True


def verify_contract_suite(core_module) -> None:
    missing_flags = [
        name for name in CONTRACT_ORDER
        if not getattr(core_module.app.state, _STATE_FLAGS[name], False)
    ]
    if missing_flags:
        raise RuntimeError(
            "Backend contract suite chưa cài đủ: " + ", ".join(missing_flags)
        )
    if not getattr(core_module.app.state, "contract_health_v1", False):
        raise RuntimeError("Backend health chưa phản ánh trạng thái contract suite")

    if input_contract.validate_manual_mapping is not validate_manual_mapping:
        raise RuntimeError("Input contract không dùng shared mapping validator")

    for method, path, attribute in _ROUTE_BINDINGS:
        expected = getattr(core_module, attribute, None)
        if not callable(expected):
            raise RuntimeError(f"Backend contract thiếu callable core.{attribute}")
        route = _route_for(core_module, method, path)
        if route.endpoint is not expected:
            raise RuntimeError(
                f"Route {method} {path} bị ghi đè sau contract '{attribute}'"
            )
        dependant = getattr(route, "dependant", None)
        if dependant is not None and dependant.call is not expected:
            raise RuntimeError(
                f"Dependency call của {method} {path} không trỏ tới core.{attribute}"
            )

    main_core = getattr(core_module._main_mod, "_core", None)
    if main_core is None:
        raise RuntimeError("Backend contract suite không tìm thấy _ctkm_main_core")
    baseline = getattr(main_core, "_ctkm_main_facade_baseline", None)
    if not isinstance(baseline, dict):
        raise RuntimeError("Public main facade chưa có immutable baseline")
    baseline_mapper = baseline.get("get_or_map")
    if not callable(baseline_mapper):
        raise RuntimeError("Immutable main baseline thiếu get_or_map")
    if getattr(baseline_mapper, "_ctkm_mapping_result_contract_v1", False):
        raise RuntimeError("Immutable main baseline đã bị runtime hardening sửa đổi")

    hooks = registered_post_facade_hooks(main_core)
    if "mapping-result-contract-v1" not in hooks:
        raise RuntimeError("Main facade chưa đăng ký mapping-result post-facade hook")

    mapper = getattr(main_core, "_get_or_map", None)
    if not getattr(mapper, "_ctkm_mapping_result_contract_v1", False):
        raise RuntimeError("Mapping-result hardening không còn bọc _ctkm_main_core._get_or_map")

    core_module.app.state.contract_installation_order = CONTRACT_ORDER
    core_module.app.state.registered_main_facade_hooks = hooks


def install_contract_suite(core_module) -> None:
    """Install contracts in their only supported order, then verify the surface."""
    # The input module still contains its historical validator for compatibility.
    # Make the production suite explicitly bind the shared validator before any
    # route captures it; do not depend on import side effects in main_api.py.
    input_contract.validate_manual_mapping = validate_manual_mapping

    install_runtime_contract(core_module)
    install_input_contract(core_module)
    install_mapping_result_contract(core_module, validate_manual_mapping)
    install_gemini_availability_contract(core_module)
    install_tem_r_resource_contract(core_module)
    install_auxiliary_workflows_contract(core_module)
    install_expiration_api_contract(core_module)
    install_final_output_contract(core_module)
    install_preview_contract(core_module)
    _install_health_contract(core_module)

    main_core = getattr(core_module._main_mod, "_core", None)
    if main_core is None:
        raise RuntimeError("Backend contract suite không tìm thấy _ctkm_main_core")

    def verify_after_facade_rebuild(_main_core, _facade_module=None) -> None:
        verify_contract_suite(core_module)

    register_post_facade_hook(
        main_core,
        "backend-contract-suite-verify-v1",
        verify_after_facade_rebuild,
    )

    verify_contract_suite(core_module)
    core_module.app.state.contract_suite_v1 = True
