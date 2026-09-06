import asyncio

from backend import main_api  # installs production scanner wrappers
from backend import tag_audit_contract


def _row(**overrides):
    row = {
        "item_id": "P30766",
        "item_name": "Sản phẩm thử nghiệm",
        "campaign_name": "FULL MONTH",
        "campaign_detail": "GIẢM 25%",
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "normal_price": 225000,
        "promo_price": 168750,
        "expected_action": "gan_tem",
        "source_sheet": "Gắn tem",
        "key_channel": "All channel",
        "channel": "Offline",
    }
    row.update(overrides)
    return row


def _observed(**overrides):
    observed = {
        "item_id": "P30766",
        "item_id_candidates": ["P30766"],
        "barcode": "",
        "product_name": "Sản phẩm thử nghiệm",
        "promo_text": "GIẢM 25%",
        "normal_price": 225000,
        "promo_price": 168750,
        "promo_from": "2026-09-01",
        "promo_to": "2026-09-30",
        "raw_text": "P30766",
        "confidence": 0.95,
    }
    observed.update(overrides)
    return observed


def _route(path: str, method: str):
    matches = [
        route for route in main_api.app.routes
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", None) or set())
    ]
    assert len(matches) == 1
    return matches[0]


def test_same_sku_indistinguishable_different_channels_requires_review():
    rows = [
        _row(key_channel="All channel", channel="Offline"),
        _row(key_channel="All channel", channel="Online"),
    ]

    result = tag_audit_contract.compare_observation(rows, _observed())

    assert result["verdict"]["code"] == "review_ambiguous"
    assert result["progress_eligible"] is False
    assert result["check_key"] is None
    assert "promotion_identity" in result["mismatches"]


def test_channel_formatting_variants_do_not_create_false_ambiguity():
    rows = [
        _row(key_channel="All channel", channel="Offline"),
        _row(key_channel="ALL CHANNEL", channel=" offline "),
    ]

    result = tag_audit_contract.compare_observation(rows, _observed())

    assert result["verdict"]["code"] == "correct"
    assert result["progress_eligible"] is True


def test_get_context_reuses_uploaded_workbook_context(monkeypatch):
    uploaded = {
        "source_key": "upload:test",
        "source": "uploaded-workbook",
        "job_id": None,
        "month": "2026-09",
        "rows": [_row()],
    }
    calls = {"current": 0, "latest": 0}

    def fake_current(core_module):
        calls["current"] += 1
        assert core_module is main_api
        return uploaded

    def forbidden_latest(core_module, *, force=False):
        calls["latest"] += 1
        raise AssertionError("GET context must not replace an uploaded workbook with latest-job")

    monkeypatch.setattr(tag_audit_contract, "_current_context", fake_current)
    monkeypatch.setattr(tag_audit_contract, "_cache_latest_job", forbidden_latest)

    endpoint = _route("/api/tag-audit/context", "GET").endpoint
    payload = asyncio.run(endpoint(_admin="admin"))

    assert calls == {"current": 1, "latest": 0}
    assert payload["source"] == "uploaded-workbook"
    assert payload["item_count"] == 1
    assert payload["context_id"].startswith("ctx_")


def test_scanner_pipeline_installs_perception_wrappers_once():
    assert tag_audit_contract._local_ocr_contract_v1 is True
    assert tag_audit_contract._itemid_primary_contract_v1 is True
    assert tag_audit_contract._barcode_contract_v1 is True
    assert main_api.app.state.tag_audit_progress_contract_v1 is True

    context = tag_audit_contract._context_payload({
        "source": "uploaded-workbook",
        "job_id": None,
        "month": "2026-09",
        "rows": [_row()],
    })
    assert context["ocr_primary"] == "rapidocr"
    assert context["image_preprocessor"] == "opencv-clahe-v1"
    assert context["barcode_fallback"] == "zxingcpp"
    assert context["progress_scope"] == "gan_tem_only"
