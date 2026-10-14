"""fetcher 注册完整性 + IT之家 AI 关键词过滤。"""
from __future__ import annotations

from app.fetchers import FETCHERS
from app.fetchers import ithome
from app.fetchers.base import NewsItem


def test_all_fetchers_registered_with_metadata():
    """每个注册的 fetcher 必须带 SOURCE_NAME / SCORE_CLASS / 可调 fetch()，且显示名唯一。"""
    assert len(FETCHERS) >= 20, f"应有至少 20 个源（10 基础 + 6 + 3 + 1），实际 {len(FETCHERS)}"
    names = []
    for mod in FETCHERS:
        assert getattr(mod, "SOURCE_NAME", None), f"{mod.__name__} 缺 SOURCE_NAME"
        assert getattr(mod, "SCORE_CLASS", None), f"{mod.__name__} 缺 SCORE_CLASS"
        assert callable(getattr(mod, "fetch", None)), f"{mod.__name__} 缺 fetch()"
        names.append(mod.SOURCE_NAME)
    assert len(names) == len(set(names)), f"SOURCE_NAME 重复: {sorted(names)}"


def test_direct_upstream_sources_present():
    """v0.3.3/v0.3.4 两批拆出来的直接源必须全部注册。"""
    names = {m.SOURCE_NAME for m in FETCHERS}
    for expect in (
        # v0.3.3
        "Ars Technica AI", "Hacker News AI", "OpenAI", "Google DeepMind", "IT之家", "VentureBeat AI",
        # v0.3.4
        "Tessl", "GitHub Releases", "MarkTechPost",
        # v0.4.3
        "Star 飙升",
    ):
        assert expect in names, f"直接源 {expect} 未注册"


def test_ithome_filters_ai_keywords(monkeypatch):
    """IT之家用全站 feed，必须按 AI 关键词过滤非 AI 内容。"""
    fake = [
        NewsItem(title="OpenAI 发布新模型", url="https://ithome.com/1", source_name="IT之家"),
        NewsItem(title="某手机品牌发布新款充电器", url="https://ithome.com/2", source_name="IT之家"),
        NewsItem(title="人工智能大会在上海开幕", url="https://ithome.com/3", source_name="IT之家"),
        NewsItem(title="GPT-5 使用技巧大全", url="https://ithome.com/4", source_name="IT之家"),
        NewsItem(title="显卡降价促销", url="https://ithome.com/5", source_name="IT之家"),
    ]
    monkeypatch.setattr(ithome, "parse_rss", lambda url, name, limit=60: fake)
    got = ithome.fetch()
    urls = [it.url for it in got]
    assert "https://ithome.com/1" in urls and "https://ithome.com/3" in urls and "https://ithome.com/4" in urls
    assert "https://ithome.com/2" not in urls and "https://ithome.com/5" not in urls
