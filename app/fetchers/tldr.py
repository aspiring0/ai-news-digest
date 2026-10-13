"""TLDR AI：英文 AI Newsletter，官方 RSS（只含标题+链接，无摘要）。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "TLDR AI"
FEED_URL = "https://tldr.tech/api/rss/ai"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=20)
