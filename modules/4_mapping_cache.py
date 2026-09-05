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


def compute_signature(columns, schema_section=None, prompt_version="column-mapping-v2"):
    """Build a cache key from the exact source headers seen by the loader.

    Mapping values are keyed by exact DataFrame column names. Lower-casing the
    signature can make two workbooks share a cache entry even though the stored
    mapping keys no longer exist in the second DataFrame, which silently turns
    mapped fields into ``extra__...`` columns. Keep the header spelling/case exact.
    """
    normalized_schema = schema_section or {}
    identity = {
        "columns": sorted(str(c) for c in columns),
        "schema": normalized_schema,
        "prompt_version": prompt_version,
    }
    joined = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(joined.encode()).hexdigest()


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


def get_cached_mapping(columns, schema_section=None, prompt_version="column-mapping-v2") -> Optional[dict]:
    signature = compute_signature(columns, schema_section, prompt_version)
    with _CACHE_LOCK:
        return _load_unlocked().get(signature)


def save_mapping(columns, result_dict, schema_section=None, prompt_version="column-mapping-v2"):
    signature = compute_signature(columns, schema_section, prompt_version)
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
