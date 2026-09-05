from backend import main_api


def _route(path: str, method: str):
    matches = [
        route for route in main_api.app.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", None) or set())
    ]
    assert len(matches) == 1
    return matches[0]


def test_tag_audit_routes_are_installed_once_and_before_static_frontend():
    get_context = _route("/api/tag-audit/context", "GET")
    post_context = _route("/api/tag-audit/context", "POST")
    check = _route("/api/tag-audit/check", "POST")

    routes = list(main_api.app.routes)
    frontend_mount_index = next(
        index for index, route in enumerate(routes)
        if getattr(route, "path", None) == "/" and route.__class__.__name__ == "Mount"
    )
    assert routes.index(get_context) < frontend_mount_index
    assert routes.index(post_context) < frontend_mount_index
    assert routes.index(check) < frontend_mount_index


def test_all_tag_audit_routes_require_admin():
    for path, method in (
        ("/api/tag-audit/context", "GET"),
        ("/api/tag-audit/context", "POST"),
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
