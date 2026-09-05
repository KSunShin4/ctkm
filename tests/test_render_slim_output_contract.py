from types import SimpleNamespace

import pandas as pd
from openpyxl import load_workbook

import main
from backend.final_output_contract import validate_ctkm_workbook
from backend.slim_output_contract import SLIM_SHEET_ORDER, install_slim_output_contract


def _actions():
    rows = [
        {
            "task_id": "T-GAN",
            "item_id": "P1001",
            "item_name": "Gan",
            "key_channel": "Offline",
            "channel": "OFFLINE",
            "campaign_name": "A",
            "promo_from": pd.Timestamp("2026-09-01"),
            "promo_to": pd.Timestamp("2026-09-30"),
            "scheduled_action": "gắn tem",
            "action": "gắn tem",
            "in_report_scope": True,
            "location_completeness": "Đủ vị trí",
            "location_needs_review": False,
            "review_required": True,
            "review_reason": "xung_dot_chuong_trinh",
            "review_severity": "warning",
            "review_blocks_action": False,
            "program_source": "CTKM",
        },
        {
            "task_id": "T-THAO",
            "item_id": "P1002",
            "item_name": "Thao",
            "key_channel": "Online",
            "channel": "Online",
            "campaign_name": "B",
            "promo_from": pd.Timestamp("2026-09-01"),
            "promo_to": pd.Timestamp("2026-09-04"),
            "scheduled_action": "tháo tem",
            "action": "tháo tem",
            "in_report_scope": True,
            "location_completeness": "Đủ vị trí",
            "location_needs_review": False,
            "review_required": False,
            "review_reason": "",
            "program_source": "CTKM",
        },
        {
            "task_id": "T-WAIT",
            "item_id": "P1003",
            "item_name": "Wait",
            "key_channel": "Others",
            "channel": "Offline/WEB/APP",
            "campaign_name": "C",
            "promo_from": pd.Timestamp("2026-09-27"),
            "promo_to": pd.Timestamp("2026-09-27"),
            "scheduled_action": "chờ gắn tem",
            "action": "chờ gắn tem",
            "in_report_scope": True,
            "location_completeness": "Không tìm thấy SKU trong POG",
            "location_needs_review": True,
            "review_required": False,
            "review_reason": "",
            "program_source": "CTKM",
        },
    ]
    return pd.DataFrame(rows)


def _install_on_fake_backend():
    # Use the public exporter module but isolate installation state.
    core = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace()),
        _main_mod=SimpleNamespace(EX=main.EX),
    )
    install_slim_output_contract(core)
    return core


def test_slim_backend_export_writes_only_required_operational_sheets(tmp_path):
    core = _install_on_fake_backend()
    output = tmp_path / "slim.xlsx"
    actions = _actions()
    summary = {
        "Thang bao cao": "2026-09",
        "Ngay nghiep vu": pd.Timestamp("2026-09-05"),
        "So dong KM thieu vi tri POG": 1,
        "So dong can kiem tra vi tri": 1,
        "So dong cho gan": 1,
        "So dong can review": 1,
    }

    main.EX.export_final_report(
        output_path=output,
        df_matched=pd.DataFrame(),
        df_ctkm_only=pd.DataFrame(),
        df_pog_only=pd.DataFrame(),
        overlap_warnings=[],
        mapping_logs=[],
        reconciliation_summary=summary,
        df_fefo_actions=actions,
    )

    workbook = load_workbook(output, data_only=False)
    assert workbook.sheetnames == SLIM_SHEET_ORDER
    assert "Canh bao trung thoi gian" not in workbook.sheetnames
    assert "Mapping log" not in workbook.sheetnames
    assert "Tom tat" not in workbook.sheetnames
    assert "POG metadata" not in workbook.sheetnames
    assert "Xác nhận CTKM Clearance" not in workbook.sheetnames

    assert workbook["Gắn tem"].max_row == 2
    assert workbook["Tháo tem"].max_row == 2
    assert workbook["Chờ gắn"].max_row == 2
    # P1001 keeps its operational action and also appears in review.
    assert workbook["Cần review"].max_row == 2
    assert workbook["CTKM thieu vi tri ke"].max_row == 2
    assert workbook["POG cần kiểm tra"].max_row == 2
    assert workbook["Audit hành động"].max_row == 4
    workbook.close()

    validate_ctkm_workbook(output, summary)
    assert core.app.state.ctkm_output_profile == "production-slim"


def test_full_library_export_remains_available_outside_backend_contract(tmp_path):
    # The contract is backend-installed; source exporter still exposes the full
    # implementation for CLI/tests that do not install the backend suite.
    assert hasattr(main.EX, "_original_export_final_report")
