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
