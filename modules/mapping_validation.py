# -*- coding: utf-8 -*-
"""Shared canonical mapping validation for API and direct pipeline entrypoints."""
from __future__ import annotations

from collections import Counter

import pandas as pd


MULTI_SOURCE_CANONICAL_FIELDS = {"campaign_detail", "promo_price"}


def _required_fields(schema_section: dict) -> set[str]:
    return {
        name for name, meta in schema_section.items()
        if meta.get("required", False) and not meta.get("auto_filled", False)
    }


def validate_manual_mapping(mapping, df: pd.DataFrame, schema_section: dict) -> dict:
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

    counts = Counter(cleaned.values())
    duplicate_targets = sorted(
        target for target, count in counts.items()
        if count > 1 and target not in MULTI_SOURCE_CANONICAL_FIELDS
    )
    if duplicate_targets:
        raise ValueError(
            "Mỗi canonical field chỉ được map từ một cột nguồn, trừ field multi-promo "
            "campaign_detail/promo_price. Bị trùng: " + ", ".join(duplicate_targets)
        )

    missing_required = sorted(_required_fields(schema_section) - set(cleaned.values()))
    if missing_required:
        raise ValueError(
            "Mapping thiếu trường bắt buộc: " + ", ".join(missing_required)
        )
    return cleaned
