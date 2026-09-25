import zipfile

import pytest

from backend import main_api
from backend.tem_r_resource_contract import validate_tem_r_archive


def test_tem_r_archive_uses_uncompressed_size_not_zip_size(tmp_path):
    path = tmp_path / "compressed.xlsx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "x")
        archive.writestr("xl/workbook.xml", "x")
        archive.writestr("xl/worksheets/sheet1.xml", "0" * 4096)

    assert path.stat().st_size < 4096
    with pytest.raises(ValueError, match="giải nén quá lớn"):
        validate_tem_r_archive(path, max_uncompressed_bytes=1024)
    assert validate_tem_r_archive(path, max_uncompressed_bytes=8192) == path


def test_auxiliary_installers_are_active_once_on_public_api_module():
    state = main_api.app.state
    assert state.tem_r_resource_contract_v1 is True
    assert state.auxiliary_workflows_contract_v1 is True
    assert state.expiration_api_contract_v1 is True

    inspect_before = main_api._tem_r_mod.inspect_tem_r_workbook
    create_before = main_api._tem_r_mod.create_tem_r_workbook
    expiration_before = main_api._expiration_mod.check_entries

    from backend.tem_r_resource_contract import install_tem_r_resource_contract
    from backend.auxiliary_workflows_contract import install_auxiliary_workflows_contract
    from backend.expiration_api_contract import install_expiration_api_contract

    install_tem_r_resource_contract(main_api)
    install_auxiliary_workflows_contract(main_api)
    install_expiration_api_contract(main_api)

    assert main_api._tem_r_mod.inspect_tem_r_workbook is inspect_before
    assert main_api._tem_r_mod.create_tem_r_workbook is create_before
    assert main_api._expiration_mod.check_entries is expiration_before


def test_auxiliary_routes_keep_expected_access_boundaries():
    routes = {
        (getattr(route, "path", None), next(iter(getattr(route, "methods", set()) or set()), None)): route
        for route in main_api.app.routes
    }

    def route(path, method):
        return next(
            item for item in main_api.app.routes
            if getattr(item, "path", None) == path
            and method in (getattr(item, "methods", None) or set())
        )

    for path in ("/api/inspect-tem-r", "/api/jobs/tem-r", "/api/tem-r"):
        dependency_calls = [getattr(dep, "call", None) for dep in route(path, "POST").dependant.dependencies]
        assert main_api.require_admin not in dependency_calls

    expiration_dependencies = [
        getattr(dep, "call", None)
        for dep in route("/api/check-expiration", "POST").dependant.dependencies
    ]
    assert main_api.require_admin not in expiration_dependencies
