"""体验优化组合：RSS 摘要兜底 / 源健康记录。"""
from __future__ import annotations

import json
import types
from datetime import datetime, timezone

from app import db
from app.fetchers import base as fetcher_base


def _dt(h: int) -> datetime:
    return datetime(2026, 10, 13, h, tzinfo=timezone.utc)


# ---------------- 1. RSS 摘要兜底 ----------------

RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
  <item>
    <title>Hello Muse Wonder</title>
    <link>https://x.example/1</link>
    <description>&lt;p&gt;Some &lt;b&gt;bold&lt;/b&gt; text about the item&lt;/p&gt;</description>
    <pubDate>Mon, 13 Oct 2026 08:00:00 GMT</pubDate>
  </item>
  <item>
    <title>No Description Here</title>
    <link>https://x.example/2</link>
  </item>
</channel></rss>
"""


class _FakeResp:
    content = RSS_XML

    def raise_for_status(self):
        pass


def test_parse_rss_extracts_stripped_summary(monkeypatch):
    """RSS description 应提取为纯文本 summary（去 HTML 标签/实体）。"""
    monkeypatch.setattr(fetcher_base.requests, "get", lambda url, headers=None, timeout=None: _FakeResp())
    items = fetcher_base.parse_rss("https://feed", "Test")
    assert items[0].title == "Hello Muse Wonder"
    assert items[0].summary == "Some bold text about the item"
    assert items[1].summary is None


def test_insert_items_stores_and_backfills_summary(clean_db):
    """新条目入库带 summary；同 URL 重复抓取且旧值为空时回填。"""
    db.insert_items([{
        "url": "https://x/1", "title": "T1", "source_name": "S",
        "fetched_at": _dt(8), "score": 66.0, "summary": None,
    }])
    with db._connect() as conn:
        assert conn.execute("SELECT summary FROM news_items WHERE url='https://x/1'").fetchone()["summary"] is None
    # 同 URL 再次入库（带 summary）→ 回填
    added, skipped = db.insert_items([{
        "url": "https://x/1", "title": "T1", "source_name": "S",
        "fetched_at": _dt(9), "score": 66.0, "summary": "RSS 摘要内容",
    }])
    assert (added, skipped) == (0, 1)
    with db._connect() as conn:
        assert conn.execute("SELECT summary FROM news_items WHERE url='https://x/1'").fetchone()["summary"] == "RSS 摘要内容"


def test_api_summary_passes_rss_summary(client, monkeypatch):
    """/api/summary 应把库里的 RSS 摘要作为兜底传给 summarizer。"""
    db.insert_items([{
        "url": "https://y/1", "title": "被反爬的文章", "source_name": "S",
        "fetched_at": _dt(8), "score": 66.0, "summary": "来自 RSS 的内容摘要",
    }])
    captured = {}

    def spy(url, title="", rss_summary="", regenerate=False):
        captured["rss_summary"] = rss_summary
        captured["title"] = title
        return {"core": "c", "plain": "p", "details": "d", "link": url}

    import app.main as main_mod
    monkeypatch.setattr(main_mod.summarizer, "summarize", spy)
    r = client.get("/api/summary?url=https%3A%2F%2Fy%2F1")
    assert r.status_code == 200
    assert captured["rss_summary"] == "来自 RSS 的内容摘要"
    assert captured["title"] == "被反爬的文章"


# ---------------- 2. 源健康 ----------------

def test_run_once_records_source_health(clean_db, monkeypatch):
    """每轮抓取后把各源成功/失败状态写入 meta（供 UI 健康面板）。"""
    ok_src = types.ModuleType("fake_ok")
    ok_src.SOURCE_NAME = "好源"
    ok_src.SCORE_CLASS = "rss"
    ok_src.fetch = lambda: [fetcher_base.NewsItem(title="a b", url="https://h/1", source_name="好源")]
    bad_src = types.ModuleType("fake_bad")
    bad_src.SOURCE_NAME = "坏源"
    bad_src.SCORE_CLASS = "rss"
    bad_src.fetch = lambda: (_ for _ in ()).throw(ConnectionError("被源站重置"))
    import app.fetch_all as fa
    monkeypatch.setattr(fa, "FETCHERS", [ok_src, bad_src])
    fa.run_once()

    raw = db.get_meta("source_health")
    assert raw, "应写入 source_health"
    health = json.loads(raw)
    assert health["好源"]["ok"] is True and health["好源"]["fetched"] == 1
    assert health["坏源"]["ok"] is False and "重置" in health["坏源"]["error"]


def test_api_sources_health(client):
    r = client.get("/api/sources/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True and "sources" in data
