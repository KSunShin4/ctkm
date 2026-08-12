import pandas as pd
import asyncio
import pytest

from backend import main_api


class FakeUpload:
    def __init__(self, content):
        self.content = content

    async def read(self, size):
        return self.content[:size]


def test_upload_limit_rejects_oversized_file():
    with pytest.raises(main_api.HTTPException) as exc:
        asyncio.run(main_api._read_upload_limited(FakeUpload(b"12345"), 4, "Test"))
    assert exc.value.status_code == 413


def test_identical_expiration_file_is_parsed_once(monkeypatch):
    calls = []
    frame = pd.DataFrame({"ITEMID": ["P1"], "BATCHNUMER": ["B1"], "EXPDATE": ["01/01/2030"]})

    def fake_loader(content):
        calls.append(content)
        return frame, "Export"

    monkeypatch.setattr(main_api._expiration_mod, "load_expiration_export", fake_loader)
    with main_api._expiration_cache_lock:
        main_api._expiration_cache.clear()

    first_frame, first_sheet, first_hit = main_api._load_expiration_cached(b"same workbook")
    second_frame, second_sheet, second_hit = main_api._load_expiration_cached(b"same workbook")

    assert first_frame is second_frame
    assert first_sheet == second_sheet == "Export"
    assert first_hit is False
    assert second_hit is True
    assert calls == [b"same workbook"]
