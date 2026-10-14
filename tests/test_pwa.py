"""PWA：manifest / service worker / 静态资源。"""
from __future__ import annotations


def test_manifest_served(client):
    r = client.get("/manifest.json")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "AI 资讯聚合"
    assert data["start_url"] == "/hot"
    assert any("192" in i["sizes"] for i in data["icons"])


def test_service_worker_served(client):
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "addEventListener" in r.text
    assert "javascript" in r.headers.get("content-type", "")


def test_offline_page_served(client):
    r = client.get("/static/offline.html")
    assert r.status_code == 200
    assert "离线" in r.text


def test_pwa_links_in_page(client):
    html = client.get("/hot").text
    assert 'rel="manifest"' in html
    assert "/sw.js" in html or "serviceWorker" in html
