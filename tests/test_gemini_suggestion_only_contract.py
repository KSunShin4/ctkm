from pathlib import Path


def test_gemini_is_preview_only_and_never_an_executable_cache_source():
    source = Path("backend/gemini_suggestion_only_contract.py").read_text(encoding="utf-8")

    assert 'return None, "approval-required"' in source
    assert 'safe["source"] = "gemini-suggestion-unapproved"' in source
    assert "get_cached_mapping" not in source
    assert "save_mapping" not in source
    assert "MC.save_mapping" not in source


def test_explicit_mapping_requires_saved_confirmation_or_deterministic_identity():
    source = Path("backend/gemini_suggestion_only_contract.py").read_text(encoding="utf-8")

    assert "checked == confirmed_preset" in source
    assert "checked == deterministic" in source
    assert 'return checked, "saved-preset-confirmed"' in source
    assert 'return checked, f"standard-{kind}"' in source


def test_implicit_gemini_execution_is_blocked_before_job_run():
    source = Path("backend/gemini_suggestion_only_contract.py").read_text(encoding="utf-8")

    assert "def block_implicit_gemini" in source
    assert "status_code=422" in source
    assert "Gemini chỉ được dùng để gợi ý" in source
    assert '"/api/preview-mapping"' in source
    assert "preview_state.allowed = True" in source
    assert "preview_state.allowed = False" in source


def test_core_mapper_never_falls_through_to_historical_gemini_mapper():
    source = Path("backend/gemini_suggestion_only_contract.py").read_text(encoding="utf-8")
    mapper = source.split("def deterministic_get_or_map", 1)[1].split(
        "deterministic_get_or_map._ctkm_mapping_result_contract_v1", 1
    )[0]

    assert "map_columns_with_gemini" not in mapper
    assert "_original_get_or_map" not in mapper
    assert "get_cached_mapping" not in mapper
    assert "chưa được xác nhận" in mapper


def test_contract_suite_installs_suggestion_only_after_availability_gate():
    source = Path("backend/contract_suite.py").read_text(encoding="utf-8")

    assert "install_gemini_suggestion_only_contract" in source
    order = source.split("CONTRACT_ORDER = (", 1)[1].split(")", 1)[0]
    assert order.index('"gemini-availability"') < order.index('"gemini-suggestion-only"')
    install = source.split("def install_contract_suite", 1)[1]
    assert install.index("install_gemini_availability_contract") < install.index(
        "install_gemini_suggestion_only_contract"
    )
