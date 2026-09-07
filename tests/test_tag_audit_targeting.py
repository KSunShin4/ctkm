import numpy as np

from backend import tag_audit_local_ocr_contract as local_ocr


def _line(text, score=0.95, height=12, variant="full", rotation=0):
    return {
        "text": text,
        "score": score,
        "height": height,
        "ocr_variant": variant,
        "ocr_rotation_degrees": rotation,
    }


def _candidate(lines, variant, rotation):
    return {
        "variant": variant,
        "rotation": rotation,
        "lines": lines,
        "evidence": local_ocr._line_evidence(lines),
    }


def test_focus_and_center_crops_match_scanner_targeting_contract():
    image = np.zeros((1000, 2000, 3), dtype=np.uint8)
    focus = local_ocr._focus_crop(image)
    center = local_ocr._center_crop(image)

    assert focus is not None
    assert center is not None
    assert focus.shape[:2] == (440, 1120)
    assert center.shape[:2] == (700, 1680)


def test_structured_single_tag_beats_busy_multi_tag_frame():
    full_lines = [
        _line("P03845"),
        _line("P20383"),
        _line("57,750VND", height=30),
        _line("KM:01/09-30/09"),
    ]
    center_lines = [
        _line("P03845", variant="center", rotation=90),
        _line("57,750VND", height=30, variant="center", rotation=90),
        _line("77,000VND", height=10, variant="center", rotation=90),
        _line("KM:01/09-30/09", variant="center", rotation=90),
    ]

    best = local_ocr._choose_best_ocr_candidate([
        _candidate(full_lines, "full", 0),
        _candidate(center_lines, "center", 90),
    ])

    assert best is not None
    assert best["variant"] == "center"
    assert best["rotation"] == 90
    assert best["evidence"]["complete"] is True
    assert best["evidence"]["itemids"] == ["P03845"]


def test_equivalent_complete_candidate_prefers_tight_focus_region():
    focus_lines = [
        _line("P25175", variant="focus"),
        _line("MUA 1 TANG 1", variant="focus"),
        _line("500,000VND", height=30, variant="focus"),
        _line("KM:06/09-15/09", variant="focus"),
    ]
    center_lines = [
        _line("P25175", variant="center"),
        _line("MUA 1 TANG 1", variant="center"),
        _line("500,000VND", height=30, variant="center"),
        _line("KM:06/09-15/09", variant="center"),
    ]

    best = local_ocr._choose_best_ocr_candidate([
        _candidate(center_lines, "center", 0),
        _candidate(focus_lines, "focus", 0),
    ])

    assert best is not None
    assert best["variant"] == "focus"
    assert best["evidence"]["itemids"] == ["P25175"]


def test_complete_upright_full_frame_is_not_rotated_unnecessarily():
    full_lines = [
        _line("P03845"),
        _line("57,750VND", height=30),
        _line("KM:01/09-30/09"),
    ]
    rotated_lines = [
        _line("P03845", variant="full", rotation=90),
        _line("57,750VND", height=30, variant="full", rotation=90),
        _line("KM:01/09-30/09", variant="full", rotation=90),
    ]

    best = local_ocr._choose_best_ocr_candidate([
        _candidate(full_lines, "full", 0),
        _candidate(rotated_lines, "full", 90),
    ])

    assert best is not None
    assert best["rotation"] == 0


def test_parser_surfaces_target_region_and_rotation_diagnostics(monkeypatch):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("P03845", variant="focus", rotation=270),
            _line("57,750VND", height=30, variant="focus", rotation=270),
            _line("77,000VND", height=10, variant="focus", rotation=270),
            _line("KM:01/09-30/09", variant="focus", rotation=270),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    assert observed["item_id"] == "P03845"
    assert observed["ocr_target_region"] == "focus"
    assert observed["ocr_rotation_degrees"] == 270
    assert local_ocr._minimum_complete(observed) is True