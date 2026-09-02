import json

import pandas as pd
import pytest

import main


def _schema():
    return {
        "item_id": {"type": "string", "required": True},
        "source_sheet": {"type": "string", "auto_filled": True},
    }


def test_structured_mapping_is_validated(monkeypatch):
    df = pd.DataFrame({"SKU": ["A", "B"], "Other": [1, 2]})
    response = {
        "assignments": [
            {"source_column": "SKU", "canonical_field": "item_id", "confidence": 0.98},
            {"source_column": "Other", "canonical_field": "__UNMAPPED__", "confidence": 0.2},
        ]
    }
    monkeypatch.setattr(main.CM, "_call_gemini_with_retry", lambda prompt, schema: json.dumps(response))

    result = main.CM.map_columns_with_gemini("Sheet1", df, _schema())

    assert result.mapping == {"SKU": "item_id"}
    assert result.unmapped == ["Other"]
    assert result.low_confidence_fields == ["Other"]


def test_mapping_rejects_missing_source_assignment(monkeypatch):
    df = pd.DataFrame({"SKU": ["A"], "Other": [1]})
    response = {
        "assignments": [
            {"source_column": "SKU", "canonical_field": "item_id", "confidence": 0.9}
        ]
    }
    monkeypatch.setattr(main.CM, "_call_gemini_with_retry", lambda prompt, schema: json.dumps(response))

    with pytest.raises(main.CM.GeminiMappingError, match="khong tra assignment"):
        main.CM.map_columns_with_gemini("Sheet1", df, _schema())


def test_mapping_accepts_legacy_bold_unmapped_marker(monkeypatch):
    df = pd.DataFrame({"Other": [1]})
    response = {
        "assignments": [
            {"source_column": "Other", "canonical_field": "**UNMAPPED**", "confidence": 0.8}
        ]
    }
    monkeypatch.setattr(main.CM, "_call_gemini_with_retry", lambda prompt, schema: json.dumps(response))

    result = main.CM.map_columns_with_gemini("Sheet1", df, _schema())

    assert result.mapping == {}
    assert result.unmapped == ["Other"]


def test_response_schema_excludes_auto_filled_fields():
    df = pd.DataFrame({"SKU": ["A"]})
    schema = main.CM._response_schema(df, _schema())
    allowed = schema["properties"]["assignments"]["items"]["properties"]["canonical_field"]["enum"]

    assert "item_id" in allowed
    assert "source_sheet" not in allowed


def test_cache_signature_is_scoped_to_schema_and_prompt_version():
    columns = ["SKU"]
    fact = {"item_id": {"type": "string"}}
    pog = {"store_id": {"type": "string"}}

    assert main.MC.compute_signature(columns, fact, "v2") != main.MC.compute_signature(columns, pog, "v2")
    assert main.MC.compute_signature(columns, fact, "v2") != main.MC.compute_signature(columns, fact, "v3")


def test_manual_mapping_rejects_unknown_target():
    df = pd.DataFrame({"SKU": ["A"]})

    with pytest.raises(ValueError, match="canonical field"):
        main._validate_manual_mapping({"SKU": "invented_field"}, df, _schema())


def test_sample_values_uses_first_five_non_empty_rows():
    df = pd.DataFrame({"Unknown": [None, "P1", "P2", "P3", "P4", "P5", "P6"]})

    samples = main.CM._sample_values(df, "Unknown", 5)

    assert samples == "P1 | P2 | P3 | P4 | P5"


def test_prompt_tells_gemini_to_use_values_not_only_header_names():
    df = pd.DataFrame({"Unknown": ["SGPMC047", "HNPMC100"]})

    prompt = main.CM._build_prompt("Export", df, _schema(), 5)

    assert "khong chi dua vao ten cot" in prompt
    assert "SGPMC047 | HNPMC100" in prompt


def test_key_channel_is_preferred_over_ambiguous_channel_column():
    frame = pd.DataFrame({
        "KEY Channel": ["ALL CHANNEL - EXCEPT MKP"],
        "Channel": ["COMBO ĐI SINH"],
    })

    mapping = main._ensure_channel_mapping({"Channel": "channel"}, frame)

    assert mapping["KEY Channel"] == "channel"
    assert "Channel" not in mapping


def test_normalizer_keeps_integral_excel_identifier_as_text():
    frame = pd.DataFrame({"item_id": [12345.0, "P00123", "#N/A"]})

    result = main.NM.clean_values(frame)

    assert result["item_id"].tolist() == ["12345", "P00123"]
