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


def test_raw_channel_is_preferred_over_key_channel():
    perf = _performance_module()
    frame = pd.DataFrame({
        "KEY Channel": ["OFFLINE", "ONLINE"],
        "Channel": ["COMBO ĐI SINH", "MẸ & BÉ"],
        "Item code": ["P1", "P2"],
    })
    mapping = {"KEY Channel": "channel", "Item code": "item_id"}

    result = perf.prefer_raw_channel_mapping(mapping, frame, normalize_header=_normalize)

    assert result.get("Channel") == "channel"
    assert result.get("KEY Channel") != "channel"


def test_action_sheet_places_user_fields_before_technical_ids():
    perf = _performance_module()
    frame = pd.DataFrame({
        "task_id": ["T1"],
        "promotion_id": ["P1"],
        "pog_position_id": ["L1"],
        "item_id": ["P123"],
        "item_name": ["Thuốc A"],
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

    assert columns.index("item_id") < columns.index("task_id")
    assert columns.index("item_name") < columns.index("promotion_id")
    assert columns.index("channel") < columns.index("pog_position_id")
    assert columns[:4] == ["item_id", "item_name", "channel", "campaign_name"]
