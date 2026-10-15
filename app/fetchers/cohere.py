"""Cohere 官方博客（无 RSS，HTML 抓取）。探测 2026-10-15：200，24 条。

页面约 1MB 偏重，limit 压小到 12；标题带"日期+阅读时长"粘连，
parse_link_page 清洗规则覆盖。
"""
from .base import NewsItem, parse_link_page

SOURCE_NAME = "Cohere"
PAGE_URL = "https://cohere.com/blog"
LINK_RE = r"^/blog/[a-z0-9-]+$"
SCORE_CLASS = "lab"


def fetch() -> list[NewsItem]:
    return parse_link_page(PAGE_URL, SOURCE_NAME, LINK_RE, limit=12)
