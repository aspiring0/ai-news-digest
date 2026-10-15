"""Mistral AI 官方新闻（厂商一手）。/news RSS 404，root RSS 即 news 流。
探测 2026-10-15：200，89 条。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "Mistral AI"
FEED_URL = "https://mistral.ai/rss.xml"
SCORE_CLASS = "lab"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=25)
