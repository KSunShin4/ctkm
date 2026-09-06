# -*- coding: utf-8 -*-
"""FastAPI entrypoint with exact, atomic workflow preset storage.

The existing API implementation is preserved byte-for-byte in ``main_api_core.py``.
Only preset identity/storage and compatibility contracts are hardened here, then
this module resolves to the core module so monkeypatching and FastAPI endpoint
globals keep normal semantics.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

from backend.contract_suite import install_contract_suite
from backend import tag_audit_contract as _tag_audit_contract
from backend import tag_audit_local_ocr_contract as _tag_audit_local_ocr_contract
from backend.tag_audit_contract import install_tag_audit_contract
from backend.tag_audit_local_ocr_contract import install_tag_audit_local_ocr_contract
from backend.tag_audit_itemid_contract import install_tag_audit_itemid_contract
from backend.tag_audit_progress_contract import install_tag_audit_progress_contract
from backend.tag_audit_promotion_disambiguation_contract import install_tag_audit_promotion_disambiguation_contract
from backend.tag_audit_temporal_hint_contract import install_tag_audit_temporal_hint_contract
from backend.tag_audit_business_date_contract import install_tag_audit_business_date_contract

_CORE_NAME = "backend.main_api_core"
_CORE_PATH = Path(__file__).with_name("main_api_core.py")

if _CORE_NAME in sys.modules:
    _core = sys.modules[_CORE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(_CORE_NAME, _CORE_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Không nạp được API core: {_CORE_PATH}")
    _core = importlib.util.module_from_spec(_spec)
    sys.modules[_CORE_NAME] = _core
    _spec.loader.exec_module(_core)

_PRESET_LOCK = threading.RLock()
_PRESET_KEY_PREFIX = "v2:"


def _preset_key(ctkm_columns, pog_columns) -> str:
    """Key workflow presets by exact source headers, in a new safe namespace."""
    identity = {
        "version": 2,
        "ctkm_columns": sorted(str(column) for column in ctkm_columns),
        "pog_columns": sorted(str(column) for column in pog_columns),
    }
    encoded = json.dumps(
        identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _PRESET_KEY_PREFIX + hashlib.sha256(encoded).hexdigest()


def _load_presets_unlocked() -> dict:
    path = _core._PRESETS_PATH
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_presets_unlocked(presets: dict) -> None:
    path = _core._PRESETS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(presets, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _load_presets() -> dict:
    with _PRESET_LOCK:
        return _load_presets_unlocked()


def _save_presets(presets: dict) -> None:
    with _PRESET_LOCK:
        _save_presets_unlocked(presets)


def _get_saved_preset(ctkm_columns, pog_columns) -> dict:
    key = _preset_key(ctkm_columns, pog_columns)
    with _PRESET_LOCK:
        value = _load_presets_unlocked().get(key, {})
        return dict(value) if isinstance(value, dict) else {}


def _store_preset(
    ctkm_columns,
    pog_columns,
    ctkm_mapping=None,
    pog_mapping=None,
    output_columns=None,
) -> None:
    key = _preset_key(ctkm_columns, pog_columns)
    with _PRESET_LOCK:
        presets = _load_presets_unlocked()
        existing = presets.get(key, {})
        current = dict(existing) if isinstance(existing, dict) else {}
        if ctkm_mapping is not None:
            current["ctkm_mapping"] = ctkm_mapping
        if pog_mapping is not None:
            current["pog_mapping"] = pog_mapping
        if output_columns is not None:
            current["output_columns"] = output_columns
        current["preset_version"] = 2
        current["ctkm_columns"] = [str(column) for column in ctkm_columns]
        current["pog_columns"] = [str(column) for column in pog_columns]
        current["updated_at"] = _core.datetime.now().isoformat()
        presets[key] = current
        _save_presets_unlocked(presets)


def _list_presets() -> list[dict]:
    with _PRESET_LOCK:
        presets = _load_presets_unlocked()
    results = []
    for key, raw_value in presets.items():
        value = raw_value if isinstance(raw_value, dict) else {}
        legacy = not str(key).startswith(_PRESET_KEY_PREFIX)
        if legacy:
            ctkm_sig, pog_sig = key.split("::", 1) if "::" in key else (key, "")
        else:
            ctkm_sig = " | ".join(value.get("ctkm_columns") or [])
            pog_sig = " | ".join(value.get("pog_columns") or [])
        results.append({
            "key": key,
            "ctkm_signature": ctkm_sig,
            "pog_signature": pog_sig,
            "updated_at": value.get("updated_at"),
            "has_ctkm_mapping": bool(value.get("ctkm_mapping")),
            "has_pog_mapping": bool(value.get("pog_mapping")),
            "has_output_columns": bool(value.get("output_columns")),
            "preset_version": value.get("preset_version", 1 if legacy else 2),
            "legacy": legacy,
        })
    return sorted(results, key=lambda item: item.get("updated_at") or "", reverse=True)


def _delete_preset(key: str) -> bool:
    with _PRESET_LOCK:
        presets = _load_presets_unlocked()
        if key not in presets:
            return False
        del presets[key]
        _save_presets_unlocked(presets)
        return True


for _name, _value in {
    "_preset_key": _preset_key,
    "_load_presets": _load_presets,
    "_save_presets": _save_presets,
    "_get_saved_preset": _get_saved_preset,
    "_store_preset": _store_preset,
    "_list_presets": _list_presets,
    "_delete_preset": _delete_preset,
}.items():
    setattr(_core, _name, _value)

# All compatibility/hardening layers are installed and verified by one ordered
# suite. The suite also binds the shared mapping validator before routes capture it.
install_contract_suite(_core)

# Production slim workbooks use explicit business-facing channel labels. Accept
# those exact headers in addition to the earlier short aliases while keeping the
# source cell values untouched. These fields are backend disambiguation context;
# they are not OCR targets and are never inferred from one another.
_tag_audit_contract._DISPLAY_TO_KEY.update({
    "Phạm vi áp dụng (KEY Channel)": "key_channel",
    "Kênh chương trình (Channel)": "channel",
})
_tag_audit_contract._CANONICAL_KEYS.update({"key_channel", "channel"})

# Production scanner pipeline: local RapidOCR is the primary text reader, then
# ITEMID hardening treats the printed Pxxxxx as the primary identity signal.
# Gemini remains an optional fallback inside the local OCR contract only.
install_tag_audit_local_ocr_contract(_tag_audit_contract)
install_tag_audit_itemid_contract(_tag_audit_contract)
install_tag_audit_promotion_disambiguation_contract(_tag_audit_contract)
install_tag_audit_temporal_hint_contract(_tag_audit_contract, _tag_audit_local_ocr_contract)
install_tag_audit_business_date_contract(_tag_audit_contract)

# In the production Docker image frontend/dist exists before this module imports,
# so main_api_core has already mounted StaticFiles at "/". Starlette normalizes a
# root Mount's ``path`` to the empty string. The original tag-audit helper looked
# only for path == "/", failed to see the root mount, and appended API routes after
# StaticFiles. POST /api/tag-audit/context was therefore intercepted by StaticFiles
# and returned 405 Method Not Allowed. Keep all tag-audit API routes ahead of the
# root frontend mount, regardless of that normalization detail.
def _insert_tag_audit_route_before_frontend(
    core_module, path: str, endpoint, methods: list[str], **kwargs
):
    core_module.app.add_api_route(path, endpoint, methods=methods, **kwargs)
    routes = core_module.app.router.routes
    new_route = next(
        route for route in reversed(routes)
        if getattr(route, "path", None) == path
        and set(methods).issubset(getattr(route, "methods", set()) or set())
    )
    routes.remove(new_route)
    mount_index = next(
        (
            index for index, route in enumerate(routes)
            if route.__class__.__name__ == "Mount"
            and (
                getattr(route, "name", None) == "frontend"
                or getattr(route, "path", None) in {"", "/"}
            )
        ),
        len(routes),
    )
    routes.insert(mount_index, new_route)


_tag_audit_contract._insert_api_route_before_frontend = _insert_tag_audit_route_before_frontend
setattr(_core, "_insert_tag_audit_route_before_frontend", _insert_tag_audit_route_before_frontend)

# Progress is a store-facing checklist only: count current Gắn-tem promotions,
# expose stable check keys, and let the browser persist completed checks locally.
# It wraps the already-hardened comparator before scanner routes are added.
install_tag_audit_progress_contract(_tag_audit_contract, _core)

# The tag-audit feature is additive and deliberately installed after the verified
# legacy suite so it cannot mutate existing CTKM/Tem-R route contracts.
install_tag_audit_contract(_core)

# The root StaticFiles mount in main_api_core is intentionally last among core
# routes, but Starlette StaticFiles(html=True) does not provide a generic SPA
# fallback. Intercept only the scanner browser entrypoint before routing. This is
# independent of route-list ordering and therefore remains reliable in the
# production Docker image where the root static mount already exists at import.
async def _scan_tem_spa_entry(request, call_next):
    if request.method == "GET" and request.url.path.rstrip("/") == "/scan-tem":
        index_path = _core._FRONTEND_DIST / "index.html"
        if index_path.is_file():
            return _core.FileResponse(index_path)
    return await call_next(request)


setattr(_core, "_scan_tem_spa_entry", _scan_tem_spa_entry)
if not getattr(_core.app.state, "scan_tem_spa_middleware_v1", False):
    _core.app.middleware("http")(_scan_tem_spa_entry)
    _core.app.state.scan_tem_spa_middleware_v1 = True

# Make imports receive the actual core module. This preserves attribute mutation
# semantics used by tests and by runtime monkeypatch/configuration code.
sys.modules[__name__] = _core

if __name__ == "__main__":
    _core.uvicorn.run("backend.main_api:app", host="0.0.0.0", port=8000, reload=True)
