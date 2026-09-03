from pathlib import Path


def test_main_api_installs_hardening_only_through_contract_suite():
    root = Path(__file__).resolve().parents[1]
    source = (root / "backend" / "main_api.py").read_text(encoding="utf-8")

    assert "from backend.contract_suite import install_contract_suite" in source
    assert "install_contract_suite(_core)" in source

    # Installer ownership belongs to backend/contract_suite.py. Keeping individual
    # imports/calls out of main_api.py prevents order from drifting into two places.
    for installer in (
        "install_runtime_contract",
        "install_input_contract",
        "install_mapping_result_contract",
        "install_gemini_availability_contract",
        "install_tem_r_resource_contract",
        "install_auxiliary_workflows_contract",
        "install_expiration_api_contract",
        "install_final_output_contract",
        "install_preview_contract",
    ):
        assert f"from backend.{installer}" not in source
        assert f"{installer}(_core" not in source
