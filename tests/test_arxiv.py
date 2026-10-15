"""arXiv 论文流接入：fetcher 契约 / paper 打分 / 翻译配额排除 / 注册表。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import db
from app.fetchers import arxiv
from app.fetchers.base import NewsItem


# ---------------- fetcher 契约 ----------------

def test_arxiv_fetches_three_categories_with_limit(monkeypatch):
    calls = []

    def fake_parse_rss(url, name, limit=30):
        calls.append((url, name, limit))
        return [NewsItem(title="Paper One Appears Here", url=f"https://arxiv.org/abs/{url[-6:]}", source_name=name)]

    monkeypatch.setattr(arxiv, "parse_rss", fake_parse_rss)
    items = arxiv.fetch()
    assert len(calls) == 3
    assert all(name == "arXiv" and limit == 15 for _, name, limit in calls)
    assert {u for u, _, _ in calls} == set(arxiv.FEED_URLS)
    assert len(items) == 3


def test_arxiv_dedupes_crosslist_and_strips_suffix(monkeypatch):
    dup = "https://arxiv.org/abs/2610.18877"

    def fake_parse_rss(url, name, limit=30):
        if url.endswith("cs.AI"):
            return [
                NewsItem(title="Lotus: Forecasting (arXiv:2610.18877v1 [cs.LG])", url=dup, source_name=name),
                NewsItem(title="Only In AI Feed Title Long Enough", url="https://arxiv.org/abs/1", source_name=name),
            ]
        return [NewsItem(title="Same Crosslisted Paper (arXiv:2610.18877v2 [cs.AI] UPDATED)", url=dup, source_name=name)]

    monkeypatch.setattr(arxiv, "parse_rss", fake_parse_rss)
    items = arxiv.fetch()
    urls = [i.url for i in items]
    assert urls.count(dup) == 1, "crosslist 同 URL 应去重"
    assert len(items) == 2
    assert all("(arXiv:" not in i.title for i in items), "标题应剥 arXiv ID 后缀"
    assert items[0].title == "Lotus: Forecasting"


# ---------------- paper 打分类 ----------------

def test_paper_score_class():
    from app.scorer import SCORE_RULES, static_score

    assert SCORE_RULES["paper"] == (55, 2, 45)
    assert static_score("paper", 0) == 55
    assert static_score("paper", 2) == 51
    assert static_score("paper", 30) == 45  # 下限
    # 低于新闻源：论文不挤占新闻位
    assert static_score("paper", 0) < static_score("rss", 0)


# ---------------- 翻译配额排除 ----------------

def test_translator_skips_arxiv_sources(clean_db, monkeypatch):
    import app.translator as tr

    now = datetime.now(timezone.utc)
    db.insert_items([
        {"url": "https://arxiv.org/abs/x1", "title": "A Paper Title In English Words",
         "source_name": "arXiv", "fetched_at": now, "published_at": now, "score": 55.0},
        {"url": "https://news/1", "title": "A News Headline In English Words",
         "source_name": "Test RSS", "fetched_at": now, "published_at": now, "score": 66.0},
    ])
    monkeypatch.setattr(tr, "_call_llm_translate",
                        lambda titles: {t: ("中文", "描述") for t in titles})
    n = tr.translate_untranslated()
    assert n == 1, "只应翻译新闻源条目"
    with db._connect() as conn:
        paper = conn.execute("SELECT title_cn FROM news_items WHERE url='https://arxiv.org/abs/x1'").fetchone()
        news = conn.execute("SELECT title_cn FROM news_items WHERE url='https://news/1'").fetchone()
    assert paper["title_cn"] is None, "论文条目不占翻译配额"
    assert news["title_cn"] == "中文"


# ---------------- 注册表 ----------------

def test_registry_includes_arxiv():
    from app.fetchers import FETCHERS

    names = [m.SOURCE_NAME for m in FETCHERS]
    assert len(FETCHERS) == 31
    assert "arXiv" in names
    assert arxiv.SCORE_CLASS == "paper"
