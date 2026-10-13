"""VentureBeat AI：英文科技媒体 AI 板块官方 RSS。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "VentureBeat AI"
FEED_URL = "https://venturebeat.com/category/ai/feed/"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=10)
