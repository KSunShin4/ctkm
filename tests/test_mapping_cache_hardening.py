import importlib.util
from pathlib import Path
import sys

import pandas as pd


def _cache_module():
    path = Path(__file__).resolve().parents[1] / "modules" / "4_mapping_cache.py"
    spec = importlib.util.spec_from_file_location("mapping_cache_hardening_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cache_signature_distinguishes_exact_header_spelling_and_spacing():
    cache = _cache_module()
    schema = {"item_id": {"type": "string"}}

    assert cache.compute_signature(["ITEMID"], schema, "v1") != cache.compute_signature(
        ["itemid"], schema, "v1"
    )
    assert cache.compute_signature(["Channel"], schema, "v1") != cache.compute_signature(
        [" Channel "], schema, "v1"
    )


def test_cache_save_is_atomic_and_round_trips(tmp_path, monkeypatch):
    cache = _cache_module()
    monkeypatch.setattr(cache, "_CACHE_PATH", tmp_path / "mapping_cache.json")
    result = {
        "mapping": {"ITEMID": "item_id"},
        "confidence": {"ITEMID": 0.96},
        "unmapped": [],
        "source": "gemini",
    }

    frame = pd.DataFrame({"ITEMID": ["P1001", "P1002", "P1003"]})
    cache.save_mapping(
        ["ITEMID"], result, {"item_id": {"type": "string"}}, "v1",
        dataframe=frame, sheet_name="Export", sample_rows_per_column=3,
    )
    loaded = cache.get_cached_mapping(
        ["ITEMID"], {"item_id": {"type": "string"}}, "v1",
        dataframe=frame, sheet_name="Export", sample_rows_per_column=3,
    )

    assert loaded == result
    assert not list(tmp_path.glob("*.tmp"))



def test_cache_signature_includes_value_evidence_sheet_and_column_order():
    cache = _cache_module()
    schema = {"item_id": {"type": "string"}}
    first = pd.DataFrame({
        "A": ["P1001", "P1002", "P1003"],
        "B": ["x", "y", "z"],
    })
    changed_values = pd.DataFrame({
        "A": ["SGPMC1885", "SGPMC1885", "SGPMC1885"],
        "B": ["x", "y", "z"],
    })
    reordered = first[["B", "A"]]

    base = cache.compute_signature(
        list(first.columns), schema, "v2",
        dataframe=first, sheet_name="Sheet1", sample_rows_per_column=3,
    )
    assert base != cache.compute_signature(
        list(changed_values.columns), schema, "v2",
        dataframe=changed_values, sheet_name="Sheet1", sample_rows_per_column=3,
    )
    assert base != cache.compute_signature(
        list(first.columns), schema, "v2",
        dataframe=first, sheet_name="Other sheet", sample_rows_per_column=3,
    )
    assert base != cache.compute_signature(
        list(reordered.columns), schema, "v2",
        dataframe=reordered, sheet_name="Sheet1", sample_rows_per_column=3,
    )


def test_headers_only_cache_entry_cannot_hit_evidence_aware_lookup(tmp_path, monkeypatch):
    cache = _cache_module()
    monkeypatch.setattr(cache, "_CACHE_PATH", tmp_path / "mapping_cache.json")
    schema = {"item_id": {"type": "string"}}
    result = {
        "mapping": {"Mystery": "item_id"},
        "confidence": {"Mystery": 0.95},
        "unmapped": [],
        "source": "cache",
    }
    frame = pd.DataFrame({"Mystery": ["P1001", "P1002", "P1003"]})

    cache.save_mapping(["Mystery"], result, schema, "v2")
    assert cache.get_cached_mapping(
        ["Mystery"], schema, "v2",
        dataframe=frame, sheet_name="Sheet1", sample_rows_per_column=3,
    ) is None


def test_same_headers_with_changed_samples_do_not_reuse_gemini_cache(tmp_path, monkeypatch):
    cache = _cache_module()
    monkeypatch.setattr(cache, "_CACHE_PATH", tmp_path / "mapping_cache.json")
    schema = {
        "item_id": {"type": "string", "required": True},
        "store_id": {"type": "string", "required": True},
    }
    old_frame = pd.DataFrame({
        "Mystery A": ["P1001", "P1002", "P1003"],
        "Mystery B": ["SGPMC1885", "SGPMC1885", "SGPMC1885"],
    })
    new_frame = pd.DataFrame({
        "Mystery A": ["SGPMC1885", "SGPMC1885", "SGPMC1885"],
        "Mystery B": ["P1001", "P1002", "P1003"],
    })
    result = {
        "mapping": {"Mystery A": "item_id", "Mystery B": "store_id"},
        "confidence": {"Mystery A": 0.97, "Mystery B": 0.98},
        "unmapped": [],
        "source": "cache",
    }

    cache.save_mapping(
        list(old_frame.columns), result, schema, "v2",
        dataframe=old_frame, sheet_name="POG", sample_rows_per_column=3,
    )

    assert cache.get_cached_mapping(
        list(old_frame.columns), schema, "v2",
        dataframe=old_frame, sheet_name="POG", sample_rows_per_column=3,
    ) == result
    assert cache.get_cached_mapping(
        list(new_frame.columns), schema, "v2",
        dataframe=new_frame, sheet_name="POG", sample_rows_per_column=3,
    ) is None


def test_corrupt_or_out_of_range_confidence_cache_is_evicted(tmp_path, monkeypatch):
    cache = _cache_module()
    monkeypatch.setattr(cache, "_CACHE_PATH", tmp_path / "mapping_cache.json")
    schema = {"item_id": {"type": "string"}}
    frame = pd.DataFrame({"ITEMID": ["P1001", "P1002", "P1003"]})
    signature = cache.compute_signature(
        ["ITEMID"], schema, "v2",
        dataframe=frame, sheet_name="Export", sample_rows_per_column=3,
    )
    cache._save({
        signature: {
            "mapping": {"ITEMID": "item_id"},
            "confidence": {"ITEMID": 7.0},
            "unmapped": [],
            "source": "cache",
        }
    })

    assert cache.get_cached_mapping(
        ["ITEMID"], schema, "v2",
        dataframe=frame, sheet_name="Export", sample_rows_per_column=3,
    ) is None
    assert signature not in cache._load()
