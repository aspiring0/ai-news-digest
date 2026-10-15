"""Anthropic 官方新闻页（无 RSS，HTML 抓取）。探测 2026-10-15：200，可解析。

稳定性警示：两次探测页面结构不一致（10 条 vs 1 条，疑似按请求降级），
列入 48h 观察期重点；不稳则从 FETCHERS 一行摘除。
"""
from .base import NewsItem, parse_link_page

SOURCE_NAME = "Anthropic"
PAGE_URL = "https://www.anthropic.com/news"
LINK_RE = r"^/news/[a-z0-9-]+$"
SCORE_CLASS = "lab"


def fetch() -> list[NewsItem]:
    return parse_link_page(PAGE_URL, SOURCE_NAME, LINK_RE, limit=15)
