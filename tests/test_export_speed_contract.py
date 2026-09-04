import pandas as pd
from openpyxl import Workbook

from backend import main_api


def test_export_speed_contract_is_installed_on_shared_exporter_core():
    exporter = main_api._main_mod._core.EX
    exporter_core = exporter._core
    assert main_api.app.state.export_speed_contract_v1 is True
    assert getattr(exporter_core._apply_professional_style, "_ctkm_export_speed_contract_v1", False)
    assert getattr(exporter_core._apply_alternating_shelf_colors, "_ctkm_export_speed_contract_v1", False)


def test_bounded_style_uses_range_rules_not_full_cell_matrix_mutation():
    exporter_core = main_api._main_mod._core.EX._core
    wb = Workbook()
    ws = wb.active
    ws.title = "Gắn tem"
    headers = [
        "store_id", "pog_code", "action", "location_completeness",
        "location_needs_review", "promotion_count_at_position",
        "has_multiple_promotions_at_position",
    ]
    ws.append(headers)
    ws.append(["S1", "P1", "gắn tem", "Đủ vị trí", False, 1, False])
    ws.append(["S1", "P1", "tháo tem", "Đủ vị trí", False, 1, False])
    ws.append(["S2", "P2", "review", "Thiếu một phần thông tin vị trí", True, 2, True])

    frame = pd.DataFrame([
        dict(zip(headers, row))
        for row in [
            ["S1", "P1", "gắn tem", "Đủ vị trí", False, 1, False],
            ["S1", "P1", "tháo tem", "Đủ vị trí", False, 1, False],
            ["S2", "P2", "review", "Thiếu một phần thông tin vị trí", True, 2, True],
        ]
    ])

    exporter_core._apply_professional_style(ws, "Gắn tem", frame)
    exporter_core._apply_alternating_shelf_colors(ws, frame)

    # Header remains directly styled; data emphasis is represented as bounded
    # conditional-format rules instead of assigning style to every cell.
    assert ws["A1"].fill.fill_type == "solid"
    assert ws["A1"].font.bold is True
    assert len(ws.conditional_formatting) >= 5

    # No historical shelf pass should repaint ordinary body cells directly.
    assert ws["A2"].fill.fill_type is None
    assert ws["A3"].fill.fill_type is None

    assert ws.column_dimensions["A"].width >= 12
    assert ws.sheet_format.defaultRowHeight == 22
    assert ws.freeze_panes == "C2"
    assert ws.auto_filter.ref == ws.dimensions
    wb.close()
