# -*- coding: utf-8 -*-
"""Restrict Gemini to explicit mapping suggestions only.

Production execution may use only explicit/manual mappings, saved presets, or
recognized deterministic company mappings. Gemini may be called only by the
mapping-preview surface to propose a mapping for human review. Suggestions are
never written to the legacy mapping cache and are never executable until the
user saves/confirms them as a preset or sends them explicitly.
"""
from __future__ import annotations


def install_gemini_suggestion_only_contract(core_module) -> None:
    if getattr(core_module.app.state, "gemini_suggestion_only_contract_v1", False):
        return

    main_mod = core_module._main_mod
    main_core = getattr(main_mod, "_core", None)
    if main_core is None:
        raise RuntimeError("Không tìm thấy _ctkm_main_core để khóa Gemini suggestion-only")

    from backend import input_contract
    validate_mapping = input_contract.validate_manual_mapping

    def deterministic_mapping_or_none(main_module, df, schema_section, explicit, preset, *, kind: str):
        """Resolve executable mapping without Gemini or legacy AI cache."""
        sheet_label = str(getattr(df, "attrs", {}).get("sheet_name") or kind.upper())
        if explicit is not None:
            checked = validate_mapping(explicit, df, schema_section)
            return checked, "manual"

        if preset:
            try:
                checked = validate_mapping(preset, df, schema_section)
                return checked, "saved-preset"
            except ValueError:
                # Do not trust a stale preset; deterministic recognition may still
                # recover a standard Pharmacity file below.
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

    # Bind execution mapper to both retained facade and shared core. Explicit
    # mapping_override continues to bypass _get_or_map in main_core._process.
    main_core._get_or_map = deterministic_get_or_map
    main_mod._get_or_map = deterministic_get_or_map

    def preview_mapping_suggestion(sheet_name, df, schema_section, mapping_logs=None):
        """Explicit AI suggestion path: validate result, do not save to cache."""
        logs = [] if mapping_logs is None else mapping_logs
        core_module._enforce_gemini_cooldown()
        result = main_mod.CM.map_columns_with_gemini(sheet_name, df, schema_section)
        checked = validate_mapping(result.mapping, df, schema_section)
        safe = main_mod.MC.mapping_result_to_dict_safe(result)
        safe["mapping"] = checked
        safe["source"] = "gemini-suggestion"
        logs.append({**safe, "sheet_name": sheet_name})
        return checked, logs

    main_mod.preview_mapping = preview_mapping_suggestion
    main_core.preview_mapping = preview_mapping_suggestion

    core_module.app.state.gemini_suggestion_only_contract_v1 = True
