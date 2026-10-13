"""MarkTechPost：AI 研究动态媒体（AIHOT 上游之一），官方 RSS。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "MarkTechPost"
FEED_URL = "https://www.marktechpost.com/feed/"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=15)
