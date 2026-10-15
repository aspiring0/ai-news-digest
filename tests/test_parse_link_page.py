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
            return html.encode("utf-8")

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
