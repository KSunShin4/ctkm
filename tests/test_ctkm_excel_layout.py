import importlib.util
from pathlib import Path
import sys

import pandas as pd


def _performance_module():
    root = Path(__file__).resolve().parents[1]
    path = root / "modules" / "ctkm_performance.py"
    spec = importlib.util.spec_from_file_location("ctkm_excel_layout_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _normalize(value):
    return " ".join(str(value).strip().lower().split())


def test_key_channel_and_channel_are_both_preserved():
    perf = _performance_module()
    frame = pd.DataFrame({
        "KEY Channel": ["OFFLINE", "ONLINE"],
        "Channel": ["COMBO ĐI SINH", "MẸ & BÉ"],
        "Item code": ["P1", "P2"],
    })
    mapping = {"KEY Channel": "channel", "Item code": "item_id"}

    result = perf.preserve_both_channel_mappings(
        mapping, frame, normalize_header=_normalize
    )

    assert result["KEY Channel"] == "key_channel"
    assert result["Channel"] == "channel"


def test_action_sheet_starts_with_approved_user_columns():
    perf = _performance_module()
    frame = pd.DataFrame({
        "task_id": ["T1"],
        "promotion_id": ["P1"],
        "pog_position_id": ["L1"],
        "item_id": ["P123"],
        "item_name": ["Thuốc A"],
        "promo_uom": ["Hộp"],
        "key_channel": ["OFFLINE"],
        "channel": ["MẸ & BÉ"],
        "campaign_name": ["CTKM A"],
        "store_id": ["S1"],
        "pog_code": ["POG1"],
        "location_id": [1],
        "scheduled_action": ["gắn tem"],
        "processing_status": ["Chưa xử lý"],
    })

    result = perf.prepare_action_sheet_user_first(frame)
    columns = list(result.columns)

    assert columns[:5] == [
        "key_channel", "channel", "item_id", "item_name", "promo_uom"
    ]
    assert columns.index("item_id") < columns.index("task_id")
    assert columns.index("key_channel") < columns.index("promotion_id")
    assert columns.index("channel") < columns.index("pog_position_id")


def test_selected_output_pins_both_channels_before_identifier():
    perf = _performance_module()
    frame = pd.DataFrame({
        "item_id": ["P1"],
        "item_name": ["Thuốc A"],
        "key_channel": ["ALL CHANNEL - EXCEPT MKP"],
        "channel": ["COMBO ĐI SINH"],
        "campaign_name": ["CTKM A"],
    })

    result = perf.filter_selected_columns_keep_channels(frame, ["item_name"])

    assert list(result.columns) == ["key_channel", "channel", "item_id", "item_name"]


def test_selected_output_does_not_reorder_columns_by_checkbox_click_sequence():
    perf = _performance_module()
    frame = pd.DataFrame({
        "item_id": ["P1"],
        "item_name": ["Thuốc A"],
        "campaign_name": ["CTKM A"],
        "key_channel": ["Offline"],
        "channel": ["OFFLINE"],
    })

    result = perf.filter_selected_columns_keep_channels(
        frame, ["campaign_name", "item_name"]
    )

    assert list(result.columns) == [
        "key_channel", "channel", "item_id", "item_name", "campaign_name"
    ]


def test_output_labels_keep_channel_source_names_exact():
    perf = _performance_module()

    class FakeExporter:
        _BILINGUAL_HEADERS = {}

    class FakeMain:
        EX = FakeExporter()

    from modules import ctkm_output_layout
    ctkm_output_layout.apply_header_labels(FakeMain.EX)

    assert FakeMain.EX._BILINGUAL_HEADERS["key_channel"] == "KEY Channel"
    assert FakeMain.EX._BILINGUAL_HEADERS["channel"] == "Channel"
    assert FakeMain.EX._BILINGUAL_HEADERS["promo_uom"] == "Đơn vị sản phẩm (Promo UoM)"
