# -*- coding: utf-8 -*-
"""Module 4: Mapping Cache — luu/tra mapping theo hash cua tap ten cot."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Optional

_CACHE_PATH = Path(__file__).resolve().parent.parent / "logs" / "mapping_cache.json"
_CACHE_LOCK = threading.RLock()


_CACHE_CONTRACT_VERSION = 3


def _prompt_samples(series, n: int) -> list[str]:
    # Mirror column_mapper._sample_values exactly: head(N) is taken before
    # blank/duplicate filtering and each visible value is truncated to 120 chars.
    values = []
    for value in series.dropna().head(n):
        text = str(value).strip()
        if text and text not in values:
            values.append(text[:120])
    return values


def compute_dataframe_evidence(df, sample_rows_per_column=8) -> dict:
    """Canonicalize exactly the dataframe evidence that influences Gemini prompt."""
    columns = []
    for column in df.columns:
        series = df[column]
        columns.append({
            "name": str(column),
            "dtype": str(series.dtype),
            "null_ratio": round(float(series.isna().mean()), 12),
            "samples": _prompt_samples(series, int(sample_rows_per_column)),
        })
    return {"columns": columns}


def compute_signature(
    columns,
    schema_section=None,
    prompt_version="column-mapping-v2",
    *,
    dataframe=None,
    sheet_name=None,
    sample_rows_per_column=8,
):
    """Build a versioned Gemini-cache key from the actual prompt context.

    Presets are user-confirmed and may survive harmless column reordering. Gemini
    cache is different: reuse is allowed only when exact header order, sheet name,
    canonical schema, prompt version and the value evidence seen by the mapper all
    match. Legacy headers-only cache entries therefore cannot collide with v3.
    """
    ordered_columns = [str(column) for column in columns]
    evidence = (
        compute_dataframe_evidence(dataframe, sample_rows_per_column)
        if dataframe is not None else None
    )
    identity = {
        "cache_contract_version": _CACHE_CONTRACT_VERSION,
        "columns": ordered_columns,
        "sheet_name": "" if sheet_name is None else str(sheet_name),
        "schema": schema_section or {},
        "prompt_version": str(prompt_version),
        "sample_rows_per_column": int(sample_rows_per_column),
        "evidence": evidence,
    }
    joined = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(joined.encode()).hexdigest()


def _valid_cached_payload(value) -> bool:
    if not isinstance(value, dict):
        return False
    mapping = value.get("mapping")
    confidence = value.get("confidence")
    unmapped = value.get("unmapped")
    if not isinstance(mapping, dict) or not isinstance(confidence, dict):
        return False
    if unmapped is not None and not isinstance(unmapped, list):
        return False
    for source, target in mapping.items():
        if not isinstance(source, str) or not isinstance(target, str):
            return False
    for source, score in confidence.items():
        if not isinstance(source, str):
            return False
        try:
            numeric = float(score)
        except (TypeError, ValueError):
            return False
        if not 0.0 <= numeric <= 1.0:
            return False
    return True


def _load_unlocked():
    if not _CACHE_PATH.exists():
        return {}
    try:
        with open(_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _save_unlocked(cache):
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{_CACHE_PATH.name}.", suffix=".tmp", dir=str(_CACHE_PATH.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, _CACHE_PATH)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _load():
    with _CACHE_LOCK:
        return _load_unlocked()


def _save(cache):
    with _CACHE_LOCK:
        _save_unlocked(cache)


def get_cached_mapping(
    columns,
    schema_section=None,
    prompt_version="column-mapping-v2",
    *,
    dataframe=None,
    sheet_name=None,
    sample_rows_per_column=8,
) -> Optional[dict]:
    signature = compute_signature(
        columns,
        schema_section,
        prompt_version,
        dataframe=dataframe,
        sheet_name=sheet_name,
        sample_rows_per_column=sample_rows_per_column,
    )
    with _CACHE_LOCK:
        cache = _load_unlocked()
        value = cache.get(signature)
        if not _valid_cached_payload(value):
            if signature in cache:
                del cache[signature]
                _save_unlocked(cache)
            return None
        # Do not hand callers a mutable reference to the loaded cache payload.
        return json.loads(json.dumps(value, ensure_ascii=False))


def save_mapping(
    columns,
    result_dict,
    schema_section=None,
    prompt_version="column-mapping-v2",
    *,
    dataframe=None,
    sheet_name=None,
    sample_rows_per_column=8,
):
    if not _valid_cached_payload(result_dict):
        raise ValueError("Mapping cache payload không hợp lệ.")
    signature = compute_signature(
        columns,
        schema_section,
        prompt_version,
        dataframe=dataframe,
        sheet_name=sheet_name,
        sample_rows_per_column=sample_rows_per_column,
    )
    with _CACHE_LOCK:
        cache = _load_unlocked()
        cache[signature] = result_dict
        _save_unlocked(cache)


def mapping_result_to_dict(result) -> dict:
    d = asdict(result)
    d["source"] = "cache"
    return d


def mapping_result_to_dict_safe(result) -> dict:
    """Phien ban an toan hon: ho tro ca dataclass lan object thuong (dung khi mock test)."""
    try:
        d = asdict(result)
    except TypeError:
        d = {
            k: getattr(result, k, None)
            for k in [
                "sheet_name", "mapping", "confidence", "unmapped",
                "low_confidence_fields", "raw_response", "source",
            ]
        }
    d["source"] = "cache"
    return d
