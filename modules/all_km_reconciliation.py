# -*- coding: utf-8 -*-
"""All-promotion POG reconciliation for the user-facing ``Tong hop`` sheet.

Historically ``Tong hop`` and ``POG không có CTKM`` were built from Monthly CTKM
only. That made valid Clearance-only products appear to be missing even though
the action pipeline still carried them. This contract keeps the historical
Monthly audit explicitly, but makes the user-facing reconciliation cover every
in-scope promotion source (Monthly + Clearance).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from modules.item_code_identity import build_transition_identity


_HOOK_NAME = "all-km-reconciliation-v1"
_COMPAT_MISSING_SHEET = "POG không có CTKM"
_ALL_KM_MISSING_SHEET = "POG không có KM"
_MONTHLY_MISSING_SHEET = "POG không có Monthly CTKM"


def _blank(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


def _identity(core_module, actions: pd.DataFrame):
    return build_transition_identity(
        actions,
        key_func=core_module.NM.make_item_key,
        is_sku=core_module.RC.is_sku,
    )


def _row_key(core_module, identity, row) -> str | None:
    raw = row.get("item_key")
    if _blank(raw):
        raw = row.get("item_id")
    key = core_module.NM.make_item_key(raw)
    if not key:
        return None
    return identity.canonical(key, key_func=core_module.NM.make_item_key)


def _frame_keys(core_module, identity, frame: pd.DataFrame | None) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=object)
    return frame.apply(lambda row: _row_key(core_module, identity, row), axis=1)


def _scope_actions(actions: pd.DataFrame | None) -> pd.DataFrame:
    if actions is None:
        return pd.DataFrame()
    scoped = actions.copy()
    if "in_report_scope" in scoped.columns:
        scoped = scoped[scoped["in_report_scope"].fillna(False).astype(bool)].copy()
    return scoped.reset_index(drop=True)


def _overlay_action(row_dict: dict, action: pd.Series) -> dict:
    result = dict(row_dict)
    for column, value in action.items():
        if _blank(value):
            continue
        if column not in result or _blank(result.get(column)):
            result[column] = value
        monthly_column = f"{column}__ctkm"
        if monthly_column in result and _blank(result.get(monthly_column)):
            result[monthly_column] = value
    result["program_source"] = str(action.get("program_source") or "KM").strip().upper()
    result["reconciliation_basis"] = "KM + POG"
    return result


def build_all_km_reconciliation_frames(
    core_module,
    df_matched: pd.DataFrame | None,
    df_pog_only_monthly: pd.DataFrame | None,
    df_fefo_actions: pd.DataFrame | None,
) -> tuple[pd.DataFrame, pd.DataFrame, set[str]]:
    """Return all-KM matched rows, true all-KM POG-missing rows and added SKU keys."""
    matched = df_matched.copy() if df_matched is not None else pd.DataFrame()
    pog_only = (
        df_pog_only_monthly.copy()
        if df_pog_only_monthly is not None else pd.DataFrame()
    )
    actions = _scope_actions(df_fefo_actions)

    identity_input = actions if not actions.empty else pd.concat(
        [frame for frame in (matched, pog_only) if frame is not None and not frame.empty],
        ignore_index=True,
        sort=False,
    ) if (not matched.empty or not pog_only.empty) else pd.DataFrame(columns=["item_id"])
    identity = _identity(core_module, identity_input)

    action_keys = _frame_keys(core_module, identity, actions)
    action_by_key: dict[str, pd.Series] = {}
    for position, key in enumerate(action_keys):
        if not key:
            continue
        action = actions.iloc[position]
        current = action_by_key.get(key)
        # Prefer a Clearance row for products that are Monthly-unmatched. It is
        # the most informative proof for why the SKU belongs in all-KM coverage.
        if current is None or (
            str(current.get("program_source") or "").upper() != "CLEARANCE"
            and str(action.get("program_source") or "").upper() == "CLEARANCE"
        ):
            action_by_key[key] = action

    if matched.empty:
        matched_all = matched.copy()
    else:
        matched_all = matched.copy()
        if "program_source" not in matched_all.columns:
            matched_all["program_source"] = "CTKM"
        else:
            matched_all["program_source"] = matched_all["program_source"].map(
                lambda value: "CTKM" if _blank(value) else value
            )
        if "reconciliation_basis" not in matched_all.columns:
            matched_all["reconciliation_basis"] = "Monthly + POG"
        else:
            matched_all["reconciliation_basis"] = matched_all["reconciliation_basis"].map(
                lambda value: "Monthly + POG" if _blank(value) else value
            )

    pog_keys = _frame_keys(core_module, identity, pog_only)
    covered_mask = pog_keys.map(lambda key: bool(key and key in action_by_key))
    covered_pog = pog_only.loc[covered_mask].copy().reset_index(drop=True)
    missing_all_km = pog_only.loc[~covered_mask].copy().reset_index(drop=True)

    added_rows: list[dict] = []
    added_keys: set[str] = set()
    if not covered_pog.empty:
        covered_keys = _frame_keys(core_module, identity, covered_pog)
        for position, key in enumerate(covered_keys):
            if not key:
                continue
            action = action_by_key.get(key)
            if action is None:
                continue
            added_rows.append(_overlay_action(covered_pog.iloc[position].to_dict(), action))
            added_keys.add(key)

    if added_rows:
        added = pd.DataFrame(added_rows)
        matched_all = pd.concat([matched_all, added], ignore_index=True, sort=False)

    # Hard invariant: an in-scope KM SKU that exists in POG must never be absent
    # from the user-facing Tong hop coverage after this transformation.
    all_pog_keys = set(_frame_keys(core_module, identity, matched).dropna()) | set(pog_keys.dropna())
    km_keys = set(action_keys.dropna())
    tong_hop_keys = set(_frame_keys(core_module, identity, matched_all).dropna())
    missing_from_tong_hop = (all_pog_keys & km_keys) - tong_hop_keys
    if missing_from_tong_hop:
        raise RuntimeError(
            "All-KM reconciliation invariant failed; KM+POG SKU missing from Tong hop: "
            + ", ".join(sorted(missing_from_tong_hop))
        )

    return matched_all.reset_index(drop=True), missing_all_km, added_keys


def _excel_value(value):
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def _write_frame_sheet(core_module, workbook, name: str, frame: pd.DataFrame) -> None:
    if name in workbook.sheetnames:
        del workbook[name]
    ws = workbook.create_sheet(name)
    source = frame if frame is not None else pd.DataFrame()
    if source.empty:
        source = pd.DataFrame({"Ghi chu": ["Không có dòng phù hợp."]})
    ws.append(list(source.columns))
    for _, row in source.iterrows():
        ws.append([_excel_value(row[column]) for column in source.columns])
    style = getattr(core_module.EX, "_apply_professional_style", None)
    if callable(style):
        style(ws, name, source)
    bilingual = getattr(core_module.EX, "_apply_bilingual_headers", None)
    if callable(bilingual):
        bilingual(ws)


def _publish_user_facing_audits(
    core_module,
    output_path,
    monthly_pog_only: pd.DataFrame,
) -> None:
    path = Path(output_path)
    if not path.is_file():
        return
    workbook = load_workbook(path)

    # The compatibility sheet is now populated with true all-KM missing rows by
    # the wrapped exporter. Keep it for contracts/older clients, but expose a
    # correctly named visible copy to store users.
    if _ALL_KM_MISSING_SHEET in workbook.sheetnames:
        del workbook[_ALL_KM_MISSING_SHEET]
    if _COMPAT_MISSING_SHEET in workbook.sheetnames:
        compat = workbook[_COMPAT_MISSING_SHEET]
        all_km_ws = workbook.copy_worksheet(compat)
        all_km_ws.title = _ALL_KM_MISSING_SHEET
        compat.sheet_state = "hidden"

    _write_frame_sheet(core_module, workbook, _MONTHLY_MISSING_SHEET, monthly_pog_only)

    preferred_after_tong_hop = [_ALL_KM_MISSING_SHEET, _MONTHLY_MISSING_SHEET, _COMPAT_MISSING_SHEET]
    if "Tong hop" in workbook.sheetnames:
        before = [sheet for sheet in workbook.worksheets if sheet.title not in preferred_after_tong_hop]
        tong_index = next(i for i, sheet in enumerate(before) if sheet.title == "Tong hop")
        inserts = [workbook[name] for name in preferred_after_tong_hop if name in workbook.sheetnames]
        workbook._sheets = before[: tong_index + 1] + inserts + before[tong_index + 1 :]

    workbook.save(path)
    workbook.close()


def apply_all_km_reconciliation_hook(core_module, facade_module=None) -> None:
    """Wrap the current exporter surface after the main facade has rebuilt it."""
    current = core_module.EX.export_final_report
    if getattr(current, "_all_km_reconciliation_v1", False):
        return

    def export_all_km(*args, **kwargs):
        df_matched = kwargs.get("df_matched")
        if df_matched is None and len(args) > 1:
            df_matched = args[1]
        monthly_pog_only = kwargs.get("df_pog_only")
        if monthly_pog_only is None and len(args) > 3:
            monthly_pog_only = args[3]
        actions = kwargs.get("df_fefo_actions")
        if actions is None and len(args) > 9:
            actions = args[9]
        summary = kwargs.get("reconciliation_summary")
        if summary is None and len(args) > 6:
            summary = args[6]

        matched_all, missing_all_km, added_keys = build_all_km_reconciliation_frames(
            core_module, df_matched, monthly_pog_only, actions
        )

        if isinstance(summary, dict):
            identity_input = _scope_actions(actions)
            if identity_input.empty:
                identity_input = matched_all
            identity = _identity(core_module, identity_input)
            monthly_keys = set(_frame_keys(core_module, identity, monthly_pog_only).dropna())
            summary["So dong POG khong co CTKM Monthly phu hop"] = len(monthly_pog_only) if monthly_pog_only is not None else 0
            summary["So item POG khong co CTKM Monthly phu hop"] = len(monthly_keys)
            summary["So dong khop (Matched)"] = len(matched_all)
            summary["So item duy nhat khop"] = len(set(_frame_keys(core_module, identity, matched_all).dropna()))
            summary["So item Clearance bo sung vao Tong hop"] = len(added_keys)
            summary["So item KM+POG thieu trong Tong hop"] = 0

        call_args = list(args)
        call_kwargs = dict(kwargs)
        if "df_matched" in call_kwargs or len(call_args) <= 1:
            call_kwargs["df_matched"] = matched_all
        else:
            call_args[1] = matched_all
        if "df_pog_only" in call_kwargs or len(call_args) <= 3:
            call_kwargs["df_pog_only"] = missing_all_km
        else:
            call_args[3] = missing_all_km

        output_path = current(*call_args, **call_kwargs)
        _publish_user_facing_audits(core_module, output_path, monthly_pog_only)
        return output_path

    export_all_km._all_km_reconciliation_v1 = True
    core_module.EX.export_final_report = export_all_km
