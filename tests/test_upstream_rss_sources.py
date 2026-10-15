"""六个平台 RSS 源：透传参数契约 + lab 打分类。"""
from __future__ import annotations

import pytest


_RSS_SOURCES = [
    ("google_research", "Google Research", "https://research.google/blog/rss/", 25),
    ("microsoft_research", "Microsoft Research",
     "https://www.microsoft.com/en-us/research/feed/", 15),
    ("azure_ai", "Azure AI Blog", "https://azure.microsoft.com/en-us/blog/feed/", 15),
    ("mistral", "Mistral AI", "https://mistral.ai/rss.xml", 25),
    ("nvidia", "NVIDIA Blog", "https://blogs.nvidia.com/feed/", 15),
    ("mit_ai", "MIT News AI",
     "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml", 20),
]


@pytest.mark.parametrize("mod_name,src_name,feed_url,limit", _RSS_SOURCES)
def test_rss_fetcher_contract(monkeypatch, mod_name, src_name, feed_url, limit):
    from app.fetchers import google_research  # noqa: F401  确保包可导入
    import importlib

    mod = importlib.import_module(f"app.fetchers.{mod_name}")
    assert mod.SOURCE_NAME == src_name
    assert mod.SCORE_CLASS == "lab"

    from app.fetchers.base import NewsItem
    sentinel = [NewsItem(title="t", url="https://x/1", source_name=src_name)]
    captured = {}

    def fake_parse_rss(url, name, limit=30):
        captured.update(url=url, name=name, limit=limit)
        return sentinel

    monkeypatch.setattr(mod, "parse_rss", fake_parse_rss)
    out = mod.fetch()
    assert out is sentinel
    assert captured == {"url": feed_url, "name": src_name, "limit": limit}


# ---------------- scorer：lab 类 ----------------

def test_lab_score_class():
    from app.scorer import SCORE_RULES, static_score

    assert SCORE_RULES["lab"] == (68, 2, 50)
    assert static_score("lab", 0) == 68
    assert static_score("lab", 3) == 62
    # 下限
    assert static_score("lab", 20) == 50
