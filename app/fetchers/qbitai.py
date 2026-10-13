"""量子位：中文 AI 媒体，官方 RSS。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "量子位"
FEED_URL = "https://www.qbitai.com/feed"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=20)
