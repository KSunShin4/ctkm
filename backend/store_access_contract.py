# -*- coding: utf-8 -*-
"""Store-facing access policy for CTKM/Tem workflows.

The application historically reused admin dependencies for operational routes.
This contract removes only the admin dependency from routes that store users need
to run CTKM/Tem workflows. Administrative surfaces such as presets, queue
inspection, job history and system configuration remain admin-only.
"""
from __future__ import annotations


STORE_ROUTES = (
    ("POST", "/api/inspect-ctkm"),
    ("POST", "/api/inspect-pog"),
    ("POST", "/api/preview-mapping"),
    ("POST", "/api/jobs/ctkm"),
    ("POST", "/api/run"),
    ("GET", "/api/job/{job_id}/status"),
    ("GET", "/api/preview/{job_id}"),
    ("GET", "/api/download/{job_id}"),
    ("POST", "/api/inspect-tem-r"),
    ("POST", "/api/jobs/tem-r"),
    ("POST", "/api/tem-r"),
    ("GET", "/api/tag-audit/context"),
    ("POST", "/api/tag-audit/context"),
    ("GET", "/api/tag-audit/checklist"),
    ("POST", "/api/tag-audit/check"),
)


def _route_for(core_module, method: str, path: str):
    matches = [
        route for route in core_module.app.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", None) or set())
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Store access contract cần đúng 1 route {method} {path}, hiện có {len(matches)}"
        )
    return matches[0]


def install_store_access_contract(core_module) -> None:
    if getattr(core_module.app.state, "store_access_contract_v1", False):
        return

    for method, path in STORE_ROUTES:
        route = _route_for(core_module, method, path)
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        dependant.dependencies = [
            dependency
            for dependency in dependant.dependencies
            if getattr(dependency, "call", None) is not core_module.require_admin
        ]

    core_module.app.state.store_access_contract_v1 = True
