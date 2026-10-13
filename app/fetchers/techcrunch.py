"""TechCrunch AI：英文科技媒体 AI 板块，官方 RSS。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "TechCrunch AI"
FEED_URL = "https://techcrunch.com/category/artificial-intelligence/feed/"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=20)
