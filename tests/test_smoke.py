"""冒烟测试：服务能起、关键页面能渲染（对应 CHANGELOG 承诺的 CI 冒烟）。"""
from __future__ import annotations

from app import __version__


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["version"] == __version__
    assert isinstance(data["news_count"], int) and data["news_count"] >= 3


def test_index_redirects_to_hot(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (307, 302)
    assert r.headers["location"].endswith("/hot")


def test_six_pages_render(client):
    for path in ("/hot", "/timeline", "/daily", "/topics", "/bookmarks", "/settings"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} 应返回 200，实际 {r.status_code}"
        assert "AI 资讯聚合" in r.text, f"{path} 应渲染出页面标题"


def test_hot_shows_seeded_item(client):
    r = client.get("/hot")
    assert "OpenAI 发布 GPT-5 对齐研究报告" in r.text


def test_timeline_pagination(client):
    r1 = client.get("/timeline")
    assert r1.status_code == 200
    assert "第 1 /" in r1.text  # 分页信息渲染
    # 越界页码自动收敛到第 1 页
    r2 = client.get("/timeline?page=0")
    assert r2.status_code == 200


def test_bookmark_toggle_roundtrip(client):
    url = "https://example.com/news/1"
    r1 = client.post("/api/bookmark", json={"url": url})
    assert r1.status_code == 200 and r1.json()["bookmarked"] is True
    page = client.get("/bookmarks")
    assert "OpenAI 发布 GPT-5 对齐研究报告" in page.text
    r2 = client.post("/api/bookmark", json={"url": url})
    assert r2.json()["bookmarked"] is False
    r3 = client.post("/api/bookmark", json={"url": ""})
    assert r3.status_code == 400
