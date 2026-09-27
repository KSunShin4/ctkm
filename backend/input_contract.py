# -*- coding: utf-8 -*-
"""Input, mapping and Gemini-fallback contracts for CTKM API requests."""
from __future__ import annotations

import asyncio
from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import shutil
import uuid
import zipfile

import pandas as pd
from fastapi import Depends, File, Form, HTTPException, UploadFile
from typing import Optional


def _validate_xlsx_container(content: bytes, label: str) -> bytes:
    """Reject renamed/non-OOXML files before any job or temp artifact is created."""
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            names = set(archive.namelist())
            required = {"[Content_Types].xml", "xl/workbook.xml"}
            if not required.issubset(names):
                raise ValueError("thiếu cấu trúc workbook OOXML bắt buộc")
    except (zipfile.BadZipFile, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"{label} không phải workbook .xlsx hợp lệ: {exc}",
        ) from exc
    return content


def _required_fields(schema_section: dict) -> set[str]:
    return {
        name for name, meta in schema_section.items()
        if meta.get("required", False) and not meta.get("auto_filled", False)
    }


def validate_manual_mapping(mapping, df: pd.DataFrame, schema_section: dict) -> dict:
    """Require an exact, one-source-to-one-canonical mapping for required fields."""
    if not isinstance(mapping, dict):
        raise ValueError("Mapping thủ công phải là JSON object.")

    source_columns = {str(column) for column in df.columns}
    allowed_fields = {
        name for name, meta in schema_section.items() if not meta.get("auto_filled", False)
    }
    cleaned: dict[str, str] = {}
    for raw_source, raw_target in mapping.items():
        source = str(raw_source)
        target = str(raw_target).strip() if raw_target is not None else ""
        if not source.strip() or not target:
            raise ValueError("Mapping không được chứa source/target rỗng.")
        cleaned[source] = target

    unknown_sources = sorted(set(cleaned) - source_columns)
    invalid_targets = sorted(set(cleaned.values()) - allowed_fields)
    if unknown_sources:
        raise ValueError(f"Mapping có cột nguồn không tồn tại: {unknown_sources}")
    if invalid_targets:
        raise ValueError(f"Mapping có canonical field không hợp lệ: {invalid_targets}")

    duplicate_targets = sorted(
        target for target, count in Counter(cleaned.values()).items() if count > 1
    )
    if duplicate_targets:
        raise ValueError(
            "Mỗi canonical field chỉ được map từ một cột nguồn. Bị trùng: "
            + ", ".join(duplicate_targets)
        )

    missing_required = sorted(_required_fields(schema_section) - set(cleaned.values()))
    if missing_required:
        raise ValueError(
            "Mapping thiếu trường bắt buộc: " + ", ".join(missing_required)
        )
    return cleaned


def validate_output_columns(value, schema: dict) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("selected_output_columns phải là JSON array.")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError("selected_output_columns chỉ được chứa tên field dạng chuỗi không rỗng.")
    cleaned = [item.strip() for item in value]
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("selected_output_columns không được chứa field trùng nhau.")
    allowed = set()
    for section_name in ("fact_fields", "pog_fields"):
        for name, meta in schema.get(section_name, {}).items():
            if not meta.get("auto_filled", False):
                allowed.add(name)
    unknown = sorted(set(cleaned) - allowed)
    if unknown:
        raise ValueError("Output chứa field không hợp lệ: " + ", ".join(unknown))
    return cleaned


def _mapping_or_none(main_mod, df, schema_section, explicit, preset, *, kind: str):
    if explicit is not None:
        return validate_manual_mapping(explicit, df, schema_section), "manual"
    if preset:
        return validate_manual_mapping(preset, df, schema_section), "saved-preset"
    infer = (
        main_mod._infer_standard_fact_mapping
        if kind == "fact" else main_mod._infer_standard_pog_mapping
    )
    inferred = infer(df)
    if inferred:
        return validate_manual_mapping(inferred, df, schema_section), f"standard-{kind}"
    return None, "gemini-required"


def _cleanup_dir(path: Path) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


def _replace_route(core_module, path: str, method: str, endpoint) -> None:
    for route in core_module.app.routes:
        if getattr(route, "path", None) != path:
            continue
        if method not in (getattr(route, "methods", None) or set()):
            continue
        route.endpoint = endpoint
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            dependant.call = endpoint
        return
    raise RuntimeError(f"Không tìm thấy route {method} {path} để cài input contract")


def install_input_contract(core_module) -> None:
    if getattr(core_module.app.state, "input_contract_v1", False):
        return

    main_mod = core_module._main_mod
    main_core = getattr(main_mod, "_core", None)

    # Strong mapping validation must be seen both by API preset endpoints and by
    # main_core._build_manual_mapping_result during actual pipeline execution.
    main_mod._validate_manual_mapping = validate_manual_mapping
    if main_core is not None:
        main_core._validate_manual_mapping = validate_manual_mapping

    original_read = core_module._read_upload_limited

    async def read_upload_limited(upload, max_bytes: int, label: str) -> bytes:
        content = await original_read(upload, max_bytes, label)
        # This shared byte-limit reader is also used by the shelf-tag image route.
        # Validate OOXML only for uploads that are actually declared as .xlsx;
        # CTKM/POG/Tem-R routes already enforce that extension before calling us.
        filename = str(getattr(upload, "filename", "") or "").lower()
        if filename.endswith(".xlsx"):
            return _validate_xlsx_container(content, label)
        return content

    core_module._read_upload_limited = read_upload_limited

    # Record a process-level cooldown only after a real Gemini 429. Standard,
    # preset and manual mappings remain usable because enqueue preflight checks
    # cooldown only when a source genuinely requires Gemini.
    original_gemini = main_mod.CM.map_columns_with_gemini
    if not getattr(original_gemini, "_ctkm_cooldown_wrapped", False):
        def gemini_with_cooldown(*args, **kwargs):
            try:
                return original_gemini(*args, **kwargs)
            except main_mod.CM.GeminiRateLimitError as exc:
                retry_after = int(getattr(exc, "retry_after", 0) or 0)
                core_module._set_gemini_cooldown(max(300, retry_after))
                raise
        gemini_with_cooldown._ctkm_cooldown_wrapped = True
        main_mod.CM.map_columns_with_gemini = gemini_with_cooldown

    async def enqueue_ctkm(
        ctkm_file: UploadFile = File(...), pog_file: UploadFile = File(...),
        clearance_file: Optional[UploadFile] = File(None),
        month: str = Form(...), strict_month: bool = Form(False),
        ctkm_sheet_name: Optional[str] = Form(None),
        clearance_sheet_name: Optional[str] = Form(None),
        pog_sheet_name: Optional[str] = Form(None),
        ctkm_mapping_override: Optional[str] = Form(None),
        pog_mapping_override: Optional[str] = Form(None),
        selected_output_columns: Optional[str] = Form(None),
        business_date: Optional[str] = Form(None),
        mapping_mode: str = Form("auto"),
        _admin: str = Depends(core_module.require_admin),
    ):
        core_module._cleanup_old_jobs()
        business_date_value = core_module._validate_ctkm_request_dates(month, business_date)
        if not ctkm_file.filename or not ctkm_file.filename.lower().endswith(".xlsx") \
                or not pog_file.filename or not pog_file.filename.lower().endswith(".xlsx"):
            raise HTTPException(status_code=422, detail="CTKM và POG phải là file .xlsx")
        if clearance_file and (
            not clearance_file.filename or not clearance_file.filename.lower().endswith(".xlsx")
        ):
            raise HTTPException(status_code=422, detail="Clearance phải là file .xlsx")
        if not pog_sheet_name or not pog_sheet_name.strip():
            raise HTTPException(status_code=422, detail="Hãy chọn sheet POG trước khi chạy pipeline")
        selected_pog_sheet = pog_sheet_name.strip()
        selected_ctkm_sheet = ctkm_sheet_name.strip() if ctkm_sheet_name and ctkm_sheet_name.strip() else None
        selected_clearance_sheet = (
            clearance_sheet_name.strip()
            if clearance_sheet_name and clearance_sheet_name.strip() else None
        )
        if mapping_mode not in {"auto", "saved_only"}:
            raise HTTPException(status_code=422, detail="mapping_mode không hợp lệ")

        upload_tasks = [
            core_module._read_upload_limited(ctkm_file, core_module._MAX_PIPELINE_BYTES, "File CTKM"),
            core_module._read_upload_limited(pog_file, core_module._MAX_PIPELINE_BYTES, "File POG"),
        ]
        if clearance_file:
            upload_tasks.append(core_module._read_upload_limited(
                clearance_file, core_module._MAX_PIPELINE_BYTES, "File Clearance"
            ))
        upload_contents = await asyncio.gather(*upload_tasks)
        ctkm_content, pog_content = upload_contents[:2]
        clearance_content = upload_contents[2] if len(upload_contents) > 2 else None

        try:
            raw_ctkm_override = json.loads(ctkm_mapping_override) if ctkm_mapping_override else None
            raw_pog_override = json.loads(pog_mapping_override) if pog_mapping_override else None
            raw_output = json.loads(selected_output_columns) if selected_output_columns else None
            output_columns = validate_output_columns(raw_output, main_mod.SCHEMA)
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Cấu hình chạy không hợp lệ: {exc}") from exc
        if raw_ctkm_override is not None and not isinstance(raw_ctkm_override, dict):
            raise HTTPException(status_code=422, detail="ctkm_mapping_override phải là JSON object")
        if raw_pog_override is not None and not isinstance(raw_pog_override, dict):
            raise HTTPException(status_code=422, detail="pog_mapping_override phải là JSON object")

        job_id = uuid.uuid4().hex[:8]
        job_dir = core_module._TMP_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        ctkm_path, pog_path = job_dir / "ctkm.xlsx", job_dir / "pog.xlsx"
        clearance_path = job_dir / "clearance.xlsx"
        output_path = core_module._OUT_DIR / f"tong_hop_ctkm_{month}_{job_id}.xlsx"
        ctkm_path.write_bytes(ctkm_content)
        pog_path.write_bytes(pog_content)
        if clearance_content is not None:
            clearance_path.write_bytes(clearance_content)

        try:
            wb_ctkm = await asyncio.to_thread(
                main_mod.L.load_workbook_raw, str(ctkm_path), is_pog_file=False,
                selected_sheet_names=[selected_ctkm_sheet] if selected_ctkm_sheet else None,
            )
            wb_pog = await asyncio.to_thread(
                main_mod.L.load_workbook_raw, str(pog_path), is_pog_file=True,
                selected_sheet_names=[selected_pog_sheet],
            )
            primary_name, primary_sheet = main_mod._select_primary_ctkm_sheet(
                wb_ctkm, selected_ctkm_sheet
            )
            if selected_pog_sheet not in wb_pog.sheets:
                available = ", ".join(wb_pog.sheets) or "(không có sheet dữ liệu)"
                raise ValueError(
                    f"Không tìm thấy sheet POG '{selected_pog_sheet}'. Sheet có sẵn: {available}"
                )
            pog_sheet = wb_pog.sheets[selected_pog_sheet]
            preset = core_module._get_saved_preset(
                list(primary_sheet.df.columns), list(pog_sheet.df.columns)
            )

            ctkm_map, ctkm_source = _mapping_or_none(
                main_mod, primary_sheet.df, main_mod.SCHEMA["fact_fields"],
                raw_ctkm_override, preset.get("ctkm_mapping"), kind="fact",
            )
            pog_map, pog_source = _mapping_or_none(
                main_mod, pog_sheet.df, main_mod.SCHEMA["pog_fields"],
                raw_pog_override, preset.get("pog_mapping"), kind="pog",
            )

            preset_output = preset.get("output_columns")
            if output_columns is None and preset_output is not None:
                output_columns = validate_output_columns(preset_output, main_mod.SCHEMA)

            clearance_map = None
            clearance_source = None
            if clearance_content is not None:
                wb_clearance = await asyncio.to_thread(
                    main_mod.L.load_workbook_raw, str(clearance_path), is_pog_file=False,
                    selected_sheet_names=[selected_clearance_sheet] if selected_clearance_sheet else None,
                )
                clearance_name, clearance_sheet = main_mod._select_primary_ctkm_sheet(
                    wb_clearance, selected_clearance_sheet
                )
                clearance_map, clearance_source = _mapping_or_none(
                    main_mod, clearance_sheet.df, main_mod.SCHEMA["fact_fields"],
                    None, None, kind="fact",
                )
                selected_clearance_sheet = clearance_name

            needs_gemini = [
                name for name, mapping in (
                    ("CTKM", ctkm_map), ("POG", pog_map),
                    ("Clearance", clearance_map if clearance_content is not None else {}),
                ) if mapping is None
            ]
            if mapping_mode == "saved_only" and needs_gemini:
                raise ValueError(
                    "Chế độ chỉ mapping đã lưu không được gọi Gemini. Chưa có mapping an toàn cho: "
                    + ", ".join(needs_gemini)
                )
            if mapping_mode == "auto" and needs_gemini:
                core_module._enforce_gemini_cooldown()

            alignment = main_mod.TF.check_snapshot_alignment(month, wb_pog.pog_snapshot_month)
            if strict_month and not alignment.is_aligned:
                raise ValueError(alignment.warning_message)
        except HTTPException:
            _cleanup_dir(job_dir)
            raise
        except Exception as exc:
            _cleanup_dir(job_dir)
            raise HTTPException(status_code=422, detail=f"Preflight CTKM không đạt: {exc}") from exc

        job = core_module._new_job(job_id, "ctkm", output_path, output_path.name, month=month)
        job["mapping_sources"] = {
            "ctkm": ctkm_source,
            "pog": pog_source,
            "clearance": clearance_source,
        }

        def work(current):
            try:
                current.update(progress=20, message="Đang đọc CTKM và POG")
                confirmed = current.get("confirmed_mappings") or {}
                local_ctkm = confirmed.get("ctkm") or ctkm_map
                local_pog = confirmed.get("pog") or pog_map
                sources = dict(current.get("mapping_sources") or {})

                def resolve_runtime(sheet_name, frame, schema_section, mapping, source):
                    if mapping:
                        return mapping, source, {
                            "mapping": mapping,
                            "confidence": {key: 1.0 for key in mapping},
                            "unmapped": [str(col) for col in frame.columns if col not in mapping],
                            "source": source or "manual",
                        }
                    logs = []
                    main_mod.preview_mapping(sheet_name, frame, schema_section, logs)
                    entry = logs[-1] if logs else {
                        "mapping": {},
                        "confidence": {},
                        "unmapped": [str(col) for col in frame.columns],
                        "source": "unknown",
                    }
                    return entry.get("mapping") or {}, entry.get("source") or "unknown", entry

                local_ctkm, ctkm_runtime_source, ctkm_preview = resolve_runtime(
                    primary_name, primary_sheet.df, main_mod.SCHEMA["fact_fields"],
                    local_ctkm, sources.get("ctkm"),
                )
                local_pog, pog_runtime_source, pog_preview = resolve_runtime(
                    selected_pog_sheet, pog_sheet.df, main_mod.SCHEMA["pog_fields"],
                    local_pog, sources.get("pog"),
                )

                if (
                    core_module._mapping_needs_confirmation(
                        ctkm_preview, main_mod.SCHEMA["fact_fields"]
                    )
                    or core_module._mapping_needs_confirmation(
                        pog_preview, main_mod.SCHEMA["pog_fields"]
                    )
                ):
                    current["mapping_confirmation"] = {
                        "ctkm": ctkm_preview,
                        "pog": pog_preview,
                        "ctkm_columns": list(primary_sheet.df.columns),
                        "pog_columns": list(pog_sheet.df.columns),
                        "reason": "Mapping bắt buộc còn thiếu hoặc độ tin cậy chưa đủ.",
                    }
                    current["resume_work"] = work
                    current["status"] = "awaiting_mapping_confirmation"
                    raise core_module.MappingConfirmationRequired()

                sources["ctkm"] = ctkm_runtime_source
                sources["pog"] = pog_runtime_source
                current["mapping_sources"] = sources

                current.update(progress=45, message="Đang ghép dữ liệu và xuất Excel")
                result = core_module.run_pipeline(
                    ctkm_filepath=str(ctkm_path),
                    pog_filepath=str(pog_path),
                    target_month=month,
                    output_path=str(output_path),
                    fail_on_month_mismatch=strict_month,
                    ctkm_sheet_name=primary_name,
                    ctkm_mapping_override=local_ctkm,
                    pog_mapping_override=local_pog,
                    selected_output_columns=output_columns,
                    pog_sheet_name=selected_pog_sheet,
                    clearance_filepath=(str(clearance_path) if clearance_content is not None else None),
                    clearance_sheet_name=selected_clearance_sheet,
                    clearance_mapping_override=clearance_map,
                    business_date=business_date_value,
                    ctkm_mapping_source=ctkm_runtime_source,
                    pog_mapping_source=pog_runtime_source,
                    clearance_mapping_source=(
                        sources.get("clearance") if clearance_map else None
                    ),
                )
                return result.summary, result.warnings
            finally:
                if current.get("status") != "awaiting_mapping_confirmation":
                    ctkm_path.unlink(missing_ok=True)
                    pog_path.unlink(missing_ok=True)
                    clearance_path.unlink(missing_ok=True)

        core_module._submit_job(job_id, "ctkm", work)
        return core_module._job_public(job)

    async def preview_mapping_job(
        ctkm_file: UploadFile = File(...),
        pog_file: UploadFile = File(...),
        ctkm_sheet_name: str = Form(...),
        pog_sheet_name: Optional[str] = Form(None),
        manual_only: bool = Form(False),
        _admin: str = Depends(core_module.require_admin),
    ):
        if not ctkm_file.filename or not ctkm_file.filename.lower().endswith(".xlsx"):
            raise HTTPException(status_code=422, detail="ctkm_file phải là file .xlsx")
        if not pog_file.filename or not pog_file.filename.lower().endswith(".xlsx"):
            raise HTTPException(status_code=422, detail="pog_file phải là file .xlsx")
        if not ctkm_sheet_name or not ctkm_sheet_name.strip():
            raise HTTPException(status_code=422, detail="Hãy chọn sheet CTKM trước khi xem mapping")

        ctkm_content, pog_content = await asyncio.gather(
            core_module._read_upload_limited(ctkm_file, core_module._MAX_PIPELINE_BYTES, "File CTKM"),
            core_module._read_upload_limited(pog_file, core_module._MAX_PIPELINE_BYTES, "File POG"),
        )
        job_dir = core_module._TMP_DIR / f"preview_{uuid.uuid4().hex[:8]}"
        job_dir.mkdir(parents=True, exist_ok=True)
        ctkm_path, pog_path = job_dir / "ctkm.xlsx", job_dir / "pog.xlsx"
        ctkm_path.write_bytes(ctkm_content)
        pog_path.write_bytes(pog_content)
        try:
            selected_pog = pog_sheet_name.strip() if pog_sheet_name and pog_sheet_name.strip() else None
            if not selected_pog:
                pog_sheets = await asyncio.to_thread(main_mod.L.inspect_workbook_sheets, str(pog_path))
                if len(pog_sheets) != 1:
                    raise HTTPException(status_code=422, detail="Hãy chọn rõ sheet POG trước khi xem mapping")
                selected_pog = pog_sheets[0]
            wb_ctkm, wb_pog = await asyncio.gather(
                asyncio.to_thread(
                    main_mod.L.load_workbook_raw, str(ctkm_path), is_pog_file=False,
                    selected_sheet_names=[ctkm_sheet_name],
                ),
                asyncio.to_thread(
                    main_mod.L.load_workbook_raw, str(pog_path), is_pog_file=True,
                    selected_sheet_names=[selected_pog],
                ),
            )
            if ctkm_sheet_name not in wb_ctkm.sheets:
                raise HTTPException(status_code=422, detail=f"Không tìm thấy sheet CTKM '{ctkm_sheet_name}'")
            if selected_pog not in wb_pog.sheets:
                raise HTTPException(status_code=422, detail=f"Không tìm thấy sheet POG '{selected_pog}'")
            ctkm_sheet = wb_ctkm.sheets[ctkm_sheet_name]
            pog_sheet = wb_pog.sheets[selected_pog]
            stored = core_module._get_saved_preset(
                list(ctkm_sheet.df.columns), list(pog_sheet.df.columns)
            )
            warnings: list[str] = []
            usable_preset: dict = {}

            def preview_one(sheet_name, df, schema_section, preset_mapping, kind):
                if preset_mapping:
                    try:
                        mapping = validate_manual_mapping(preset_mapping, df, schema_section)
                        return {
                            "mapping": mapping,
                            "confidence": {source: 1.0 for source in mapping},
                            "unmapped": [str(col) for col in df.columns if col not in mapping],
                            "source": "saved-preset",
                        }, mapping
                    except ValueError as exc:
                        warnings.append(f"Preset {sheet_name} không còn hợp lệ: {exc}")

                inferred, source = _mapping_or_none(
                    main_mod, df, schema_section, None, None, kind=kind
                )
                if inferred is not None:
                    return {
                        "mapping": inferred,
                        "confidence": {key: 1.0 for key in inferred},
                        "unmapped": [str(col) for col in df.columns if col not in inferred],
                        "source": source,
                    }, None
                columns = [str(col) for col in df.columns]
                if manual_only:
                    return {
                        "mapping": {}, "confidence": {}, "unmapped": columns, "source": "manual"
                    }, None
                try:
                    core_module._enforce_gemini_cooldown()
                    logs = []
                    main_mod.preview_mapping(sheet_name, df, schema_section, logs)
                    return (logs[-1] if logs else {
                        "mapping": {}, "confidence": {}, "unmapped": columns, "source": "manual-fallback"
                    }), None
                except Exception as exc:
                    warnings.append(f"{sheet_name}: {type(exc).__name__}: {exc}")
                    return {
                        "mapping": {}, "confidence": {}, "unmapped": columns,
                        "source": "manual-fallback",
                    }, None

            ctkm_result, valid_ctkm_preset = preview_one(
                ctkm_sheet_name, ctkm_sheet.df, main_mod.SCHEMA["fact_fields"],
                stored.get("ctkm_mapping"), "fact",
            )
            pog_result, valid_pog_preset = preview_one(
                selected_pog, pog_sheet.df, main_mod.SCHEMA["pog_fields"],
                stored.get("pog_mapping"), "pog",
            )
            if valid_ctkm_preset is not None:
                usable_preset["ctkm_mapping"] = valid_ctkm_preset
            if valid_pog_preset is not None:
                usable_preset["pog_mapping"] = valid_pog_preset
            if stored.get("output_columns") is not None:
                try:
                    usable_preset["output_columns"] = validate_output_columns(
                        stored.get("output_columns"), main_mod.SCHEMA
                    )
                except ValueError as exc:
                    warnings.append(f"Preset output không còn hợp lệ: {exc}")

            return {
                "ctkm_sheet_name": ctkm_sheet_name,
                "pog_sheet_name": selected_pog,
                "ctkm_mapping": ctkm_result,
                "pog_mapping": pog_result,
                "mapping_warnings": warnings,
                "stored_preset": usable_preset,
                "ctkm_preview": {"columns": list(ctkm_sheet.df.columns)},
                "pog_preview": {
                    "columns": list(pog_sheet.df.columns),
                    "snapshot_month": wb_pog.pog_snapshot_month,
                },
            }
        finally:
            _cleanup_dir(job_dir)

    def save_preset(
        ctkm_columns: str = Form(...),
        pog_columns: str = Form(...),
        ctkm_mapping: str = Form(...),
        pog_mapping: str = Form(...),
        selected_output_columns: Optional[str] = Form(None),
        _admin: str = Depends(core_module.require_admin),
    ):
        try:
            parsed_ctkm_columns = json.loads(ctkm_columns)
            parsed_pog_columns = json.loads(pog_columns)
            parsed_ctkm_mapping = json.loads(ctkm_mapping)
            parsed_pog_mapping = json.loads(pog_mapping)
            parsed_output = json.loads(selected_output_columns) if selected_output_columns else None
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"Preset JSON không hợp lệ: {exc.msg}") from exc
        if not isinstance(parsed_ctkm_columns, list) or not isinstance(parsed_pog_columns, list):
            raise HTTPException(status_code=422, detail="Danh sách cột preset phải là JSON array")
        try:
            checked_ctkm = validate_manual_mapping(
                parsed_ctkm_mapping, pd.DataFrame(columns=parsed_ctkm_columns),
                main_mod.SCHEMA["fact_fields"],
            )
            checked_pog = validate_manual_mapping(
                parsed_pog_mapping, pd.DataFrame(columns=parsed_pog_columns),
                main_mod.SCHEMA["pog_fields"],
            )
            checked_output = validate_output_columns(parsed_output, main_mod.SCHEMA)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        core_module._store_preset(
            parsed_ctkm_columns, parsed_pog_columns,
            ctkm_mapping=checked_ctkm, pog_mapping=checked_pog,
            output_columns=checked_output,
        )
        return {
            "saved": True,
            "key": core_module._preset_key(parsed_ctkm_columns, parsed_pog_columns),
        }

    _replace_route(core_module, "/api/jobs/ctkm", "POST", enqueue_ctkm)
    _replace_route(core_module, "/api/preview-mapping", "POST", preview_mapping_job)
    _replace_route(core_module, "/api/presets", "POST", save_preset)
    core_module.enqueue_ctkm = enqueue_ctkm
    core_module.preview_mapping_job = preview_mapping_job
    core_module.save_preset = save_preset
    core_module.app.state.input_contract_v1 = True
