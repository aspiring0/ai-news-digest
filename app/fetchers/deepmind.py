"""Google DeepMind 官方博客：官方 RSS（2026-10-13 实测可用）。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "Google DeepMind"
FEED_URL = "https://deepmind.google/blog/rss.xml"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=10)
