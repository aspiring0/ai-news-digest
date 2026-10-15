"""Microsoft Research 官方博客（实验室一手，RSS）。探测 2026-10-15：200，10 条。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "Microsoft Research"
FEED_URL = "https://www.microsoft.com/en-us/research/feed/"
SCORE_CLASS = "lab"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=15)
