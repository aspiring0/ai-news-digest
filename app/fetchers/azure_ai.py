"""Azure AI 官方博客（厂商一手，RSS）。探测 2026-10-15：200，10 条。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "Azure AI Blog"
FEED_URL = "https://azure.microsoft.com/en-us/blog/feed/"
SCORE_CLASS = "lab"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=15)
