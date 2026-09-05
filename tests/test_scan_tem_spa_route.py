import asyncio

from starlette.requests import Request

from backend import main_api


def _request(path: str) -> Request:
    return Request({
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    })


async def _fallback(_request):
    raise AssertionError("scan-tem request should not fall through")


def _exercise(path: str, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<!doctype html><html><body>scan-tem-marker</body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr(main_api, "_FRONTEND_DIST", dist)

    response = asyncio.run(main_api._scan_tem_spa_entry(_request(path), _fallback))
    assert response.status_code == 200
    assert response.media_type == "text/html"
    assert response.path == str(dist / "index.html")


def test_scan_tem_returns_frontend_index_when_built(tmp_path, monkeypatch):
    _exercise("/scan-tem", tmp_path, monkeypatch)


def test_scan_tem_trailing_slash_returns_frontend_index_when_built(tmp_path, monkeypatch):
    _exercise("/scan-tem/", tmp_path, monkeypatch)
