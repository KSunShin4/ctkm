from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from backend import tag_audit_barcode_contract as barcode_contract
from backend import tag_audit_local_ocr_contract as local_ocr


def _line(text, score=0.95, height=12, variant="full", rotation=0):
    return {
        "text": text,
        "score": score,
        "height": height,
        "ocr_variant": variant,
        "ocr_rotation_degrees": rotation,
    }


def _candidate(lines, variant="full", rotation=0):
    return {
        "variant": variant,
        "rotation": rotation,
        "lines": lines,
        "evidence": local_ocr._line_evidence(lines),
    }


def _ocr_result(entries):
    texts = [entry[0] for entry in entries]
    heights = [entry[1] if len(entry) > 1 else 12 for entry in entries]
    scores = [entry[2] if len(entry) > 2 else 0.95 for entry in entries]
    boxes = [
        [[0, 0], [120, 0], [120, height], [0, height]]
        for height in heights
    ]
    return SimpleNamespace(txts=texts, scores=scores, boxes=boxes)


def _jpeg(image):
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("P30766", ["P30766"]),
        ("p 30766", ["P30766"]),
        ("P-30766", ["P30766"]),
        ("P_30766", ["P30766"]),
        ("P:30766", ["P30766"]),
    ],
)
def test_itemid_normalization_accepts_common_print_and_ocr_separators(raw, expected):
    assert local_ocr._canonical_itemids(raw) == expected


def test_itemid_candidates_are_deduplicated_in_reading_order():
    assert local_ocr._canonical_itemids("P30766 p 30766 P25175 P30766") == [
        "P30766",
        "P25175",
    ]


def test_prices_and_numeric_barcodes_do_not_create_itemid_candidates():
    assert local_ocr._canonical_itemids("168750 225000 8850029850726") == []


@pytest.mark.parametrize(
    "text,expected",
    [
        ("500,000VND", [500000]),
        ("500.000 VND", [500000]),
        ("382500", [382500]),
        ("168,750 VNĐ", [168750]),
    ],
)
def test_money_parser_handles_shelf_tag_price_formats(text, expected):
    assert local_ocr._parse_money(text) == expected


def test_money_parser_does_not_treat_13_digit_barcode_as_price():
    assert local_ocr._parse_money("8850029850726") == []


def test_parser_prefers_larger_printed_current_price_over_higher_confidence_old_price(monkeypatch):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("P30766", score=0.99, height=8),
            _line("225,000VND", score=0.99, height=11),
            _line("168,750VND", score=0.72, height=34),
            _line("KM:01/09-30/09", score=0.92, height=8),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    assert observed["promo_price"] == 168750
    assert observed["normal_price"] == 225000


def test_parser_does_not_invent_normal_price_from_duplicate_current_price(monkeypatch):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("P30766"),
            _line("168,750VND", height=34),
            _line("168,750VND", height=20),
            _line("KM:01/09-30/09"),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    assert observed["promo_price"] == 168750
    assert observed["normal_price"] is None


@pytest.mark.parametrize(
    "date_text",
    [
        "KM:01/09-30/09",
        "01/09 TO 30/09",
        "01/09 DEN 30/09",
        "01/09 ĐẾN 30/09",
        "01/09–30/09",
    ],
)
def test_date_range_parser_accepts_common_print_and_ocr_separators(monkeypatch, date_text):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("P30766"),
            _line("168,750VND", height=30),
            _line(date_text),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    assert observed["promo_from"] == "2026-09-01"
    assert observed["promo_to"] == "2026-09-30"


def test_two_digit_printed_year_is_normalized_to_2000s(monkeypatch):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("P30766"),
            _line("168,750VND", height=30),
            _line("KM:01/09/26-30/09/26"),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    assert observed["promo_from"] == "2026-09-01"
    assert observed["promo_to"] == "2026-09-30"


def test_multiple_itemids_remain_ambiguous_even_with_price_and_dates(monkeypatch):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("P30766"),
            _line("P25175"),
            _line("168,750VND", height=30),
            _line("KM:01/09-30/09"),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    assert observed["item_id"] == ""
    assert observed["item_id_candidates"] == ["P30766", "P25175"]
    assert local_ocr._minimum_complete(observed) is False


def test_lower_confidence_single_tag_beats_high_confidence_busy_multi_tag_candidate():
    busy = [
        _line("P30766", score=0.99),
        _line("P25175", score=0.99),
        _line("168,750VND", score=0.99, height=30),
        _line("KM:01/09-30/09", score=0.99),
    ]
    focused = [
        _line("P30766", score=0.70, variant="focus"),
        _line("168,750VND", score=0.70, height=30, variant="focus"),
        _line("KM:01/09-30/09", score=0.70, variant="focus"),
    ]

    best = local_ocr._choose_best_ocr_candidate(
        [_candidate(busy, "full", 0), _candidate(focused, "focus", 0)]
    )

    assert best["variant"] == "focus"
    assert best["evidence"]["itemids"] == ["P30766"]


def test_candidate_with_date_beats_same_item_price_candidate_without_date():
    no_date = [
        _line("P30766", score=0.99, variant="focus"),
        _line("168,750VND", score=0.99, height=30, variant="focus"),
    ]
    with_date = [
        _line("P30766", score=0.75, variant="center"),
        _line("168,750VND", score=0.75, height=30, variant="center"),
        _line("KM:01/09-30/09", score=0.75, variant="center"),
    ]

    best = local_ocr._choose_best_ocr_candidate(
        [_candidate(no_date, "focus", 0), _candidate(with_date, "center", 0)]
    )

    assert best["variant"] == "center"
    assert best["evidence"]["complete"] is True


def test_real_crop_pipeline_short_circuits_when_focus_is_complete(monkeypatch):
    image = np.zeros((1000, 2000, 3), dtype=np.uint8)
    calls = []

    def fake_engine(frame):
        calls.append(frame.shape[:2])
        if frame.shape[:2] == (440, 1120):
            return _ocr_result([
                ("P30766", 8),
                ("168,750VND", 32),
                ("KM:01/09-30/09", 8),
            ])
        return _ocr_result([])

    monkeypatch.setattr(local_ocr, "_get_engine", lambda: fake_engine)

    lines = local_ocr._rapidocr_lines(_jpeg(image))

    assert calls == [(440, 1120)]
    assert {line["ocr_variant"] for line in lines} == {"focus"}
    assert {line["ocr_rotation_degrees"] for line in lines} == {0}


def test_real_crop_pipeline_keeps_full_frame_fallback_when_rois_are_too_small(monkeypatch):
    image = np.zeros((240, 240, 3), dtype=np.uint8)
    calls = []

    def fake_engine(frame):
        calls.append(frame.shape[:2])
        return _ocr_result([
            ("P30766", 8),
            ("168,750VND", 32),
            ("KM:01/09-30/09", 8),
        ])

    monkeypatch.setattr(local_ocr, "_get_engine", lambda: fake_engine)

    lines = local_ocr._rapidocr_lines(_jpeg(image))

    assert calls == [(240, 240)]
    assert {line["ocr_variant"] for line in lines} == {"full"}


def test_real_crop_pipeline_recovers_sideways_target_from_rotated_focus(monkeypatch):
    image = np.zeros((1000, 2000, 3), dtype=np.uint8)
    calls = []

    def fake_engine(frame):
        shape = frame.shape[:2]
        calls.append(shape)
        if shape == (440, 1120):
            return _ocr_result([("P30766", 8)])
        if shape == (700, 1680):
            return _ocr_result([])
        if shape == (1000, 2000):
            return _ocr_result([
                ("P30766", 8),
                ("P25175", 8),
                ("168,750VND", 30),
            ])
        if shape == (1120, 440):
            return _ocr_result([
                ("P30766", 8),
                ("168,750VND", 32),
                ("KM:01/09-30/09", 8),
            ])
        return _ocr_result([])

    monkeypatch.setattr(local_ocr, "_get_engine", lambda: fake_engine)

    lines = local_ocr._rapidocr_lines(_jpeg(image))

    assert (1120, 440) in calls
    assert {line["ocr_variant"] for line in lines} == {"focus"}
    assert {line["ocr_rotation_degrees"] for line in lines} == {90}
    evidence = local_ocr._line_evidence(lines)
    assert evidence["itemids"] == ["P30766"]
    assert evidence["complete"] is True


@pytest.mark.parametrize(
    "value,valid",
    [
        ("14496", False),
        ("1234567", False),
        ("12345678", True),
        ("8850029850726", True),
        ("12345678901234", True),
        ("123456789012345", False),
        ("ABC12345678", False),
    ],
)
def test_backend_barcode_contract_rejects_short_long_and_non_numeric_candidates(value, valid):
    assert bool(barcode_contract._NUMERIC_BARCODE_RE.fullmatch(value)) is valid


@pytest.mark.parametrize(
    "itemids,price,dates,expected",
    [
        (["P30766"], 168750, (None, None), True),
        (["P30766"], 168750, ("2026-09-01", "2026-09-30"), True),
        (["P30766"], None, ("2026-09-01", "2026-09-30"), False),
        (["P30766", "P25175"], 168750, ("2026-09-01", "2026-09-30"), False),
        ([], 168750, ("2026-09-01", "2026-09-30"), False),
    ],
)
def test_gemini_last_resort_gate_requires_unique_local_itemid_and_price(itemids, price, dates, expected):
    observed = {
        "item_id_candidates": itemids,
        "promo_price": price,
        "promo_from": dates[0],
        "promo_to": dates[1],
        "confidence": 0.99,
    }
    assert barcode_contract._local_good_enough(observed) is expected


def test_429_failure_never_shortens_an_existing_longer_gemini_cooldown(monkeypatch):
    monkeypatch.setenv("TAG_AUDIT_GEMINI_429_COOLDOWN_SECONDS", "7")
    monkeypatch.setattr(barcode_contract.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(barcode_contract, "_GEMINI_BLOCK_UNTIL", 200.0)

    barcode_contract._record_gemini_failure(RuntimeError("HTTP 429 rate limit"))

    assert barcode_contract._GEMINI_BLOCK_UNTIL == 200.0


def test_unclassified_remote_500_does_not_create_quota_or_auth_cooldown(monkeypatch):
    monkeypatch.setattr(barcode_contract.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(barcode_contract, "_GEMINI_BLOCK_UNTIL", 0.0)

    barcode_contract._record_gemini_failure(RuntimeError("HTTP 500 upstream error"))

    assert barcode_contract._GEMINI_BLOCK_UNTIL == 0.0


def test_blank_local_observation_is_fail_safe_and_cannot_identify_a_product():
    observed = barcode_contract._blank_local_observation()

    assert observed["item_id"] == ""
    assert observed["item_id_candidates"] == []
    assert observed["promo_price"] is None
    assert observed["promo_from"] is None
    assert observed["promo_to"] is None
    assert barcode_contract._local_good_enough(observed) is False
