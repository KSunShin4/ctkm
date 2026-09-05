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
