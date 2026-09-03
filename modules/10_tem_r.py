"""Tem R facade with store-level inventory capacity fixes.

Workbook IO/hardening stays in ``tem_r_core.py``. This facade only replaces the
allocation step so a store-level stock value cannot be spent again on each shelf.
Rows with missing/error stock remain visible for audit but are excluded from the
allocation problem entirely.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from typing import Any

import pandas as pd


_CORE_MODULE_NAME = "_ctkm_tem_r_core"
_CORE_PATH = Path(__file__).with_name("tem_r_core.py")

if _CORE_MODULE_NAME in sys.modules:
    _core = sys.modules[_CORE_MODULE_NAME]
else:
    _spec = importlib.util.spec_from_file_location(_CORE_MODULE_NAME, _CORE_PATH)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Không nạp được Tem R core: {_CORE_PATH}")
    _core = importlib.util.module_from_spec(_spec)
    sys.modules[_CORE_MODULE_NAME] = _core
    _spec.loader.exec_module(_core)

# Preserve the existing public/helper surface for backend code and tests.
for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)


def _excel_row_for_index(df: pd.DataFrame, idx: int) -> int:
    """Return the real source Excel row when lineage is available."""
    if "_excel_row" in df.columns:
        value = df.at[idx, "_excel_row"]
        try:
            if not pd.isna(value):
                return int(value)
        except (TypeError, ValueError):
            pass
    return int(idx) + 2


def build_tem_r_plan(
    frame: pd.DataFrame,
    *,
    max_location_distance: float = 1,
    stock_column: str = "TỒN",
) -> TemRPlan:
    """Allocate Tem R without reusing one store-level stock pool per shelf.

    Rules:
    - missing/error stock (including #N/A) is excluded from allocation completely;
    - numeric zero is a Tem R target;
    - positive stock is store-level inventory for ``STOREID + ITEMID``;
    - repeated POG rows never add stock together;
    - every positive POG position reserves one unit before spare capacity is used;
    - replacement candidates must still exist on the same shelf and respect the
      configured LOCATIONID distance.
    """
    if max_location_distance <= 0:
        raise ValueError("max_location_distance phải lớn hơn 0")

    df = _clean_input(frame, stock_column)
    df["TEM R"] = pd.NA
    df["TEM_R_STATUS"] = pd.NA
    df["TEM_R_REPRESENTATIVE"] = pd.NA

    exceptions: list[dict[str, Any]] = []
    remaining: dict[int, int] = {}

    invalid_rows = df.index[df["_input_error"].notna()].tolist()
    for idx in invalid_rows:
        reason = str(df.at[idx, "_input_error"])
        df.at[idx, "TEM_R_STATUS"] = reason
        if pd.isna(df.at[idx, "_stock"]):
            df.at[idx, "TEM R"] = df.at[idx, "_stock_skip_marker"]
        exceptions.append({
            "row": _excel_row_for_index(df, idx),
            "ITEMID": df.at[idx, "ITEMID"],
            "reason": reason,
        })

    # Invalid/NA stock rows do not participate in stock, capacity, shelf layout,
    # or target selection. They remain only as visible audit rows above.
    valid_df = df[df["_input_error"].isna()]

    # Build one inventory ledger for the whole store. Stock is repeated on POG
    # rows, so take max instead of summing. Reserve one physical unit for every
    # currently occupied positive-stock POG position across all shelves.
    store_stock_by_item: dict[tuple[str, str], int] = {}
    store_own_positions: dict[tuple[str, str], int] = {}
    for idx, row in valid_df.iterrows():
        stock = int(row["_stock"])
        if stock <= 0:
            continue
        store = str(row["STOREID"]).strip()
        item = str(row["ITEMID"])
        key = (store, item)
        store_stock_by_item[key] = max(store_stock_by_item.get(key, 0), stock)
        store_own_positions[key] = store_own_positions.get(key, 0) + 1
        df.at[idx, "TEM_R_STATUS"] = "Còn tồn - không cần Tem R"

    store_capacity = {
        key: max(0, stock - store_own_positions.get(key, 0))
        for key, stock in store_stock_by_item.items()
    }

    for _, group_frame in valid_df.groupby("_group", sort=False):
        ordered = sorted(
            group_frame.index,
            key=lambda idx: (
                df.at[idx, "_location"]
                if not pd.isna(df.at[idx, "_location"])
                else float("inf"),
                idx,
            ),
        )
        if not ordered:
            continue

        store = str(df.at[ordered[0], "STOREID"]).strip()
        stock_by_item: dict[str, int] = {}
        source_locations: dict[str, list[float]] = {}

        for source_idx in ordered:
            stock = int(df.at[source_idx, "_stock"])
            if stock <= 0:
                continue
            item = str(df.at[source_idx, "ITEMID"])
            stock_by_item[item] = store_stock_by_item.get((store, item), stock)
            source_locations.setdefault(item, []).append(df.at[source_idx, "_location"])

        targets = [idx for idx in ordered if df.at[idx, "_stock"] == 0]
        if not targets:
            continue

        # Candidate SKU must be present on this shelf, but capacity comes from
        # the store-wide ledger and is permanently consumed across shelf groups.
        capacity = {
            item: store_capacity.get((store, item), 0)
            for item in stock_by_item
        }
        proposed: dict[int, str | None] = {idx: None for idx in targets}
        unassigned = set(targets)
        target_order = {idx: position for position, idx in enumerate(targets)}
        item_order = {item: position for position, item in enumerate(stock_by_item)}

        while unassigned:
            candidates = [
                (
                    min(
                        (
                            abs(location - df.at[target_idx, "_location"])
                            for location in source_locations[item]
                            if not pd.isna(location)
                            and not pd.isna(df.at[target_idx, "_location"])
                        ),
                        default=float("inf"),
                    ),
                    target_order[target_idx],
                    item_order[item],
                    target_idx,
                    item,
                )
                for target_idx in unassigned
                for item, count in capacity.items()
                if count > 0
                and min(
                    (
                        abs(location - df.at[target_idx, "_location"])
                        for location in source_locations[item]
                    ),
                    default=float("inf"),
                ) <= max_location_distance
            ]
            if not candidates:
                break

            _, _, _, target_idx, item = min(candidates)
            proposed[target_idx] = item
            capacity[item] -= 1
            store_capacity[(store, item)] = capacity[item]
            unassigned.remove(target_idx)

        final_codes = [
            proposed.get(idx)
            if df.at[idx, "_stock"] == 0
            else str(df.at[idx, "ITEMID"])
            for idx in ordered
        ]

        def is_contiguous(code: str) -> bool:
            positions = [
                position for position, value in enumerate(final_codes)
                if value == code
            ]
            return not positions or positions == list(
                range(positions[0], positions[-1] + 1)
            )

        needs_rearrangement = any(
            not is_contiguous(code)
            for code in {code for code in final_codes if code is not None}
        )

        if needs_rearrangement:
            arranged_preview: list[str] = []
            for item in stock_by_item:
                arranged_preview.extend([item] * final_codes.count(item))
            arranged_preview.extend(
                ["KHÔNG CÓ SẢN PHẨM THAY THẾ"] * final_codes.count(None)
            )

            rearrangement_within_distance = all(
                representative == "KHÔNG CÓ SẢN PHẨM THAY THẾ"
                or min(
                    abs(location - df.at[target_idx, "_location"])
                    for location in source_locations[representative]
                ) <= max_location_distance
                for target_idx, representative in zip(ordered, arranged_preview)
            )
            if not rearrangement_within_distance:
                needs_rearrangement = False

        if not needs_rearrangement:
            for target_idx in targets:
                representative = proposed[target_idx]
                if representative is None:
                    df.at[target_idx, "TEM R"] = "KHÔNG CÓ SẢN PHẨM THAY THẾ"
                    df.at[target_idx, "TEM_R_STATUS"] = "Kệ không còn đủ tồn để thay"
                    exceptions.append({
                        "row": _excel_row_for_index(df, target_idx),
                        "ITEMID": df.at[target_idx, "ITEMID"],
                        "reason": "Kệ không còn đủ tồn để thay",
                    })
                    continue

                df.at[target_idx, "TEM R"] = representative
                df.at[target_idx, "TEM_R_REPRESENTATIVE"] = representative
                df.at[target_idx, "TEM_R_STATUS"] = "Tồn 0 - mã thay đã nằm liền nhóm"
            continue

        # Rearrangement only changes order. Counts were already reserved from
        # store_capacity while proposals were selected.
        arranged_items: list[str] = []
        for item in stock_by_item:
            arranged_items.extend([item] * final_codes.count(item))
        arranged_items.extend(
            ["KHÔNG CÓ SẢN PHẨM THAY THẾ"] * final_codes.count(None)
        )

        for position, target_idx in enumerate(ordered):
            if position >= len(arranged_items):
                df.at[target_idx, "TEM R"] = "KHÔNG CÓ SẢN PHẨM THAY THẾ"
                df.at[target_idx, "TEM_R_STATUS"] = "Kệ không còn đủ tồn để sắp xếp"
                exceptions.append({
                    "row": _excel_row_for_index(df, target_idx),
                    "ITEMID": df.at[target_idx, "ITEMID"],
                    "reason": "Kệ không còn đủ tồn để sắp xếp",
                })
                continue

            representative = arranged_items[position]
            df.at[target_idx, "TEM R"] = representative
            if representative == "KHÔNG CÓ SẢN PHẨM THAY THẾ":
                df.at[target_idx, "TEM_R_STATUS"] = "Kệ không còn đủ tồn để sắp xếp"
                exceptions.append({
                    "row": _excel_row_for_index(df, target_idx),
                    "ITEMID": df.at[target_idx, "ITEMID"],
                    "reason": "Kệ không còn đủ tồn để sắp xếp",
                })
            else:
                df.at[target_idx, "TEM_R_REPRESENTATIVE"] = representative
                df.at[target_idx, "TEM_R_STATUS"] = "Sắp xếp lại toàn kệ - gom mã P liền nhau"

    # Expose the same store-level spare capacity on every positive source row.
    for idx, row in valid_df.iterrows():
        if int(row["_stock"]) <= 0:
            continue
        key = (str(row["STOREID"]).strip(), str(row["ITEMID"]))
        remaining[idx] = store_capacity.get(key, 0)

    audit_columns = [
        "ITEMID", "ITEMNAME", "STOREID", "POGCODE", "FIXELID", "LOCATIONID",
        stock_column, "TEM R", "TEM_R_STATUS",
    ]
    audit = df.loc[:, audit_columns].copy()
    audit["NĂNG_LỰC_CÒN_LẠI"] = [
        remaining.get(idx, pd.NA)
        if not pd.isna(df.at[idx, "_stock"]) and df.at[idx, "_stock"] != 0
        else pd.NA
        for idx in df.index
    ]
    exception_frame = pd.DataFrame(exceptions, columns=["row", "ITEMID", "reason"])
    return TemRPlan(rows=df, audit=audit, exceptions=exception_frame)


# ``create_tem_r_workbook`` lives in the hardened IO core. Point its global
# allocator at the corrected function before re-exporting it.
_core.build_tem_r_plan = build_tem_r_plan
create_tem_r_workbook = _core.create_tem_r_workbook
inspect_tem_r_workbook = _core.inspect_tem_r_workbook
