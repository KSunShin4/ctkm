import importlib.util
from pathlib import Path
import sys


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
    result = {"mapping": {"ITEMID": "item_id"}, "source": "gemini"}

    cache.save_mapping(["ITEMID"], result, {"item_id": {"type": "string"}}, "v1")
    loaded = cache.get_cached_mapping(
        ["ITEMID"], {"item_id": {"type": "string"}}, "v1"
    )

    assert loaded == result
    assert not list(tmp_path.glob("*.tmp"))
