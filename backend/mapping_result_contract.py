# -*- coding: utf-8 -*-
"""Validate mapping results and reject sheets with no business rows."""
from __future__ import annotations

from modules.facade_contracts import register_post_facade_hook


_HOOK_NAME = "mapping-result-contract-v1"
_WRAPPER_MARKER = "_ctkm_mapping_result_contract_v1"


def install_mapping_result_contract(core_module, validate_mapping) -> None:
    if getattr(core_module.app.state, "mapping_result_contract_v1", False):
        return

    main_mod = core_module._main_mod
    main_core = getattr(main_mod, "_core", None)
    if main_core is None:
        raise RuntimeError("Không tìm thấy _ctkm_main_core để cài mapping result contract")

    def _cache_context(sheet_name, df) -> dict:
        return {
            "dataframe": df,
            "sheet_name": sheet_name,
            "sample_rows_per_column": main_mod.cfg.GEMINI_CONFIG.get(
                "sample_rows_per_column", 8
            ),
        }

    def evict_cache(sheet_name, df, schema_section) -> None:
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
            list(df.columns),
            schema_section,
            prompt_version,
            **_cache_context(sheet_name, df),
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


    def get_validated_cached_mapping(sheet_name, df, schema_section):
        prompt_version = main_mod.cfg.GEMINI_CONFIG.get(
            "prompt_version", "column-mapping-v2"
        )
        cached = main_mod.MC.get_cached_mapping(
            list(df.columns),
            schema_section,
            prompt_version,
            **_cache_context(sheet_name, df),
        )
        if not isinstance(cached, dict) or not cached.get("mapping"):
            return None
        try:
            checked = validate_resolved(
                sheet_name, df, schema_section, cached["mapping"]
            )
        except ValueError as exc:
            if "subtotal/Total/control" in str(exc) or "Total/filter metadata" in str(exc):
                raise
            evict_cache(sheet_name, df, schema_section)
            return None
        return checked, cached

    main_mod._get_validated_cached_mapping = get_validated_cached_mapping
    main_core._get_validated_cached_mapping = get_validated_cached_mapping

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
            evict_cache(sheet_name, df, schema_section)
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
                list(df.columns),
                safe,
                schema_section,
                prompt_version,
                **_cache_context(sheet_name, df),
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

    def bind_facades(current, facade_module=None) -> None:
        # ``main_mod`` is the facade instance retained by backend.main_api_core.
        # A later execution may use another module name. Keep both references and
        # the shared core on the exact same hardened callable.
        main_mod._get_or_map = current
        if facade_module is not None:
            facade_module._get_or_map = current

    def apply_get_or_map_contract(core, facade_module=None) -> None:
        """Wrap the current facade mapper, never the immutable facade baseline."""
        current = core._get_or_map
        if getattr(current, _WRAPPER_MARKER, False):
            bind_facades(current, facade_module)
            return

        def validated_current(sheet_name, df, schema_section, mapping_logs):
            return recover_or_validate(
                current, sheet_name, df, schema_section, mapping_logs
            )

        setattr(validated_current, _WRAPPER_MARKER, True)
        validated_current.__wrapped__ = current
        core._get_or_map = validated_current
        bind_facades(validated_current, facade_module)

    # Register once on the shared core. The initial API import has already built
    # main.py, so apply immediately; future facade executions invoke the same hook
    # after rebuilding their raw wrappers.
    register_post_facade_hook(main_core, _HOOK_NAME, apply_get_or_map_contract)
    apply_get_or_map_contract(main_core, main_mod)

    # Preflight should not let a stale saved preset poison a standard workbook.
    # Resolve without AI in this order: manual -> saved preset -> deterministic
    # company mapping -> validated mapping cache. Only then is Gemini required.
    from backend import input_contract

    def mapping_or_none(
        main_module, df, schema_section, explicit, preset, *, kind: str, sheet_name=None
    ):
        sheet_label = str(
            sheet_name
            or getattr(df, "attrs", {}).get("sheet_name")
            or kind.upper()
        )
        if explicit is not None:
            return validate_resolved(
                sheet_label, df, schema_section, explicit
            ), "manual"
        if preset:
            try:
                checked = validate_resolved(
                    sheet_label, df, schema_section, preset
                )
                return checked, "saved-preset"
            except ValueError as exc:
                if "subtotal/Total/control" in str(exc) or "Total/filter metadata" in str(exc):
                    raise

        infer = (
            main_module._infer_standard_fact_mapping
            if kind == "fact" else main_module._infer_standard_pog_mapping
        )
        inferred = infer(df)
        if inferred:
            suffix = "-after-stale-preset" if preset else ""
            checked = validate_resolved(
                sheet_label, df, schema_section, inferred
            )
            return checked, f"standard-{kind}{suffix}"

        local_infer = getattr(main_module, "_infer_local_value_mapping", None)
        if callable(local_infer):
            candidate = local_infer(df, kind)
            if candidate:
                checked = validate_resolved(
                    sheet_label,
                    df,
                    schema_section,
                    candidate.get("mapping") or {},
                )
                suffix = "-after-stale-preset" if preset else ""
                return checked, f"{candidate.get('source') or f'local-value-{kind}'}{suffix}"

        cached_result = get_validated_cached_mapping(
            sheet_label, df, schema_section
        )
        if cached_result is not None:
            checked, _cached = cached_result
            suffix = "-after-stale-preset" if preset else ""
            return checked, f"cache{suffix}"

        return (
            None,
            "gemini-required-after-stale-preset"
            if preset else "gemini-required",
        )

    input_contract._mapping_or_none = mapping_or_none
    core_module.app.state.mapping_result_contract_v1 = True
