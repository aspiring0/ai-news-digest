"""Tessl 产品与工程博客：AIHOT 上游之一，官方 RSS（2026-10-13 实测可用）。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "Tessl"
FEED_URL = "https://www.tessl.io/blog/rss.xml"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=10)
