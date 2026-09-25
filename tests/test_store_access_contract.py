from backend import main_api
from backend.store_access_contract import STORE_ROUTES


def _route(path: str, method: str):
    matches = [
        route for route in main_api.app.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", set()) or set())
    ]
    assert len(matches) == 1, (method, path, len(matches))
    return matches[0]


def _dependencies(path: str, method: str):
    return [
        getattr(dep, "call", None)
        for dep in _route(path, method).dependant.dependencies
    ]


def test_store_ctkm_and_tem_routes_do_not_require_admin():
    assert main_api.app.state.store_access_contract_v1 is True
    for method, path in STORE_ROUTES:
        assert main_api.require_admin not in _dependencies(path, method), (method, path)


def test_admin_surfaces_remain_admin_only():
    for method, path in (
        ("GET", "/api/queue/status"),
        ("GET", "/api/jobs"),
        ("GET", "/api/presets"),
        ("POST", "/api/presets"),
        ("DELETE", "/api/presets"),
        ("POST", "/api/schedules/generate"),
        ("POST", "/api/schedules/validate"),
        ("POST", "/api/schedules/export.xlsx"),
    ):
        assert main_api.require_admin in _dependencies(path, method), (method, path)
