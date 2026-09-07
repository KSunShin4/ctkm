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


def test_center_crop_matches_scanner_target_frame_and_preserves_full_fallback():
    image = np.zeros((1000, 2000, 3), dtype=np.uint8)
    cropped = local_ocr._center_crop(image)

    assert cropped is not None
    assert cropped.shape[:2] == (700, 1680)


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
            _line("P03845", variant="center", rotation=270),
            _line("57,750VND", height=30, variant="center", rotation=270),
            _line("77,000VND", height=10, variant="center", rotation=270),
            _line("KM:01/09-30/09", variant="center", rotation=270),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    assert observed["item_id"] == "P03845"
    assert observed["ocr_target_region"] == "center"
    assert observed["ocr_rotation_degrees"] == 270
    assert local_ocr._minimum_complete(observed) is True
