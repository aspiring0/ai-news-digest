"""A+B 批次：收藏正文快照 / 自定义 RSS 源 / 屏蔽（URL/来源/分类）。"""
from __future__ import annotations

import json

from app import db


# ---------------- 收藏正文快照 ----------------

def test_bookmark_saves_snapshot(clean_db, monkeypatch):
    """收藏时应抓正文存档（原文失效后仍可读）。"""
    db.insert_items([{
        "url": "https://s/1", "title": "会被收藏的文章", "source_name": "S",
        "fetched_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        "score": 66.0, "summary": None,
    }])
    import app.summarizer as summarizer
    monkeypatch.setattr(summarizer, "fetch_article_text", lambda url, rss_summary="": "这是收藏时抓取的正文快照内容。")
    state = db.toggle_bookmark("https://s/1")
    assert state is True
    bm = db.get_bookmarks()[0]
    assert bm["snapshot"] == "这是收藏时抓取的正文快照内容。"


def test_bookmark_snapshot_fallback_to_rss(clean_db, monkeypatch):
    """正文抓取失败时用 RSS 摘要当快照，不留空。"""
    db.insert_items([{
        "url": "https://s/2", "title": "反爬文章", "source_name": "S",
        "fetched_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        "score": 66.0, "summary": "RSS 摘要内容",
    }])
    import app.summarizer as summarizer
    monkeypatch.setattr(summarizer, "fetch_article_text", lambda url, rss_summary="": rss_summary or None)
    db.toggle_bookmark("https://s/2")
    assert db.get_bookmarks()[0]["snapshot"] == "RSS 摘要内容"


# ---------------- 自定义 RSS 源 ----------------

def test_custom_sources_crud(clean_db):
    db.add_custom_source("我的博客", "https://blog.example/feed")
    db.add_custom_source("某社区", "https://c.example/rss")
    # URL 去重
    try:
        db.add_custom_source("重复", "https://blog.example/feed")
        assert False, "重复 URL 应报错"
    except ValueError:
        pass
    srcs = db.list_custom_sources()
    assert len(srcs) == 2 and srcs[0]["name"] == "我的博客"
    db.delete_custom_source(srcs[0]["id"])
    assert len(db.list_custom_sources()) == 1


def test_run_once_fetches_custom_sources(clean_db, monkeypatch):
    """自定义源参与抓取轮（走 parse_rss，按 rss 规则打分）。"""
    db.add_custom_source("我的博客", "https://blog.example/feed")
    from datetime import datetime, timezone
    from app.fetchers.base import NewsItem
    import app.fetch_all as fa

    def fake_parse_rss(url, name, limit=30):
        assert url == "https://blog.example/feed" and name == "我的博客"
        return [NewsItem(title="自定义源文章 Kepler", url="https://blog.example/1", source_name=name)]

    monkeypatch.setattr(fa, "parse_rss", fake_parse_rss)
    monkeypatch.setattr(fa, "FETCHERS", [])
    summary = fa.run_once()
    assert summary["我的博客"]["ok"] is True and summary["我的博客"]["fetched"] == 1
    with db._connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM news_items WHERE source_name='我的博客'").fetchone()[0]
    assert n == 1


def test_api_custom_sources(client):
    r = client.post("/api/custom-sources", json={"name": "测试源", "url": "https://t.example/feed"})
    assert r.status_code == 200
    lst = client.get("/api/custom-sources").json()
    assert any(s["name"] == "测试源" for s in lst["sources"])
    r2 = client.post("/api/custom-sources", json={"name": "x", "url": "notaurl"})
    assert r2.status_code == 400


# ---------------- 屏蔽（不感兴趣） ----------------

def test_blocks_api_and_hot_filter(client):
    """屏蔽 URL / 来源 / 分类 后，热榜不再出现对应故事。"""
    with db._connect() as conn:  # client 共享库：先清残留，保证隔离
        conn.execute("DELETE FROM news_items")
        conn.execute("DELETE FROM blocks")
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)

    def row(url, title, source, score, hours=1.0):
        return {"url": url, "title": title, "source_name": source,
                "published_at": now - timedelta(hours=hours), "fetched_at": now, "score": score}
    db.insert_items([
        row("https://a/1", "Kepler Nova 重大发布", "AIHOT", 90),
        row("https://b/1", "融资八卦 Another Gossip Round", "AIHOT", 80),   # 分类=融资 → 屏蔽分类
        row("https://c/1", "普通事件 Zephyr Orbit", "量子位", 70),          # 来源屏蔽
        row("https://d/1", "普通事件 Zenith Pole", "TechCrunch AI", 60),
    ])
    # 屏蔽：URL（a/1）、分类（融资与公司动态）、来源（量子位）
    assert client.post("/api/blocks", json={"kind": "url", "value": "https://a/1"}).status_code == 200
    assert client.post("/api/blocks", json={"kind": "category", "value": "融资与公司动态"}).status_code == 200
    assert client.post("/api/blocks", json={"kind": "source", "value": "量子位"}).status_code == 200
    blocks = client.get("/api/blocks").json()["blocks"]
    assert len(blocks) == 3

    items, total = db.get_hot_stories()
    titles = [i["title"] for i in items]
    assert any("Zenith" in t for t in titles), "未屏蔽的故事应保留"
    assert not any("Kepler" in t or "Gossip" in t or "Zephyr" in t for t in titles), f"屏蔽项不应出现: {titles}"

    tl_items, tl_total = db.get_timeline()
    assert not any(i["url"].startswith(("https://a/", "https://b/", "https://c/")) for i in tl_items)

    # 解除屏蔽后恢复
    client.request("DELETE", "/api/blocks", json={"kind": "url", "value": "https://a/1"})
    items2, _ = db.get_hot_stories()
    assert any("Kepler" in i["title"] for i in items2)
