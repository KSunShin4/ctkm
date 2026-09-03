from io import BytesIO
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from backend import input_contract
from backend.input_contract import (
    _validate_xlsx_container,
    validate_manual_mapping,
    validate_output_columns,
)
from backend.mapping_result_contract import install_mapping_result_contract


FACT_SCHEMA = {
    "item_id": {"required": True},
    "campaign_name": {"required": True},
    "promo_from": {"required": True},
    "promo_to": {"required": True},
    "channel": {"required": False},
    "source_sheet": {"required": False, "auto_filled": True},
}
POG_SCHEMA = {
    "item_id": {"required": True},
    "store_id": {"required": True},
    "pog_code": {"required": False},
}


def _xlsx_bytes():
    wb = Workbook()
    ws = wb.active
    ws.append(["Item", "Campaign", "From", "To"])
    ws.append(["P1001", "Promo", "2026-09-01", "2026-09-30"])
    buffer = BytesIO()
    wb.save(buffer)
    wb.close()
    return buffer.getvalue()


def test_xlsx_container_is_validated_before_workbook_processing():
    content = _xlsx_bytes()
    assert _validate_xlsx_container(content, "File CTKM") == content

    with pytest.raises(HTTPException) as exc:
        _validate_xlsx_container(b"this is not an xlsx", "File CTKM")
    assert exc.value.status_code == 422
    assert "không phải workbook .xlsx hợp lệ" in str(exc.value.detail)


def test_manual_mapping_requires_all_required_fields_and_one_to_one_targets():
    df = pd.DataFrame(columns=["Item", "Campaign", "From", "To", "Other"])
    valid = {
        "Item": "item_id",
        "Campaign": "campaign_name",
        "From": "promo_from",
        "To": "promo_to",
    }
    assert validate_manual_mapping(valid, df, FACT_SCHEMA) == valid

    with pytest.raises(ValueError, match="thiếu trường bắt buộc"):
        validate_manual_mapping({"Item": "item_id"}, df, FACT_SCHEMA)

    with pytest.raises(ValueError, match="chỉ được map từ một cột nguồn"):
        validate_manual_mapping({
            "Item": "item_id",
            "Other": "item_id",
            "Campaign": "campaign_name",
            "From": "promo_from",
            "To": "promo_to",
        }, df, FACT_SCHEMA)

    with pytest.raises(ValueError, match="cột nguồn không tồn tại"):
        validate_manual_mapping({**valid, "Missing": "channel"}, df, FACT_SCHEMA)


def test_selected_output_columns_are_canonical_unique_strings():
    schema = {"fact_fields": FACT_SCHEMA, "pog_fields": POG_SCHEMA}
    assert validate_output_columns(["item_id", "campaign_name", "store_id"], schema) == [
        "item_id", "campaign_name", "store_id"
    ]
    with pytest.raises(ValueError, match="field trùng"):
        validate_output_columns(["item_id", "item_id"], schema)
    with pytest.raises(ValueError, match="field không hợp lệ"):
        validate_output_columns(["item_id", "made_up_field"], schema)
    with pytest.raises(ValueError, match="JSON array"):
        validate_output_columns("item_id", schema)


def test_stale_preset_falls_back_to_deterministic_mapping_without_gemini():
    df = pd.DataFrame(columns=["Item", "Campaign", "From", "To"])
    valid = {
        "Item": "item_id",
        "Campaign": "campaign_name",
        "From": "promo_from",
        "To": "promo_to",
    }
    stale = {"Item": "item_id"}

    fake_main_core = SimpleNamespace(
        _get_or_map=lambda *args, **kwargs: valid,
        _ctkm_main_facade_baseline={"get_or_map": lambda *args, **kwargs: valid},
    )
    fake_main = SimpleNamespace(
        _core=fake_main_core,
        _infer_standard_fact_mapping=lambda frame: valid,
        _infer_standard_pog_mapping=lambda frame: {},
        CM=SimpleNamespace(), cfg=SimpleNamespace(), MC=SimpleNamespace(),
    )
    core = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace()),
        _main_mod=fake_main,
    )

    install_mapping_result_contract(core, validate_manual_mapping)
    mapping, source = input_contract._mapping_or_none(
        fake_main, df, FACT_SCHEMA, None, stale, kind="fact"
    )
    assert mapping == valid
    assert source == "standard-fact-after-stale-preset"


def test_invalid_cache_is_recovered_once_then_validated_before_use():
    df = pd.DataFrame(columns=["Item", "Campaign", "From", "To"])
    valid = {
        "Item": "item_id",
        "Campaign": "campaign_name",
        "From": "promo_from",
        "To": "promo_to",
    }
    calls = {"gemini": 0, "save": 0}

    def stale_cache(_sheet, _df, _schema, logs):
        logs.append({"source": "cache", "mapping": {"Item": "item_id"}})
        return {"Item": "item_id"}

    def gemini(*_args, **_kwargs):
        calls["gemini"] += 1
        return SimpleNamespace(mapping=dict(valid))

    fake_mc = SimpleNamespace(
        mapping_result_to_dict_safe=lambda result: {"mapping": dict(result.mapping)},
        save_mapping=lambda *_args, **_kwargs: calls.__setitem__("save", calls["save"] + 1),
    )
    fake_main_core = SimpleNamespace(
        _get_or_map=stale_cache,
        _ctkm_main_facade_baseline={"get_or_map": stale_cache},
    )
    fake_main = SimpleNamespace(
        _core=fake_main_core,
        CM=SimpleNamespace(map_columns_with_gemini=gemini),
        cfg=SimpleNamespace(GEMINI_CONFIG={"prompt_version": "v-test"}),
        MC=fake_mc,
        _infer_standard_fact_mapping=lambda frame: {},
        _infer_standard_pog_mapping=lambda frame: {},
    )
    core = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()), _main_mod=fake_main)

    install_mapping_result_contract(core, validate_manual_mapping)
    logs = []
    result = fake_main_core._get_or_map("Sheet1", df, FACT_SCHEMA, logs)

    assert result == valid
    assert calls == {"gemini": 1, "save": 1}
    assert logs[-1]["source"] == "gemini-cache-recovery"


def test_frontend_retries_only_idempotent_job_reads():
    source = open("frontend/src/main.jsx", encoding="utf-8").read()
    assert "requestMethod === 'GET'" in source
    assert "requestUrl.includes('/api/job/')" in source
    assert "requestUrl.includes('/api/queue/status')" in source
    assert "requestUrl.includes('/api/preview/')" in source
    assert "Không gọi Gemini (mapping chuẩn/đã lưu)" in source
    assert "Nhận diện và kiểm tra mapping cột…" in source
