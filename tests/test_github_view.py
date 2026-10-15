"""GitHub 独立视图：三源过滤 / 热度排序 / 屏蔽过滤 / 分页与页面渲染。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app import db


def _row(url, title, source, score, hours=1.0):
    now = datetime.now(timezone.utc)
    return {"url": url, "title": title, "source_name": source,
            "published_at": now - timedelta(hours=hours), "fetched_at": now, "score": score}


def _seed():
    db.insert_items([
        _row("https://github.com/a/trend1", "Trend Repo Alpha Kepler", "GitHub Trending", 90),
        _row("https://github.com/b/rel1", "Release v2 of Zephyr Lib", "GitHub Releases", 80, hours=2),
        _row("https://github.com/c/star1", "Star Rising Nova Tools", "Star 飙升", 70, hours=3),
        _row("https://github.com/d/trend2", "Trend Repo Beta Orbit", "GitHub Trending", 60, hours=4),
        # 非 GitHub 源：不应出现
        _row("https://x/1", "普通新闻 Not Github Source", "Test RSS", 99),
    ])


def test_api_github_filters_and_sorts(client):
    with db._connect() as conn:  # client 共享库：先清残留
        conn.execute("DELETE FROM news_items WHERE url LIKE 'https://github.com/%'")
        conn.execute("DELETE FROM blocks")
    _seed()
    r = client.get("/api/github")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["total"] == 4
    srcs = {i["source_name"] for i in data["items"]}
    assert srcs <= {"GitHub Trending", "GitHub Releases", "Star 飙升"}
    assert "Test RSS" not in srcs
    scores = [i["hot_score"] for i in data["items"]]
    assert scores == sorted(scores, reverse=True)


def test_api_github_respects_blocks(client):
    with db._connect() as conn:
        conn.execute("DELETE FROM news_items WHERE url LIKE 'https://github.com/%'")
        conn.execute("DELETE FROM blocks")
    _seed()
    assert client.post("/api/blocks", json={"kind": "url", "value": "https://github.com/a/trend1"}).status_code == 200
    data = client.get("/api/github").json()
    assert data["total"] == 3
    assert all(i["url"] != "https://github.com/a/trend1" for i in data["items"])


def test_github_page_renders(client):
    with db._connect() as conn:
        conn.execute("DELETE FROM news_items WHERE url LIKE 'https://github.com/%'")
        conn.execute("DELETE FROM blocks")
    _seed()
    r = client.get("/github")
    assert r.status_code == 200
    body = r.text
    assert "Trend Repo Alpha Kepler" in body
    assert "Not Github Source" not in body
    assert "第 1 / 1 页" in body


def test_api_github_pagination_shape(client):
    r = client.get("/api/github?page=99")
    assert r.status_code == 200
    data = r.json()
    assert data["items"] == []  # 超界返回空页而非报错
    assert data["page"] == 99
