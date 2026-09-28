import pandas as pd

import main
from backend import input_contract, main_api


FACT_SCHEMA = {
    "item_id": {"required": True},
    "item_name": {"required": False},
    "promo_uom": {"required": False},
    "campaign_name": {"required": True},
    "campaign_detail": {"required": False},
    "promo_from": {"required": True},
    "promo_to": {"required": True},
    "key_channel": {"required": False},
    "channel": {"required": False},
    "normal_price": {"required": False},
    "promo_price": {"required": False},
    "product_type": {"required": False},
}
POG_SCHEMA = {
    "item_id": {"required": True},
    "item_name": {"required": False},
    "store_id": {"required": True},
    "pog_code": {"required": False},
    "location_id": {"required": False},
    "facing": {"required": False},
}


def test_local_fact_value_inference_autoruns_when_required_value_evidence_is_high():
    frame = pd.DataFrame({
        "Mã bí ẩn": ["P1001", "P1002", "P1003", "P1004"],
        "Campaign": ["A", "B", "C", "D"],
        "From": ["2026-09-01"] * 4,
        "To": ["2026-09-30"] * 4,
        "Product Name": ["SP A", "SP B", "SP C", "SP D"],
        "Promo UoM": ["Hộp"] * 4,
        "KEY Channel": ["Offline"] * 4,
        "Channel": ["OFFLINE"] * 4,
    })

    candidate = input_contract._mapping_candidate(
        main, frame, FACT_SCHEMA, None, None, kind="fact"
    )

    assert candidate["source"] == "local-value-fact"
    assert candidate["mapping"]["Mã bí ẩn"] == "item_id"
    assert candidate["mapping"]["Campaign"] == "campaign_name"
    assert candidate["mapping"]["From"] == "promo_from"
    assert candidate["mapping"]["To"] == "promo_to"
    assert candidate["mapping"]["Product Name"] == "item_name"
    assert candidate["mapping"]["Promo UoM"] == "promo_uom"
    assert candidate["mapping"]["KEY Channel"] == "key_channel"
    assert candidate["mapping"]["Channel"] == "channel"
    assert candidate["confidence"] == {"Mã bí ẩn": 1.0}
    assert {"Campaign", "From", "To"}.issubset(set(candidate["trusted_sources"]))
    assert not main_api._mapping_needs_confirmation(candidate, FACT_SCHEMA)


def test_local_fact_medium_value_evidence_requires_confirmation_instead_of_fake_high_confidence():
    frame = pd.DataFrame({
        "Mã bí ẩn": ["P1001", "P1002", "UNKNOWN", "P1004"],
        "Campaign": ["A", "B", "C", "D"],
        "From": ["2026-09-01"] * 4,
        "To": ["2026-09-30"] * 4,
    })

    candidate = input_contract._mapping_candidate(
        main, frame, FACT_SCHEMA, None, None, kind="fact"
    )

    assert candidate["source"] == "local-value-fact"
    assert candidate["confidence"]["Mã bí ẩn"] == 0.75
    assert main_api._mapping_needs_confirmation(candidate, FACT_SCHEMA)


def test_local_fact_does_not_guess_between_two_item_like_columns():
    frame = pd.DataFrame({
        "Mã A": ["P1001", "P1002", "P1003"],
        "Mã B": ["P9001", "P9002", "P9003"],
        "Campaign": ["A", "B", "C"],
        "From": ["2026-09-01"] * 3,
        "To": ["2026-09-30"] * 3,
    })

    candidate = input_contract._mapping_candidate(
        main, frame, FACT_SCHEMA, None, None, kind="fact"
    )

    assert candidate["mapping"] is None
    assert candidate["source"] == "gemini-required"


def test_local_fact_can_infer_exactly_two_ordered_date_columns_from_values():
    frame = pd.DataFrame({
        "Item code": ["P1001", "P1002", "P1003", "P1004"],
        "Campaign": ["A", "B", "C", "D"],
        "Ngày A": ["2026-09-01", "2026-09-05", "2026-09-10", "2026-09-15"],
        "Ngày B": ["2026-09-20", "2026-09-25", "2026-09-28", "2026-09-30"],
    })

    candidate = input_contract._mapping_candidate(
        main, frame, FACT_SCHEMA, None, None, kind="fact"
    )

    assert candidate["source"] == "local-value-fact"
    assert candidate["mapping"]["Ngày A"] == "promo_from"
    assert candidate["mapping"]["Ngày B"] == "promo_to"
    assert candidate["confidence"]["Ngày A"] == 1.0
    assert candidate["confidence"]["Ngày B"] == 1.0
    assert not main_api._mapping_needs_confirmation(candidate, FACT_SCHEMA)


def test_local_fact_refuses_date_pair_when_direction_is_ambiguous():
    frame = pd.DataFrame({
        "Item code": ["P1001", "P1002", "P1003"],
        "Campaign": ["A", "B", "C"],
        "Ngày A": ["2026-09-10", "2026-09-10", "2026-09-10"],
        "Ngày B": ["2026-09-10", "2026-09-10", "2026-09-10"],
    })

    candidate = input_contract._mapping_candidate(
        main, frame, FACT_SCHEMA, None, None, kind="fact"
    )

    assert candidate["mapping"] is None
    assert candidate["source"] == "gemini-required"


def test_local_pog_value_inference_autoruns_for_unique_item_and_store_patterns():
    frame = pd.DataFrame({
        "Cột 1": ["P1001", "P1002", "P1003", "P1004"],
        "Cột 2": ["SGPMC1885", "SGPMC1885", "SGPMC1885", "SGPMC1885"],
        "POGCODE": ["BABY.1885"] * 4,
        "LOCATIONID": [1, 2, 3, 4],
        "TOTALFACING": [2, 2, 1, 1],
    })

    candidate = input_contract._mapping_candidate(
        main, frame, POG_SCHEMA, None, None, kind="pog"
    )

    assert candidate["source"] == "local-value-pog"
    assert candidate["mapping"]["Cột 1"] == "item_id"
    assert candidate["mapping"]["Cột 2"] == "store_id"
    assert candidate["mapping"]["POGCODE"] == "pog_code"
    assert candidate["mapping"]["LOCATIONID"] == "location_id"
    assert candidate["mapping"]["TOTALFACING"] == "facing"
    assert candidate["confidence"]["Cột 1"] == 1.0
    assert candidate["confidence"]["Cột 2"] == 1.0
    assert not main_api._mapping_needs_confirmation(candidate, POG_SCHEMA)


def test_local_pog_refuses_multiple_store_like_candidates():
    frame = pd.DataFrame({
        "SKU": ["P1001", "P1002", "P1003"],
        "Store A": ["SGPMC1885", "SGPMC1885", "SGPMC1885"],
        "Store B": ["SGPMC1886", "SGPMC1886", "SGPMC1886"],
    })

    candidate = input_contract._mapping_candidate(
        main, frame, POG_SCHEMA, None, None, kind="pog"
    )

    assert candidate["mapping"] is None
    assert candidate["source"] == "gemini-required"



def test_local_value_inference_precedes_mapping_cache(monkeypatch):
    frame = pd.DataFrame({
        "Mystery SKU": ["P1001", "P1002", "P1003", "P1004"],
        "Campaign": ["A", "B", "C", "D"],
        "From": ["2026-09-01"] * 4,
        "To": ["2026-09-30"] * 4,
    })

    def cache_must_not_run(*_args, **_kwargs):
        raise AssertionError("High-evidence local inference must precede cache lookup")

    monkeypatch.setattr(
        main, "_get_validated_cached_mapping", cache_must_not_run, raising=False
    )
    candidate = input_contract._mapping_candidate(
        main, frame, FACT_SCHEMA, None, None,
        kind="fact", sheet_name="Monthly",
    )

    assert candidate["source"] == "local-value-fact"
    assert candidate["mapping"]["Mystery SKU"] == "item_id"


def test_low_confidence_cache_hit_still_requires_confirmation(monkeypatch):
    frame = pd.DataFrame({
        "Mystery SKU": ["X1", "X2", "X3"],
        "Campaign": ["A", "B", "C"],
        "From": ["2026-09-01"] * 3,
        "To": ["2026-09-30"] * 3,
    })
    cached_mapping = {
        "Mystery SKU": "item_id",
        "Campaign": "campaign_name",
        "From": "promo_from",
        "To": "promo_to",
    }

    monkeypatch.setattr(main, "_infer_local_value_mapping", lambda *_args: None)
    monkeypatch.setattr(
        main,
        "_get_validated_cached_mapping",
        lambda *_args, **_kwargs: (
            cached_mapping,
            {
                "mapping": cached_mapping,
                "confidence": {
                    "Mystery SKU": 0.62,
                    "Campaign": 0.93,
                    "From": 0.95,
                    "To": 0.95,
                },
                "unmapped": [],
                "source": "cache",
            },
        ),
        raising=False,
    )

    candidate = input_contract._mapping_candidate(
        main, frame, FACT_SCHEMA, None, None,
        kind="fact", sheet_name="Monthly",
    )

    assert candidate["source"] == "cache"
    assert candidate["confidence"]["Mystery SKU"] == 0.62
    assert main_api._mapping_needs_confirmation(candidate, FACT_SCHEMA)
