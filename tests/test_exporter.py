from openpyxl import Workbook

import main


def test_technical_column_hiding_never_hides_application_channel():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["extra__KEY Channel", "extra__Audit only", "channel"])

    main.EX._hide_technical_columns(sheet)

    assert sheet.column_dimensions["A"].hidden is False
    assert sheet.column_dimensions["B"].hidden is True
    assert sheet.column_dimensions["C"].hidden is False


def test_selected_output_columns_always_keep_application_channel():
    frame = main.pd.DataFrame({
        "item_id": ["P1"],
        "campaign_name": ["FULL MONTH"],
        "channel": ["OFFLINE"],
    })

    result = main.EX._filter_selected_columns(frame, ["campaign_name"])

    assert result.columns.tolist() == ["item_id", "campaign_name", "channel"]
