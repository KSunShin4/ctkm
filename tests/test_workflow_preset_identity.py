import copy

import pandas as pd

from backend import input_contract, main_api


def test_preset_key_uses_exact_header_identity():
    first = main_api._preset_key(["Item Code"], ["STOREID"])
    case_changed = main_api._preset_key(["item code"], ["STOREID"])
    spaced = main_api._preset_key(["Item Code "], ["STOREID"])

    assert first.startswith("v3:")
    assert len({first, case_changed, spaced}) == 3


def test_legacy_normalized_preset_is_not_auto_reused(monkeypatch, tmp_path):
    path = tmp_path / "workflow_presets.json"
    legacy_key = "item code::storeid"
    path.write_text(
        '{"item code::storeid":{"ctkm_mapping":{"Item Code":"item_id"},"pog_mapping":{"STOREID":"store_id"}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(main_api, "_PRESETS_PATH", path)

    assert main_api._get_saved_preset(["Item Code"], ["STOREID"]) == {}

    listed = main_api._list_presets()
    assert len(listed) == 1
    assert listed[0]["key"] == legacy_key
    assert listed[0]["legacy"] is True


def test_store_and_get_exact_preset_round_trip(monkeypatch, tmp_path):
    path = tmp_path / "workflow_presets.json"
    monkeypatch.setattr(main_api, "_PRESETS_PATH", path)

    main_api._store_preset(
        ["Item Code", "Campaign"],
        ["STOREID", "ITEMID"],
        ctkm_mapping={"Item Code": "item_id", "Campaign": "campaign_name"},
        pog_mapping={"STOREID": "store_id", "ITEMID": "item_id"},
        output_columns=["item_id", "campaign_name"],
    )

    saved = main_api._get_saved_preset(
        ["Campaign", "Item Code"],
        ["ITEMID", "STOREID"],
    )
    assert saved["ctkm_mapping"]["Item Code"] == "item_id"
    assert saved["pog_mapping"]["STOREID"] == "store_id"
    assert saved["output_columns"] == ["item_id", "campaign_name"]
    assert saved["preset_version"] == 3
    assert saved["schema_signature"]

    assert main_api._get_saved_preset(["item code", "Campaign"], ["STOREID", "ITEMID"]) == {}



def test_v2_preset_is_listed_but_never_auto_reused(monkeypatch, tmp_path):
    path = tmp_path / "workflow_presets.json"
    path.write_text(
        '{"v2:old":{"preset_version":2,"ctkm_columns":["Item Code"],'
        '"pog_columns":["STOREID"],"ctkm_mapping":{"Item Code":"item_id"},'
        '"pog_mapping":{"STOREID":"store_id"}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(main_api, "_PRESETS_PATH", path)

    assert main_api._get_saved_preset(["Item Code"], ["STOREID"]) == {}

    listed = main_api._list_presets()
    assert listed[0]["preset_version"] == 2
    assert listed[0]["legacy"] is True
    assert listed[0]["compatible"] is False


def test_schema_contract_change_invalidates_same_header_preset(monkeypatch, tmp_path):
    path = tmp_path / "workflow_presets.json"
    monkeypatch.setattr(main_api, "_PRESETS_PATH", path)

    ctkm_columns = ["sku", "campaign", "from", "to"]
    pog_columns = ["sku", "store"]
    main_api._store_preset(
        ctkm_columns,
        pog_columns,
        ctkm_mapping={
            "sku": "item_id",
            "campaign": "campaign_name",
            "from": "promo_from",
            "to": "promo_to",
        },
        pog_mapping={"sku": "item_id", "store": "store_id"},
    )
    assert main_api._get_saved_preset(ctkm_columns, pog_columns)

    original = main_api._main_mod.SCHEMA
    changed = copy.deepcopy(original)
    changed["fact_fields"]["__contract_probe__"] = {
        "type": "string", "required": False, "auto_filled": False,
    }
    monkeypatch.setattr(main_api._main_mod, "SCHEMA", changed)

    # Exact same file headers are not enough once the canonical contract changes.
    assert main_api._get_saved_preset(ctkm_columns, pog_columns) == {}
    listed = main_api._list_presets()
    assert listed[0]["preset_version"] == 3
    assert listed[0]["compatible"] is False


def test_confirmed_preset_round_trip_is_saved_preset_on_next_run(monkeypatch, tmp_path):
    path = tmp_path / "workflow_presets.json"
    monkeypatch.setattr(main_api, "_PRESETS_PATH", path)

    ctkm_columns = ["sku", "campaign", "from", "to"]
    pog_columns = ["sku", "store"]
    ctkm_mapping = {
        "sku": "item_id",
        "campaign": "campaign_name",
        "from": "promo_from",
        "to": "promo_to",
    }
    pog_mapping = {"sku": "item_id", "store": "store_id"}
    main_api._store_preset(
        ctkm_columns, pog_columns,
        ctkm_mapping=ctkm_mapping, pog_mapping=pog_mapping,
    )

    saved = main_api._get_saved_preset(ctkm_columns, pog_columns)
    fact = pd.DataFrame([{
        "sku": "P1001",
        "campaign": "Promo",
        "from": "2026-09-01",
        "to": "2026-09-30",
    }])
    pog = pd.DataFrame([{"sku": "P1001", "store": "SGPMC0001"}])

    resolved_fact, fact_source = input_contract._mapping_or_none(
        main_api._main_mod,
        fact,
        main_api._main_mod.SCHEMA["fact_fields"],
        None,
        saved["ctkm_mapping"],
        kind="fact",
    )
    resolved_pog, pog_source = input_contract._mapping_or_none(
        main_api._main_mod,
        pog,
        main_api._main_mod.SCHEMA["pog_fields"],
        None,
        saved["pog_mapping"],
        kind="pog",
    )

    assert resolved_fact == ctkm_mapping
    assert resolved_pog == pog_mapping
    assert fact_source == "saved-preset"
    assert pog_source == "saved-preset"
