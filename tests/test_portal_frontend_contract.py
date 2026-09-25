from backend import main_api


def _route(path: str, method: str = "GET"):
    matches = [
        route for route in main_api.app.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", set()) or set())
    ]
    assert len(matches) == 1, (path, len(matches))
    return matches[0]


def test_portal_module_routes_are_installed_before_static_frontend():
    assert main_api.app.state.portal_frontend_contract_v1 is True
    routes = list(main_api.app.routes)
    mount_index = next(
        (
            i for i, route in enumerate(routes)
            if route.__class__.__name__ == "Mount"
            and (getattr(route, "name", None) == "frontend" or getattr(route, "path", None) in {"", "/"})
        ),
        len(routes),
    )
    for path in ("/guide", "/assistant"):
        route = _route(path)
        assert routes.index(route) < mount_index
        assert not route.dependant.dependencies
