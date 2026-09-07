from backend import main_api
from backend import tag_audit_shelf_contract as shelf_contract


def _route(path: str, method: str):
    matches = [
        route for route in main_api.app.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", None) or set())
    ]
    assert len(matches) == 1
    return matches[0]


def test_shelf_routes_are_store_facing_not_admin_only():
    for path, method in (
        ("/api/tag-audit/shelf/session", "POST"),
        ("/api/tag-audit/shelf/session/{session_id}", "GET"),
    ):
        route = _route(path, method)
        dependency_calls = [getattr(dep, "call", None) for dep in route.dependant.dependencies]
        assert main_api.require_admin not in dependency_calls


def test_shelf_routes_precede_static_frontend_when_present():
    routes = list(main_api.app.routes)
    mount_indexes = [
        index for index, route in enumerate(routes)
        if route.__class__.__name__ == "Mount"
        and (getattr(route, "name", None) == "frontend" or getattr(route, "path", None) in {"", "/"})
    ]
    if not mount_indexes:
        return
    mount_index = mount_indexes[0]
    assert routes.index(_route("/api/tag-audit/shelf/session", "POST")) < mount_index
    assert routes.index(_route("/api/tag-audit/shelf/session/{session_id}", "GET")) < mount_index


def test_shelf_grouping_keeps_action_count_and_unique_sku_count():
    items = shelf_contract._decorate_items([
        {"check_key":"a1","item_id":"P1","pog_code":"POG-A","location_id":"L1"},
        {"check_key":"a2","item_id":"P1","pog_code":"POG-A","location_id":"L1"},
        {"check_key":"b1","item_id":"P2","pog_code":"POG-A","location_id":"L1"},
        {"check_key":"c1","item_id":"P3","pog_code":"POG-B","location_id":""},
    ])
    shelves = shelf_contract._build_shelves(items)

    assert items[0]["shelf_key"] == "POG-A::L1"
    assert items[0]["shelf_label"] == "POG-A · L1"
    assert shelves[0]["action_count"] == 3
    assert shelves[0]["sku_count"] == 2
    assert shelves[1]["action_count"] == 1
    assert shelves[1]["sku_count"] == 1


def test_missing_pog_and_location_are_grouped_explicitly():
    items = shelf_contract._decorate_items([
        {"check_key":"a","item_id":"P1","pog_code":"","location_id":""},
        {"check_key":"b","item_id":"P2","pog_code":None,"location_id":None},
    ])
    shelves = shelf_contract._build_shelves(items)
    assert len(shelves) == 1
    assert shelves[0]["shelf_key"] == "__NO_LOCATION__"
    assert shelves[0]["shelf_label"] == "Chưa có vị trí kệ"
    assert shelves[0]["action_count"] == 2
