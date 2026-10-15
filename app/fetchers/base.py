"""抓取器公共基础：统一数据结构 + RSS 通用解析。"""
from __future__ import annotations

import html as _html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import requests

logger = logging.getLogger("ai-news-oss")

# 统一请求头：带上身份，避免被当成恶意爬虫
HEADERS = {"User-Agent": "ai-news-oss/0.1 (+https://github.com/ai-news-oss)"}

# 单个源超时（秒）：一个源卡住不拖累整轮
FETCH_TIMEOUT = 25

_TAG_RE = re.compile(r"<[^>]+>")


def _clean_summary(s: str) -> str | None:
    """RSS 描述 → 纯文本（去标签/实体/空白，截 600 字）——作正文抓取失败的兜底。"""
    text = _html.unescape(_TAG_RE.sub(" ", s))
    text = " ".join(text.split())
    return text[:600] or None


@dataclass
class NewsItem:
    """单个资讯条目（入库前的统一结构）。"""

    title: str
    url: str
    source_name: str
    published_at: datetime | None = None  # 缺失时入库记抓取时间
    score: float | None = None  # 抓取时按源内位置打分；None 则由 scorer 按类别补
    summary: str | None = None  # RSS 描述（纯文本）：摘要正文抓取失败时兜底


def to_utc(dt: datetime | None) -> datetime | None:
    """把各种时区的时间统一成 UTC（naive 按 UTC 处理）。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_rss(url: str, source_name: str, limit: int = 30) -> list[NewsItem]:
    """通用 RSS/Atom 解析：返回标题/链接/发布时间/RSS 摘要/来源名。"""
    items: list[NewsItem] = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries[:limit]:
            link = (entry.get("link") or "").strip()
            title = (entry.get("title") or "").strip()
            if not link or not title:
                continue
            published = None
            # feedparser 常用时间字段依次尝试
            for key in ("published_parsed", "updated_parsed"):
                parsed = entry.get(key)
                if parsed:
                    published = to_utc(datetime(*parsed[:6], tzinfo=timezone.utc))
                    break
            raw_summary = (entry.get("summary") or entry.get("description") or "").strip()
            items.append(
                NewsItem(
                    title=title,
                    url=link,
                    source_name=source_name,
                    published_at=published,
                    summary=_clean_summary(raw_summary) if raw_summary else None,
                )
            )
    except Exception as e:  # noqa: BLE001 - 单个源失败只记日志
        logger.warning("RSS 解析失败 [%s] %s: %s", source_name, url, e)
    return items


# ---------------- HTML 列表页通用抓取（无 RSS 的厂商官网用） ----------------

# 纯 CTA 文本：不是标题（Meta 无 aria-label 的锚点会落到 "Learn More"）
_CTA_WORDS = {"learn more", "read more", "read", "view more", "了解更多", "查看详情"}

# 粘连截断标记：卡片锚文本常把 标题+分类词/日期/阅读时长 拼成一串
# （"…Verification ProgramAnnouncementsOct 6, 2026We…"）。
# 注意用「小写字母后跟大写」的粘连断言而非 \b——词与词粘连处没有词边界。
_GLUED_CATEGORY_RE = re.compile(
    r"(?<=([a-z\u4e00-\u9fff]))(?=(Announcements?|Research|Company|Engineering|Policy|Events))"
)
_GLUED_MONTH_RE = re.compile(
    r"(?<=([a-z\u4e00-\u9fff]))(?=(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s\d)"
)
_MIN_READ_RE = re.compile(r"\s?\d+\s?min(ute)?s?\s?read.*$", re.IGNORECASE)
# 前缀形态（观察期第一轮实测新增）：卡片锚文本把 日期/分类词/junk 放在标题前
_LEAD_DATE_RE = re.compile(r"^\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}\s*")
_LEAD_CATEGORY_RE = re.compile(r"^(Announcements?|Research|Company|Engineering|Policy|Events)(?=[A-Z])\s*")
_LEAD_JUNK_RE = re.compile(r"^(full article|read article|view article)\s*[:：]\s*", re.IGNORECASE)
# 「分类·日期」复合前缀："Product·Oct 12, 2026Introducing…"（xAI 实测形态）
_LEAD_TAG_DOT_RE = re.compile(r"^[A-Za-z]{2,12}\s*·\s*")


def _slug_title(url: str) -> str:
    """URL slug 转可读标题兜底：/news/claude-4-opus → Claude 4 Opus。"""
    tail = url.rstrip("/").rsplit("/", 1)[-1]
    words = tail.replace("_", "-").split("-")
    return " ".join(w for w in words if w).title()[:120] or url


def _clean_anchor_text(text: str) -> str:
    """清洗卡片锚文本：剥前缀（junk/分类·日期/日期/分类词）+ 去后缀粘连（分类词/月名日期/阅读时长）。"""
    t = " ".join(text.split())
    t = _MIN_READ_RE.sub("", t)
    for _ in range(3):  # 复合前缀可叠加（"Product·Oct 12, 2026标题…"）
        t = _LEAD_JUNK_RE.sub("", t)
        t = _LEAD_TAG_DOT_RE.sub("", t)
        t = _LEAD_DATE_RE.sub("", t)
        t = _LEAD_CATEGORY_RE.sub("", t)
    for pat in (_GLUED_CATEGORY_RE, _GLUED_MONTH_RE):
        m = pat.search(t)
        if m:
            t = t[: m.start()]
    return t.strip()


def _anchor_title(a) -> str:
    """单个锚点的候选标题：aria-label（剥 Read 前缀）→ 清洗后的锚文本。

    aria-label 同样过清洗：Cohere 的标签自带 "full article:" 前缀（实测）。
    """
    label = " ".join((a.get("aria-label") or "").split())
    if label.lower().startswith("read "):
        label = label[5:]
    if label:
        return _clean_anchor_text(label)
    return _clean_anchor_text(a.text_content() or "")


def _usable_title(t: str) -> bool:
    return len(t) >= 12 and t.strip().lower() not in _CTA_WORDS


def parse_link_page(url: str, source_name: str, link_re: str, limit: int = 15) -> list[NewsItem]:
    """HTML 列表页通用抓取（无 RSS 的官网新闻/博客页）。

    - href 去尾斜杠后须命中 link_re（Meta 的绝对 URL 带尾斜杠，实测踩坑）
    - 同 URL 多锚点（卡片标题锚 + CTA 锚）取最长可用标题
    - 标题不可用（CTA 文本/过短/清洗后为空）时用 slug 转标题兜底
    - 页面 200 但 0 命中 → 抛 RuntimeError：页面改版必须进健康面板，不静默
    """
    from urllib.parse import urljoin

    from lxml import html as lxml_html  # 既有依赖（readability-lxml 带入）

    resp = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT)
    resp.raise_for_status()
    tree = lxml_html.fromstring(resp.content)
    pat = re.compile(link_re)
    best: dict[str, str] = {}
    order: list[str] = []
    for a in tree.iter("a"):
        href = (a.get("href") or "").strip().rstrip("/")
        if not href or not pat.search(href):
            continue
        full = urljoin(url, href)
        cand = _anchor_title(a)
        if full not in best:
            order.append(full)
        if _usable_title(cand) and len(cand) > len(best.get(full, "")):
            best[full] = cand
    items = [
        NewsItem(title=(best.get(u) or _slug_title(u))[:120], url=u, source_name=source_name)
        for u in order[:limit]
    ]
    if not items:
        raise RuntimeError(f"{source_name} 列表页 0 命中，页面结构可能已变更: {url}")
    return items
