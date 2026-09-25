# -*- coding: utf-8 -*-
"""Serve the shared portal module entrypoints before the root static mount."""
from __future__ import annotations


PORTAL_PATHS = ("/guide", "/assistant")


def _insert_before_frontend(core_module, path: str, endpoint) -> None:
    core_module.app.add_api_route(path, endpoint, methods=["GET"], include_in_schema=False)
    routes = core_module.app.router.routes
    route = next(
        item for item in reversed(routes)
        if getattr(item, "path", None) == path
        and "GET" in (getattr(item, "methods", set()) or set())
    )
    routes.remove(route)
    mount_index = next(
        (
            index for index, item in enumerate(routes)
            if item.__class__.__name__ == "Mount"
            and (getattr(item, "name", None) == "frontend" or getattr(item, "path", None) in {"", "/"})
        ),
        len(routes),
    )
    routes.insert(mount_index, route)


def install_portal_frontend_contract(core_module) -> None:
    if getattr(core_module.app.state, "portal_frontend_contract_v1", False):
        return

    async def portal_page():
        index_path = core_module._FRONTEND_DIST / "index.html"
        if not index_path.is_file():
            raise core_module.HTTPException(status_code=404, detail="Frontend portal chưa được build")
        return core_module.FileResponse(index_path)

    for path in PORTAL_PATHS:
        _insert_before_frontend(core_module, path, portal_page)

    core_module.portal_page = portal_page
    core_module.app.state.portal_frontend_contract_v1 = True
