# -*- coding: utf-8 -*-
"""Derived channel/scope semantics without mutating source channel values."""
from __future__ import annotations

import hashlib
import json
import unicodedata


def normalize_scope_text(value) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFD", str(value).strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def _key_channel_class(value) -> str:
    text = normalize_scope_text(value)
    aliases = {
        "all": "all",
        "all channel": "all",
        "all channels": "all",
        "offline": "offline",
        "online": "online",
        "other": "others",
        "others": "others",
    }
    return aliases.get(text, text)


def scope_identity_key(key_channel, channel) -> str:
    """Exact operational scope identity, normalized only for comparison/dedupe."""
    return f"{_key_channel_class(key_channel)}|{normalize_scope_text(channel)}"


def scope_overlap_relation(key_channel_a, channel_a, key_channel_b, channel_b) -> str:
    """Return same/intersects/disjoint/unknown for two source channel scopes.

    KEY Channel is the broad Pharmacity application scope. ``Others`` is
    heterogeneous, so its raw Channel value is needed before calling two rows the
    same scope. All-channel intersects narrower scopes but is not automatically a
    blocking duplicate. Source values are never rewritten.
    """
    ka = _key_channel_class(key_channel_a)
    kb = _key_channel_class(key_channel_b)
    ca = normalize_scope_text(channel_a)
    cb = normalize_scope_text(channel_b)

    if ka == kb:
        if ka in {"all", "offline", "online"}:
            return "same"
        if ka == "others":
            return "same" if ca and ca == cb else "unknown"
        if ka:
            return "same" if ca == cb else "unknown"
        if ca and ca == cb:
            return "same"
        return "unknown"

    if "all" in {ka, kb} and (ka or kb):
        return "intersects"
    if {ka, kb} == {"offline", "online"}:
        return "disjoint"
    return "unknown"


def _canonical(value):
    if value is None:
        return None
    try:
        if value != value:  # NaN without importing pandas
            return None
    except Exception:
        pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return str(value)
    return str(value)


def operational_promotion_key(row, promotion_columns) -> str:
    """Stable work identity that normalizes only KEY Channel/Channel formatting."""
    values = []
    for column in promotion_columns:
        if column == "key_channel":
            values.append(_key_channel_class(row.get(column)))
        elif column == "channel":
            values.append(normalize_scope_text(row.get(column)))
        else:
            values.append(_canonical(row.get(column)))
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return f"OPPROMO-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24].upper()}"


def operational_task_key(operational_promotion_id, scheduled_action, pog_position_id) -> str:
    payload = json.dumps(
        [_canonical(operational_promotion_id), _canonical(scheduled_action), _canonical(pog_position_id)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"OPTASK-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24].upper()}"
