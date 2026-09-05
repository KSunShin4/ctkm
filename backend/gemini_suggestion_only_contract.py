# -*- coding: utf-8 -*-
"""Restrict Gemini to explicit mapping suggestions only.

Production execution may use only explicit/manual mappings, saved presets, or
recognized deterministic company mappings. Gemini may be called only by the
mapping-preview surface to propose a mapping for human review. Suggestions are
never written to the legacy mapping cache and are never executable until the
user saves/confirms them as a preset or sends them explicitly.
"""
from __future__ import annotations

import threading

from modules.facade_contracts import register_post_facade_hook


_HOOK_NAME = "gemini-suggestion-only-contract-v1"


def install_gemini_suggestion_only_contract(core_module) -> None:
    if getattr(core_module.app.state, "gemini_suggestion_only_contract_v1", False):
        return

    main_mod = core_module._main_mod
    main_core = getattr(main_mod, "_core", None)
    if main_core is None:
        raise RuntimeError("Không tìm thấy _ctkm_main_core để khóa Gemini suggestion-only")

    from backend import input_contract
    validate_mapping = input_contract.validate_manual_mapping

    # Availability/cooldown gate installed earlier. Keep a private reference for
    # preview-only AI suggestions, then replace the public gate so production
    # enqueue cannot call Gemini implicitly.
    gemini_available = core_module._enforce_gemini_cooldown
    preview_state = threading.local()

    def deterministic_mapping_or_none(main_module, df, schema_section, explicit, preset, *, kind: str):
        """Resolve executable mapping without Gemini or legacy AI cache."""
        if explicit is not None:
            checked = validate_mapping(explicit, df, schema_section)
            return checked, "manual-confirmed"

        if preset:
            try:
                checked = validate_mapping(preset, df, schema_section)
                return checked, "saved-preset"
            except ValueError:
                # A stale preset is not executable. Deterministic recognition may
                # still recover a standard Pharmacity file below.
                pass

        infer = (
            main_module._infer_standard_fact_mapping
            if kind == "fact" else main_module._infer_standard_pog_mapping
        )
        inferred = infer(df)
        if inferred:
            checked = validate_mapping(inferred, df, schema_section)
            return checked, f"standard-{kind}"

        return None, "approval-required"

    input_contract._mapping_or_none = deterministic_mapping_or_none

    def deterministic_get_or_map(sheet_name, df, schema_section, mapping_logs):
        """Core/CLI mapper: deterministic only; never call Gemini automatically."""
        is_fact = (
            "campaign_name" in schema_section
            and "promo_from" in schema_section
            and "promo_to" in schema_section
        )
        is_pog = (
            "store_id" in schema_section
            and "pog_code" in schema_section
            and "campaign_name" not in schema_section
        )
        if is_fact:
            inferred = main_mod._infer_standard_fact_mapping(df)
            source = "standard-fact"
        elif is_pog:
            inferred = main_mod._infer_standard_pog_mapping(df)
            source = "standard-pog"
        else:
            inferred = {}
            source = "deterministic"

        if inferred:
            checked = validate_mapping(inferred, df, schema_section)
            mapping_logs.append({
                "sheet_name": sheet_name,
                "mapping": checked,
                "confidence": {column: 1.0 for column in checked},
                "unmapped": [str(column) for column in df.columns if column not in checked],
                "source": source,
            })
            return checked

        raise ValueError(
            f"Mapping cho sheet '{sheet_name}' chưa được xác nhận. "
            "Hãy xem gợi ý mapping, kiểm tra và lưu mapping đã xác nhận trước khi chạy."
        )

    # Keep compatibility with the existing contract-suite verification marker,
    # while making the final execution policy explicit.
    deterministic_get_or_map._ctkm_mapping_result_contract_v1 = True
    deterministic_get_or_map._ctkm_gemini_suggestion_only_v1 = True

    def bind_execution_mapper(core, facade_module=None):
        core._get_or_map = deterministic_get_or_map
        main_mod._get_or_map = deterministic_get_or_map
        if facade_module is not None:
            facade_module._get_or_map = deterministic_get_or_map

    bind_execution_mapper(main_core, main_mod)
    register_post_facade_hook(main_core, _HOOK_NAME, bind_execution_mapper)

    def preview_mapping_suggestion(sheet_name, df, schema_section, mapping_logs=None):
        """Explicit AI suggestion path: validate result, do not save to cache."""
        logs = [] if mapping_logs is None else mapping_logs
        gemini_available()
        result = main_mod.CM.map_columns_with_gemini(sheet_name, df, schema_section)
        checked = validate_mapping(result.mapping, df, schema_section)
        safe = main_mod.MC.mapping_result_to_dict_safe(result)
        safe["mapping"] = checked
        safe["source"] = "gemini-suggestion-unapproved"
        logs.append({**safe, "sheet_name": sheet_name})
        return checked, logs

    main_mod.preview_mapping = preview_mapping_suggestion
    main_core.preview_mapping = preview_mapping_suggestion

    def block_implicit_gemini() -> None:
        if getattr(preview_state, "allowed", False):
            gemini_available()
            return
        raise core_module.HTTPException(
            status_code=422,
            detail=(
                "Mapping chưa được xác nhận. Gemini chỉ được dùng để gợi ý trong màn hình "
                "duyệt mapping; hãy kiểm tra và lưu mapping đã xác nhận trước khi chạy."
            ),
        )

    core_module._enforce_gemini_cooldown = block_implicit_gemini

    # The input contract's preview endpoint calls _enforce_gemini_cooldown before
    # invoking main.preview_mapping. Wrap only that endpoint in a thread-local
    # permission so production enqueue remains blocked.
    original_preview = core_module.preview_mapping_job

    async def preview_mapping_job(*args, **kwargs):
        preview_state.allowed = True
        try:
            return await original_preview(*args, **kwargs)
        finally:
            preview_state.allowed = False

    for route in core_module.app.routes:
        if getattr(route, "path", None) != "/api/preview-mapping":
            continue
        if "POST" not in (getattr(route, "methods", None) or set()):
            continue
        route.endpoint = preview_mapping_job
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            dependant.call = preview_mapping_job
        break
    else:
        raise RuntimeError("Không tìm thấy POST /api/preview-mapping để khóa Gemini preview-only")

    core_module.preview_mapping_job = preview_mapping_job
    core_module.app.state.gemini_suggestion_only_contract_v1 = True
