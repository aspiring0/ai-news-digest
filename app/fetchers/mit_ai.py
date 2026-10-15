"""MIT News AI 主题（学术一手，RSS）。探测 2026-10-15：200，50 条。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "MIT News AI"
FEED_URL = "https://news.mit.edu/topic/mitartificial-intelligence2-rss.xml"
SCORE_CLASS = "lab"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=20)
