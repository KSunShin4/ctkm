# -*- coding: utf-8 -*-
"""Daily, device-local checklist contract for the shelf-tag scanner.

The backend owns deterministic checklist identity. Progress persistence stays in
the browser. The checklist is computed from the scanner's current-date derived
action set when that contract is installed, so a monthly workbook can be reused
without carrying yesterday's Gắn/Tháo/Chờ denominator forward.
"""
from __future__ import annotations

from hashlib import sha256
import json

from fastapi import Depends


_PROGRESS_VERSION = "tag-audit-progress-v1"
_EXCLUDED_PROGRESS_VERDICTS = {
    "not_found",
    "review_identity",
    "review_ambiguous",
    "review_itemid_ambiguous",
    "review_business_date",
}


def _identity_payload(tag_audit_module, row: dict) -> dict:
    """Return a stable promotion-level identity without mutating source values."""
    return {
        "item_id": tag_audit_module._norm_item(row.get("item_id")),
        "key_channel": str(row.get("key_channel") or ""),
        "channel": str(row.get("channel") or ""),
        "campaign_name": str(row.get("campaign_name") or ""),
        "campaign_detail": str(row.get("campaign_detail") or ""),
        "promo_from": tag_audit_module._parse_iso_date(row.get("promo_from")),
        "promo_to": tag_audit_module._parse_iso_date(row.get("promo_to")),
        "normal_price": tag_audit_module._parse_money(row.get("normal_price")),
        "promo_price": tag_audit_module._parse_money(row.get("promo_price")),
        "expected_action": str(row.get("expected_action") or ""),
    }


def checklist_key(tag_audit_module, row: dict) -> str:
    encoded = json.dumps(
        _identity_payload(tag_audit_module, row),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "tag_" + sha256(encoded).hexdigest()[:24]


def _current_action_rows(tag_audit_module, rows: list[dict]) -> list[dict]:
    derive = getattr(tag_audit_module, "scanner_rows_for_current_date", None)
    return derive(rows) if callable(derive) else list(rows or [])


def checklist_rows(tag_audit_module, rows: list[dict]) -> list[dict]:
    """Return unique promotion-level tags that should be present today."""
    items: list[dict] = []
    seen: set[str] = set()
    for row in _current_action_rows(tag_audit_module, rows):
        if str(row.get("expected_action") or "") != "gan_tem":
            continue
        key = checklist_key(tag_audit_module, row)
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "check_key": key,
            "item_id": row.get("item_id"),
            "item_name": row.get("item_name"),
            "key_channel": row.get("key_channel"),
            "channel": row.get("channel"),
            "campaign_name": row.get("campaign_name"),
            "campaign_detail": row.get("campaign_detail"),
            "promo_from": tag_audit_module._cell_value(row.get("promo_from")),
            "promo_to": tag_audit_module._cell_value(row.get("promo_to")),
            "promo_price": tag_audit_module._parse_money(row.get("promo_price")),
            "pog_code": row.get("pog_code"),
            "location_id": row.get("location_id"),
            "facing": row.get("facing"),
            "store_id": row.get("store_id"),
            "expected_action": "gan_tem",
        })
    return sorted(
        items,
        key=lambda item: (
            str(item.get("pog_code") or ""),
            str(item.get("location_id") or ""),
            str(item.get("item_id") or ""),
            str(item.get("campaign_name") or ""),
            item["check_key"],
        ),
    )


def context_id(tag_audit_module, rows: list[dict]) -> str:
    keys = sorted(item["check_key"] for item in checklist_rows(tag_audit_module, rows))
    encoded = json.dumps(
        {"version": _PROGRESS_VERSION, "required_tag_keys": keys},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "ctx_" + sha256(encoded).hexdigest()[:24]


def _progress_state(result: dict) -> str | None:
    if not result.get("progress_eligible"):
        return None
    severity = str((result.get("verdict") or {}).get("severity") or "warning")
    if severity == "success":
        return "pass"
    if severity == "error":
        return "fail"
    return "review"


def install_tag_audit_progress_contract(tag_audit_module, core_module) -> None:
    """Add checklist identity/route while leaving CTKM verdict logic untouched."""
    if getattr(core_module.app.state, "tag_audit_progress_contract_v1", False):
        return

    if not hasattr(tag_audit_module, "_progress_original_context_payload"):
        tag_audit_module._progress_original_context_payload = tag_audit_module._context_payload
        original_context_payload = tag_audit_module._context_payload

        def progress_context_payload(cache: dict) -> dict:
            payload = original_context_payload(cache)
            rows = cache.get("rows") or []
            payload["context_id"] = context_id(tag_audit_module, rows)
            payload["checklist_count"] = len(checklist_rows(tag_audit_module, rows))
            payload["progress_scope"] = "gan_tem_only"
            return payload

        tag_audit_module._context_payload = progress_context_payload

    if not hasattr(tag_audit_module, "_progress_original_compare_observation"):
        tag_audit_module._progress_original_compare_observation = tag_audit_module.compare_observation
        original_compare_observation = tag_audit_module.compare_observation

        def progress_compare_observation(rows, observed, manual_item_id=""):
            result = original_compare_observation(rows, observed, manual_item_id=manual_item_id)
            expected = result.get("expected") or None
            verdict_code = str((result.get("verdict") or {}).get("code") or "")
            identity_source = str(result.get("identity_source") or "")
            eligible = bool(
                expected
                and str(expected.get("expected_action") or "") == "gan_tem"
                and identity_source in {"manual_item_id", "ocr_item_id"}
                and verdict_code not in _EXCLUDED_PROGRESS_VERDICTS
            )
            result["check_key"] = checklist_key(tag_audit_module, expected) if eligible else None
            result["progress_eligible"] = eligible
            result["progress_state"] = _progress_state(result)
            return result

        tag_audit_module.compare_observation = progress_compare_observation

    async def tag_audit_checklist(_admin: str = Depends(core_module.require_admin)):
        cache = tag_audit_module._current_context(core_module)
        items = checklist_rows(tag_audit_module, cache.get("rows") or [])
        return {
            "context": tag_audit_module._context_payload(cache),
            "items": items,
        }

    tag_audit_module._insert_api_route_before_frontend(
        core_module,
        "/api/tag-audit/checklist",
        tag_audit_checklist,
        ["GET"],
        response_model=None,
    )
    core_module.tag_audit_checklist = tag_audit_checklist
    core_module.app.state.tag_audit_progress_contract_v1 = True

    # The manual shelf checker is a separate store-facing mode. It intentionally
    # uses isolated temporary workbook sessions and therefore does not require an
    # admin login or mutate the admin scanner context.
    from backend.tag_audit_shelf_contract import install_tag_audit_shelf_contract
    install_tag_audit_shelf_contract(tag_audit_module, core_module)
