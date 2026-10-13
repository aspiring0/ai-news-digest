"""The Rundown AI：英文 AI Newsletter（beehiiv 托管，官方 /feed 可用）。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "The Rundown"
FEED_URL = "https://www.therundown.ai/feed"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=20)
