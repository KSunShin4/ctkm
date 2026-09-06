import pytest

from backend import tag_audit_local_ocr_contract as local_ocr


def _line(text, score=0.95, height=12):
    return {"text": text, "score": score, "height": height}


@pytest.mark.parametrize(
    ("item_id", "promo_price", "normal_price"),
    [
        ("P03845", 57750, 77000),
        ("P20383", 175500, 195000),
        ("P17822", 46400, 58000),
    ],
)
def test_known_pharmacity_template_values_parse_deterministically(
    monkeypatch, item_id, promo_price, normal_price
):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line(f"{normal_price:,}VND", height=9),
            _line("KM:01/09-30/09", height=8),
            _line(item_id, height=8),
            _line(f"{promo_price:,}VND", height=31),
            _line("GIAM 20%", height=10),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    assert observed["item_id"] == item_id
    assert observed["promo_price"] == promo_price
    assert observed["normal_price"] == normal_price
    assert observed["promo_from"] == "2026-09-01"
    assert observed["promo_to"] == "2026-09-30"
    assert local_ocr._minimum_complete(observed) is True


def test_price_selection_depends_on_printed_size_not_ocr_line_order(monkeypatch):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("46,400VND", height=32),
            _line("P17822", height=8),
            _line("KM:01/09-30/09", height=7),
            _line("58,000VND", height=10),
        ],
    )

    first = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("58,000VND", height=10),
            _line("KM:01/09-30/09", height=7),
            _line("P17822", height=8),
            _line("46,400VND", height=32),
        ],
    )
    second = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    assert (first["promo_price"], first["normal_price"]) == (46400, 58000)
    assert (second["promo_price"], second["normal_price"]) == (46400, 58000)


def test_ean13_text_is_not_mistaken_for_a_price(monkeypatch):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("P03845", height=8),
            _line("57,750VND", height=30),
            _line("77,000VND", height=10),
            _line("8850029850726", height=40),
            _line("KM:01/09-30/09", height=8),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    assert observed["promo_price"] == 57750
    assert observed["normal_price"] == 77000


def test_missing_old_price_stays_missing_instead_of_being_invented(monkeypatch):
    monkeypatch.setattr(
        local_ocr,
        "_rapidocr_lines",
        lambda image: [
            _line("P17822", height=8),
            _line("46,400VND", height=30),
            _line("KM:01/09-30/09", height=8),
        ],
    )

    observed = local_ocr.extract_tag_with_rapidocr(b"image", "2026-09")

    assert observed["promo_price"] == 46400
    assert observed["normal_price"] is None
    assert observed["item_id"] == "P17822"
    assert local_ocr._minimum_complete(observed) is True
