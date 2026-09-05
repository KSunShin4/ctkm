# -*- coding: utf-8 -*-
"""Serve the tag-audit SPA entrypoint on its explicit browser route.

Starlette ``StaticFiles(html=True)`` serves ``index.html`` for directory indexes,
but it is not a generic SPA fallback. Therefore ``/scan-tem`` must be registered
as a normal FastAPI route before the root static mount.
"""
from __future__ import annotations


def install_tag_audit_frontend_contract(core_module) -> None:
    if getattr(core_module.app.state, "tag_audit_frontend_contract_v1", False):
        return

    async def scan_tem_page():
        index_path = core_module._FRONTEND_DIST / "index.html"
        if not index_path.is_file():
            raise core_module.HTTPException(
                status_code=404,
                detail="Frontend kiểm tem chưa được build",
            )
        return core_module.FileResponse(index_path)

    core_module.app.add_api_route(
        "/scan-tem",
        scan_tem_page,
        methods=["GET"],
        include_in_schema=False,
    )

    routes = core_module.app.router.routes
    scan_route = next(
        route for route in reversed(routes)
        if getattr(route, "path", None) == "/scan-tem"
        and "GET" in (getattr(route, "methods", set()) or set())
    )
    routes.remove(scan_route)
    mount_index = next(
        (
            index for index, route in enumerate(routes)
            if getattr(route, "path", None) == "/"
            and route.__class__.__name__ == "Mount"
        ),
        len(routes),
    )
    routes.insert(mount_index, scan_route)

    core_module.scan_tem_page = scan_tem_page
    core_module.app.state.tag_audit_frontend_contract_v1 = True
