from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend import main_api


def _route(path: str, method: str):
    matches = [
        route for route in main_api.app.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", None) or set())
    ]
    assert len(matches) == 1
    return matches[0]


def _frontend_mount_index(routes):
    matches = [
        index for index, route in enumerate(routes)
        if route.__class__.__name__ == "Mount"
        and (
            getattr(route, "name", None) == "frontend"
            or getattr(route, "path", None) in {"", "/"}
        )
    ]
    return matches[0] if matches else None


def test_tag_audit_routes_are_installed_once_and_precede_static_frontend_when_present():
    get_context = _route("/api/tag-audit/context", "GET")
    post_context = _route("/api/tag-audit/context", "POST")
    checklist = _route("/api/tag-audit/checklist", "GET")
    check = _route("/api/tag-audit/check", "POST")

    routes = list(main_api.app.routes)
    frontend_mount_index = _frontend_mount_index(routes)
    if frontend_mount_index is not None:
        assert routes.index(get_context) < frontend_mount_index
        assert routes.index(post_context) < frontend_mount_index
        assert routes.index(checklist) < frontend_mount_index
        assert routes.index(check) < frontend_mount_index


def test_tag_audit_route_helper_handles_starlette_root_mount_normalization(tmp_path):
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    app = FastAPI()
    app.mount("/", StaticFiles(directory=str(tmp_path), html=True), name="frontend")
    core = SimpleNamespace(app=app)

    async def endpoint():
        return {"ok": True}

    main_api._insert_tag_audit_route_before_frontend(
        core,
        "/api/tag-audit/context",
        endpoint,
        ["POST"],
        response_model=None,
    )

    routes = list(app.routes)
    api_route = next(
        route for route in routes
        if getattr(route, "path", None) == "/api/tag-audit/context"
        and "POST" in (getattr(route, "methods", None) or set())
    )
    frontend_mount_index = _frontend_mount_index(routes)
    assert frontend_mount_index is not None
    assert routes.index(api_route) < frontend_mount_index


def test_all_tag_audit_routes_require_admin():
    for path, method in (
        ("/api/tag-audit/context", "GET"),
        ("/api/tag-audit/context", "POST"),
        ("/api/tag-audit/checklist", "GET"),
        ("/api/tag-audit/check", "POST"),
    ):
        route = _route(path, method)
        dependency_calls = [
            getattr(dep, "call", None) for dep in route.dependant.dependencies
        ]
        assert main_api.require_admin in dependency_calls


def test_tag_audit_install_does_not_replace_existing_ctkm_route():
    route = _route("/api/jobs/ctkm", "POST")
    assert route.endpoint is main_api.enqueue_ctkm
