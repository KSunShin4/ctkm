# -*- coding: utf-8 -*-
"""Validate mapping results and reject sheets with no business rows."""
from __future__ import annotations


def install_mapping_result_contract(core_module, validate_mapping) -> None:
    if getattr(core_module.app.state, "mapping_result_contract_v1", False):
        return

    main_mod = core_module._main_mod
    main_core = getattr(main_mod, "_core", None)
    if main_core is None:
        raise RuntimeError("Không tìm thấy _ctkm_main_core để cài mapping result contract")

    def evict_cache(df, schema_section) -> None:
        compute_signature = getattr(main_mod.MC, "compute_signature", None)
        lock = getattr(main_mod.MC, "_CACHE_LOCK", None)
        load_unlocked = getattr(main_mod.MC, "_load_unlocked", None)
        save_unlocked = getattr(main_mod.MC, "_save_unlocked", None)
        if (
            not callable(compute_signature) or lock is None
            or not callable(load_unlocked) or not callable(save_unlocked)
        ):
            return
        prompt_version = main_mod.cfg.GEMINI_CONFIG.get(
            "prompt_version", "column-mapping-v2"
        )
        signature = compute_signature(
            list(df.columns), schema_section, prompt_version
        )
        with lock:
            cache = load_unlocked()
            if signature in cache:
                del cache[signature]
                save_unlocked(cache)

    def validate_business_presence(sheet_name, df, mapping, schema_section) -> None:
        """Reject only sheets whose mapped rows are all recognized control rows.

        Genuine malformed business rows (for example a promotion missing ITEMID)
        remain valid input so the pipeline can surface them in Cần review. The
        check reuses the same fact/POG control classifiers as operational code.
        """
        mapped = main_mod.NM.apply_mapping(df.copy(), mapping)
        mapped = main_mod.NM.clean_values(mapped)
        if mapped.empty:
            raise ValueError(f"Sheet '{sheet_name}' không có dòng dữ liệu nghiệp vụ.")

        is_fact = (
            "campaign_name" in schema_section
            and "promo_from" in schema_section
            and "promo_to" in schema_section
        )
        if is_fact:
            separator = getattr(main_mod, "_separate_fact_control_rows", None)
            if callable(separator):
                business, _metadata = separator(mapped)
            else:
                business = mapped
            if business.empty:
                raise ValueError(
                    f"Sheet '{sheet_name}' chỉ chứa subtotal/Total/control; "
                    "hãy chọn sheet CTKM/Clearance có dòng sản phẩm nghiệp vụ."
                )
            return

        is_pog = "store_id" in schema_section and "campaign_name" not in schema_section
        if is_pog:
            classifier = getattr(main_mod.JN, "_pog_control_row_kind", None)
            if callable(classifier):
                kinds = mapped.apply(classifier, axis=1)
                business = mapped[kinds.isna()]
            else:
                business = mapped
            if business.empty:
                raise ValueError(
                    f"Sheet POG '{sheet_name}' chỉ chứa Total/filter metadata; "
                    "hãy chọn sheet có dữ liệu vị trí sản phẩm."
                )

    def validate_resolved(sheet_name, df, schema_section, mapping):
        checked = validate_mapping(mapping, df, schema_section)
        validate_business_presence(sheet_name, df, checked, schema_section)
        return checked

    def recover_or_validate(original, sheet_name, df, schema_section, mapping_logs):
        before = len(mapping_logs)
        mapping = original(sheet_name, df, schema_section, mapping_logs)
        try:
            checked = validate_mapping(mapping, df, schema_section)
        except ValueError as exc:
            entry = mapping_logs[-1] if len(mapping_logs) > before else {}
            source = str(entry.get("source") or "") if isinstance(entry, dict) else ""
            # The historical mapper writes Gemini output to cache before this new
            # validator runs. Never retain a mapping that failed the contract.
            evict_cache(df, schema_section)
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

        validate_business_presence(sheet_name, df, checked, schema_section)
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

    # Preflight should not let a stale saved preset poison a standard workbook.
    # Resolve without AI in this order: manual -> saved preset -> deterministic
    # company mapping -> validated mapping cache. Only then is Gemini required.
    from backend import input_contract

    def mapping_or_none(main_module, df, schema_section, explicit, preset, *, kind: str):
        sheet_label = str(getattr(df, "attrs", {}).get("sheet_name") or kind.upper())
        if explicit is not None:
            return validate_resolved(sheet_label, df, schema_section, explicit), "manual"
        if preset:
            try:
                checked = validate_resolved(sheet_label, df, schema_section, preset)
                return checked, "saved-preset"
            except ValueError as exc:
                # A structurally stale preset may be ignored, but a control-only
                # sheet must not silently fall through to another mapper.
                if "subtotal/Total/control" in str(exc) or "Total/filter metadata" in str(exc):
                    raise
        infer = (
            main_module._infer_standard_fact_mapping
            if kind == "fact" else main_module._infer_standard_pog_mapping
        )
        inferred = infer(df)
        if inferred:
            suffix = "-after-stale-preset" if preset else ""
            checked = validate_resolved(sheet_label, df, schema_section, inferred)
            return checked, f"standard-{kind}{suffix}"

        prompt_version = main_module.cfg.GEMINI_CONFIG.get(
            "prompt_version", "column-mapping-v2"
        )
        cached = main_module.MC.get_cached_mapping(
            list(df.columns), schema_section, prompt_version
        )
        if isinstance(cached, dict) and cached.get("mapping"):
            try:
                checked = validate_resolved(
                    sheet_label, df, schema_section, cached["mapping"]
                )
                suffix = "-after-stale-preset" if preset else ""
                return checked, f"cache{suffix}"
            except ValueError as exc:
                if "subtotal/Total/control" in str(exc) or "Total/filter metadata" in str(exc):
                    raise
                evict_cache(df, schema_section)

        return None, "gemini-required-after-stale-preset" if preset else "gemini-required"

    input_contract._mapping_or_none = mapping_or_none
    core_module.app.state.mapping_result_contract_v1 = True
