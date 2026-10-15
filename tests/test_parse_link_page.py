"""parse_link_page 单测：HTML 列表页提取管线全分支（零网络，fixture 覆盖实测踩过的坑）。"""
from __future__ import annotations

import pytest

from app.fetchers import base
from app.fetchers.base import NewsItem, parse_link_page


def _mock_page(monkeypatch, html: str):
    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        @property
        def content(self):
            # 补 charset 声明：lxml 对无声明字节按 latin-1 解析，· 会变 Â·
            # （真实站点都有声明，四源实测通过；此处模拟真实响应）
            return ('<meta charset="utf-8">' + html).encode("utf-8")

    monkeypatch.setattr(base.requests, "get", lambda url, **kw: _Resp())


# ── 1. aria-label 优先 + 剥 "Read " 前缀（Meta 形态） ──

def test_aria_label_preferred(monkeypatch):
    _mock_page(monkeypatch, """
    <html><body>
    <a aria-label="Read Reimagining Independence: Meta AI Models at Work"
       href="https://ai.meta.com/blog/reimagining-independence/">card</a>
    </body></html>""")
    items = parse_link_page("https://ai.meta.com/blog/", "Meta AI",
                            r"^https://ai\.meta\.com/blog/[a-z0-9-]+$", limit=5)
    assert items == [NewsItem(
        title="Reimagining Independence: Meta AI Models at Work",
        url="https://ai.meta.com/blog/reimagining-independence", source_name="Meta AI")]


# ── 2. 粘连清洗：标题+分类词（无词边界）、标题+月名日期、阅读时长 ──

def test_glued_category_and_month_cut(monkeypatch):
    _mock_page(monkeypatch, """
    <html><body>
    <a href="/news/cyber-verification">Expanding the Cyber Verification ProgramAnnouncementsOct 6, 2026We are expanding</a>
    <a href="/blog/change-mgmt">AI change management: A human-centric approachSep 22, 20268 min read</a>
    <a href="/blog/multilingual">Multilingual Bridges: How Data Mixing Unlocks Reasoning 12 min read</a>
    </body></html>""")
    items = parse_link_page("https://www.anthropic.com/news", "Anthropic",
                            r"^/(news|blog)/[a-z0-9-]+$", limit=5)
    by = {i.url: i.title for i in items}
    assert by["https://www.anthropic.com/news/cyber-verification"] == \
        "Expanding the Cyber Verification Program"
    assert by["https://www.anthropic.com/blog/change-mgmt"] == \
        "AI change management: A human-centric approach"
    # 普通空格分隔的阅读时长也剥掉，标题本体保留
    assert by["https://www.anthropic.com/blog/multilingual"] == \
        "Multilingual Bridges: How Data Mixing Unlocks Reasoning"


# ── 2b. 前缀形态（观察期第一轮实测：日期/分类/junk 在标题前） ──

def test_lead_prefixes_stripped(monkeypatch):
    _mock_page(monkeypatch, """
    <html><body>
    <a href="/news/cyber-2">Oct 6, 2026AnnouncementsExpanding the Cyber Verification Program again</a>
    <a href="/news/grok-voice">Oct 14, 2026Introducing Grok Voice 3.0 for everyone</a>
    <a href="/blog/north-2">full article: North 2: Enterprise AI without compromise</a>
    <a href="/news/x-sub">Product\u00b7Oct 12, 2026Introducing The X Subscription tier</a>
    </body></html>""")
    items = parse_link_page("https://x.ai/news", "xAI", r"^/(news|blog)/[a-z0-9-]+$", limit=5)
    by = {i.url: i.title for i in items}
    assert by["https://x.ai/news/cyber-2"] == "Expanding the Cyber Verification Program again"
    assert by["https://x.ai/news/grok-voice"] == "Introducing Grok Voice 3.0 for everyone"
    assert by["https://x.ai/blog/north-2"] == "North 2: Enterprise AI without compromise"
    assert by["https://x.ai/news/x-sub"] == "Introducing The X Subscription tier"


def test_aria_label_also_cleaned(monkeypatch):
    """aria-label 自带 junk 前缀（Cohere 实测形态）也要清洗。"""
    _mock_page(monkeypatch, """
    <html><body>
    <a aria-label="full article: North 2 Enterprise AI" href="/blog/n2/">
    </body></html>""")
    items = parse_link_page("https://cohere.com/blog", "Cohere", r"^/blog/[a-z0-9-]+$", limit=5)
    assert items[0].title == "North 2 Enterprise AI"


# ── 3. 同 URL 多锚点：标题锚 + CTA 锚，取最长可用标题 ──

def test_card_and_cta_anchors_same_url(monkeypatch):
    _mock_page(monkeypatch, """
    <html><body>
    <a href="/news/grok-4"><h3>Grok 4 is the most intelligent model in the world today</h3></a>
    <a href="/news/grok-4/">Learn More</a>
    </body></html>""")
    items = parse_link_page("https://x.ai/news", "xAI", r"^/news/[a-z0-9-]+$", limit=5)
    assert len(items) == 1  # 尾斜杠归一 + URL 去重
    assert items[0].title == "Grok 4 is the most intelligent model in the world today"


# ── 4. CTA/过短标题 → slug 兜底 ──

def test_cta_only_anchor_falls_back_to_slug(monkeypatch):
    _mock_page(monkeypatch, """
    <html><body>
    <a href="https://ai.meta.com/blog/brain2qwordy-path/">Learn More</a>
    <a href="https://ai.meta.com/blog/short-one/">Ab</a>
    </body></html>""")
    items = parse_link_page("https://ai.meta.com/blog/", "Meta AI",
                            r"^https://ai\.meta\.com/blog/[a-z0-9-]+$", limit=5)
    by = {i.url: i.title for i in items}
    assert by["https://ai.meta.com/blog/brain2qwordy-path"] == "Brain2Qwordy Path"
    assert by["https://ai.meta.com/blog/short-one"] == "Short One"


# ── 5. 0 命中抛 RuntimeError（页面改版进健康面板，不静默） ──

def test_zero_hits_raises(monkeypatch):
    _mock_page(monkeypatch, "<html><body><a href='/other/x'>t</a></body></html>")
    with pytest.raises(RuntimeError, match="0 命中"):
        parse_link_page("https://x.ai/news", "xAI", r"^/news/[a-z0-9-]+$", limit=5)


# ── 6. limit 截断 + 保序 ──

def test_limit_and_order(monkeypatch):
    links = "".join(f'<a href="/news/item-{i}/">A sufficiently long title number {i} here</a>'
                    for i in range(5))
    _mock_page(monkeypatch, f"<html><body>{links}</body></html>")
    items = parse_link_page("https://x.ai/news", "xAI", r"^/news/[a-z0-9-]+$", limit=3)
    assert [i.url.rsplit("/", 1)[-1] for i in items] == ["item-0", "item-1", "item-2"]
