from pathlib import Path

from fastapi.testclient import TestClient

from backend import main_api


def test_scan_tem_returns_frontend_index_when_built(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    index = dist / "index.html"
    index.write_text("<!doctype html><html><body>scan-tem-marker</body></html>", encoding="utf-8")
    monkeypatch.setattr(main_api, "_FRONTEND_DIST", dist)

    client = TestClient(main_api.app)
    response = client.get("/scan-tem")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "scan-tem-marker" in response.text


def test_scan_tem_trailing_slash_returns_frontend_index_when_built(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("scan-tem-marker", encoding="utf-8")
    monkeypatch.setattr(main_api, "_FRONTEND_DIST", dist)

    client = TestClient(main_api.app)
    response = client.get("/scan-tem/")

    assert response.status_code == 200
    assert "scan-tem-marker" in response.text
