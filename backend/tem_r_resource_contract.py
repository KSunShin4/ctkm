# -*- coding: utf-8 -*-
"""Bound Tem R workbook expansion using the project's existing XLSX safety cap."""
from __future__ import annotations

from pathlib import Path
import zipfile


# Expiration already uses 300 MiB as the safe uncompressed XLSX ceiling. Reuse
# the same project policy instead of inventing a separate Tem R limit.
DEFAULT_MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024


def validate_tem_r_archive(
    path: str | Path,
    *,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> Path:
    source = Path(path)
    try:
        with zipfile.ZipFile(source, "r") as archive:
            total = sum(info.file_size for info in archive.infolist())
            if total > int(max_uncompressed_bytes):
                raise ValueError(
                    "File Tem R giải nén quá lớn để xử lý an toàn. "
                    "Hãy xuất lại file với đúng vùng dữ liệu cần phân bổ."
                )
    except zipfile.BadZipFile as exc:
        raise ValueError("File Tem R có cấu trúc ZIP/XLSX bị hỏng.") from exc
    return source


def install_tem_r_resource_contract(core_module) -> None:
    if getattr(core_module.app.state, "tem_r_resource_contract_v1", False):
        return

    tem_r_mod = core_module._tem_r_mod
    original_inspect = tem_r_mod.inspect_tem_r_workbook
    original_create = tem_r_mod.create_tem_r_workbook

    def bounded_inspect(input_path):
        validate_tem_r_archive(input_path)
        return original_inspect(input_path)

    def bounded_create(input_path, output_path, **kwargs):
        validate_tem_r_archive(input_path)
        return original_create(input_path, output_path, **kwargs)

    tem_r_mod.inspect_tem_r_workbook = bounded_inspect
    tem_r_mod.create_tem_r_workbook = bounded_create
    core_module.app.state.tem_r_resource_contract_v1 = True
