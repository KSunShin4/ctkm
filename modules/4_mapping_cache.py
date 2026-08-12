# -*- coding: utf-8 -*-
"""Module 4: Mapping Cache — luu/tra mapping theo hash cua tap ten cot."""
from __future__ import annotations
import hashlib, json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

_CACHE_PATH = Path(__file__).resolve().parent.parent / "logs" / "mapping_cache.json"

def compute_signature(columns, schema_section=None, prompt_version="column-mapping-v2"):
    normalized_schema = schema_section or {}
    identity = {
        "columns": sorted(str(c).strip().lower() for c in columns),
        "schema": normalized_schema,
        "prompt_version": prompt_version,
    }
    joined = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(joined.encode()).hexdigest()

def _load():
    if not _CACHE_PATH.exists(): return {}
    try:
        with open(_CACHE_PATH,"r",encoding="utf-8") as f: return json.load(f)
    except: return {}

def _save(cache):
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_CACHE_PATH,"w",encoding="utf-8") as f: json.dump(cache, f, ensure_ascii=False, indent=2)

def get_cached_mapping(columns, schema_section=None, prompt_version="column-mapping-v2") -> Optional[dict]:
    return _load().get(compute_signature(columns, schema_section, prompt_version))

def save_mapping(columns, result_dict, schema_section=None, prompt_version="column-mapping-v2"):
    cache = _load()
    cache[compute_signature(columns, schema_section, prompt_version)] = result_dict
    _save(cache)

def mapping_result_to_dict(result) -> dict:
    d = asdict(result)
    d["source"] = "cache"
    return d

def mapping_result_to_dict_safe(result) -> dict:
    """Phien ban an toan hon: ho tro ca dataclass lan object thuong (dung khi mock test)."""
    try:
        from dataclasses import asdict
        d = asdict(result)
    except TypeError:
        d = {k: getattr(result, k, None) for k in
             ["sheet_name","mapping","confidence","unmapped","low_confidence_fields","raw_response","source"]}
    d["source"] = "cache"
    return d
