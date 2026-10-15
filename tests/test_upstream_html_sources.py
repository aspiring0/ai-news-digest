"""四个 HTML 自补源契约 + 注册表完整性（零网络，mock parse_link_page）。"""
from __future__ import annotations

import importlib

import pytest

from app.fetchers.base import NewsItem


_HTML_SOURCES = [
    ("anthropic", "Anthropic", "https://www.anthropic.com/news",
     r"^/news/[a-z0-9-]+$", 15),
    ("meta_ai", "Meta AI", "https://ai.meta.com/blog/",
     r"^https://ai\.meta\.com/blog/[a-z0-9-]+$", 15),
    ("xai", "xAI", "https://x.ai/news", r"^/news/[a-z0-9-]+$", 15),
    ("cohere", "Cohere", "https://cohere.com/blog", r"^/blog/[a-z0-9-]+$", 12),
]


@pytest.mark.parametrize("mod_name,src_name,page_url,link_re,limit", _HTML_SOURCES)
def test_html_fetcher_contract(monkeypatch, mod_name, src_name, page_url, link_re, limit):
    mod = importlib.import_module(f"app.fetchers.{mod_name}")
    assert mod.SOURCE_NAME == src_name
    assert mod.SCORE_CLASS == "lab"

    sentinel = [NewsItem(title="t", url="https://x/1", source_name=src_name)]
    captured = {}

    def fake_parse(url, name, regex, limit=15):
        captured.update(url=url, name=name, regex=regex, limit=limit)
        return sentinel

    monkeypatch.setattr(mod, "parse_link_page", fake_parse)
    out = mod.fetch()
    assert out is sentinel
    assert captured == {"url": page_url, "name": src_name, "regex": link_re, "limit": limit}


# ---------------- 注册表完整性 ----------------

def test_registry_complete():
    from app.fetchers import FETCHERS

    assert len(FETCHERS) == 30, "拆上游续批后应为 30 个源"
    names = [m.SOURCE_NAME for m in FETCHERS]
    assert len(set(names)) == len(names), "SOURCE_NAME 不得重复"
    for m in FETCHERS:
        assert callable(m.fetch)
        assert isinstance(m.SCORE_CLASS, str)
    # 新源确实在册
    for expect in ("Google Research", "Anthropic", "Meta AI", "xAI", "Cohere",
                   "Mistral AI", "MIT News AI"):
        assert expect in names
