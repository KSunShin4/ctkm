from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.gemini_availability_contract import install_gemini_availability_contract


def test_gemini_availability_check_is_idempotent_and_only_wraps_enforcement(monkeypatch):
    calls = {"cooldown": 0}

    def old_enforce():
        calls["cooldown"] += 1

    core = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace()),
        _enforce_gemini_cooldown=old_enforce,
        HTTPException=HTTPException,
    )

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    install_gemini_availability_contract(core)
    installed = core._enforce_gemini_cooldown

    with pytest.raises(HTTPException) as exc:
        installed()
    assert exc.value.status_code == 503
    assert "GEMINI_API_KEY" in str(exc.value.detail)
    assert calls["cooldown"] == 1

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    installed()
    assert calls["cooldown"] == 2

    install_gemini_availability_contract(core)
    assert core._enforce_gemini_cooldown is installed


def test_saved_only_and_standard_mappings_do_not_call_availability_gate_by_contract():
    source = open("backend/input_contract.py", encoding="utf-8").read()
    assert "if mapping_mode == \"saved_only\" and needs_gemini" in source
    assert "if mapping_mode == \"auto\" and needs_gemini" in source
    assert "core_module._enforce_gemini_cooldown()" in source
    # The old unconditional auto-mode gate must stay absent from the replacement
    # enqueue path; otherwise standard/preset runs would be blocked by cooldown.
    enqueue = source.split("async def enqueue_ctkm", 1)[1].split("async def preview_mapping_job", 1)[0]
    assert "if mapping_mode == \"auto\":\n            core_module._enforce_gemini_cooldown()" not in enqueue
