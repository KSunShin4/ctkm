# -*- coding: utf-8 -*-
"""Safe comparison identity for Pharmacity source/replacement item codes.

Source ``item_id`` remains authoritative for promotion identity and export.
This module only answers whether two valid P-codes may be treated as the same
product for comparison-oriented logic such as overlap detection, cross-source
confirmation and summary coverage.

Automatic equivalence is intentionally conservative:
- both values must match ``P<digits>``;
- a transition must be one-to-one in the observed frame;
- chains and one-to-many/many-to-one transitions are left ambiguous;
- direct use of the replacement code as another source item does not invalidate
  product comparison, but it does make POG remapping unsafe because the POG row
  may belong to that direct source row.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

import pandas as pd

_SKU_RE = re.compile(r"^P\d+$", re.IGNORECASE)


def _default_key(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip().upper()
    return text or None


def _is_sku(key) -> bool:
    return bool(key and _SKU_RE.fullmatch(str(key)))


@dataclass(frozen=True)
class TransitionIdentity:
    """Derived comparison/remap contract for one observed collection of rows."""

    comparison_map: dict[str, str]
    pog_alias_map: dict[str, str]
    ambiguous_keys: frozenset[str]
    shadowed_new_keys: frozenset[str]
    safe_pairs: tuple[tuple[str, str], ...]

    def canonical(self, value, *, key_func: Callable | None = None):
        key = (key_func or _default_key)(value)
        return self.comparison_map.get(key, key)


def build_transition_identity(
    frame: pd.DataFrame | None,
    *,
    key_func: Callable | None = None,
    is_sku: Callable | None = None,
) -> TransitionIdentity:
    key_func = key_func or _default_key
    is_sku = is_sku or _is_sku
    empty = TransitionIdentity({}, {}, frozenset(), frozenset(), ())
    if frame is None or frame.empty or "new_item_id" not in frame.columns:
        return empty

    source_values = frame.get(
        "item_key",
        frame.get("item_id", pd.Series(index=frame.index, dtype=object)),
    )
    new_values = frame.get(
        "new_item_key",
        frame["new_item_id"].map(key_func),
    )

    direct_source_keys = {
        key_func(value) for value in source_values
        if is_sku(key_func(value))
    }

    edges: set[tuple[str, str]] = set()
    for source_value, new_value in zip(source_values, new_values):
        source = key_func(source_value)
        new = key_func(new_value)
        if not source or not new or source == new:
            continue
        if not is_sku(source) or not is_sku(new):
            continue
        edges.add((source, new))

    if not edges:
        return empty

    incident: dict[str, set[tuple[str, str]]] = {}
    for edge in edges:
        source, new = edge
        incident.setdefault(source, set()).add(edge)
        incident.setdefault(new, set()).add(edge)

    # Degree > 1 includes chains (A->B->C), one-to-many and many-to-one.
    # All are deliberately ambiguous for automatic comparison because the file
    # does not tell us which code is the authoritative product identity.
    ambiguous = {key for key, linked in incident.items() if len(linked) != 1}

    safe_pairs = tuple(sorted(
        (source, new)
        for source, new in edges
        if source not in ambiguous and new not in ambiguous
    ))

    comparison_map: dict[str, str] = {}
    for source, new in safe_pairs:
        # Keep the observed source code as representative. This comparison key is
        # never written back to source item_id or used in promotion/task identity.
        comparison_map[source] = source
        comparison_map[new] = source

    shadowed_new = {
        new for _source, new in safe_pairs if new in direct_source_keys
    }
    pog_alias_map = {
        new: source
        for source, new in safe_pairs
        if new not in shadowed_new
    }

    return TransitionIdentity(
        comparison_map=comparison_map,
        pog_alias_map=pog_alias_map,
        ambiguous_keys=frozenset(ambiguous),
        shadowed_new_keys=frozenset(shadowed_new),
        safe_pairs=safe_pairs,
    )


def canonical_series(
    frame: pd.DataFrame | None,
    identity: TransitionIdentity,
    *,
    key_func: Callable | None = None,
) -> pd.Series:
    """Return a comparison-only product key Series for a frame."""
    if frame is None:
        return pd.Series(dtype=object)
    if frame.empty:
        return pd.Series(index=frame.index, dtype=object)
    key_func = key_func or _default_key
    if "item_key" in frame.columns:
        values = frame["item_key"]
    elif "item_id" in frame.columns:
        values = frame["item_id"]
    else:
        return pd.Series(index=frame.index, dtype=object)
    return values.map(lambda value: identity.canonical(value, key_func=key_func))
