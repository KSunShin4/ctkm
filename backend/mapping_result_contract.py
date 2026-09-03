# -*- coding: utf-8 -*-
"""Validate every non-manual mapping before it reaches normalization."""
from __future__ import annotations


def install_mapping_result_contract(core_module, validate_mapping) -> None:
    if getattr(core_module.app.state, "mapping_result_contract_v1", False):
        return

    main_mod = core_module._main_mod
    main_core = getattr(main_mod, "_core", None)
    if main_core is None:
        raise RuntimeError("Không tìm thấy _ctkm_main_core để cài mapping result contract")

    def recover_or_validate(original, sheet_name, df, schema_section, mapping_logs):
        before = len(mapping_logs)
        mapping = original(sheet_name, df, schema_section, mapping_logs)
        try:
            return validate_mapping(mapping, df, schema_section)
        except ValueError as exc:
            entry = mapping_logs[-1] if len(mapping_logs) > before else {}
            source = str(entry.get("source") or "") if isinstance(entry, dict) else ""
            if source != "cache":
                raise ValueError(
                    f"Mapping cho sheet '{sheet_name}' không đủ an toàn: {exc}"
                ) from exc

            # A stale cache must never poison a run. Retry the mapper once, then
            # validate the new result before replacing the cache entry.
            result = main_mod.CM.map_columns_with_gemini(sheet_name, df, schema_section)
            checked = validate_mapping(result.mapping, df, schema_section)
            prompt_version = main_mod.cfg.GEMINI_CONFIG.get(
                "prompt_version", "column-mapping-v2"
            )
            result.mapping = checked
            safe = main_mod.MC.mapping_result_to_dict_safe(result)
            main_mod.MC.save_mapping(
                list(df.columns), safe, schema_section, prompt_version
            )
            if len(mapping_logs) > before:
                mapping_logs.pop()
            mapping_logs.append({
                **safe,
                "source": "gemini-cache-recovery",
                "sheet_name": sheet_name,
            })
            return checked

    # Current facade wrapper includes deterministic Pharmacity mapping before the
    # historical cache/Gemini fallback. Validate its final result today.
    current_get_or_map = main_core._get_or_map

    def validated_current(sheet_name, df, schema_section, mapping_logs):
        return recover_or_validate(
            current_get_or_map, sheet_name, df, schema_section, mapping_logs
        )

    main_core._get_or_map = validated_current
    main_mod._get_or_map = validated_current

    # main.py can be executed later under another module name. Its import-order
    # baseline is what a future facade wrapper will call after deterministic
    # inference, so harden that baseline as well instead of allowing reload to
    # bypass this contract.
    baseline = getattr(main_core, "_ctkm_main_facade_baseline", None)
    if isinstance(baseline, dict) and callable(baseline.get("get_or_map")):
        old_baseline = baseline["get_or_map"]

        def validated_baseline(sheet_name, df, schema_section, mapping_logs):
            return recover_or_validate(
                old_baseline, sheet_name, df, schema_section, mapping_logs
            )

        baseline["get_or_map"] = validated_baseline

    core_module.app.state.mapping_result_contract_v1 = True
