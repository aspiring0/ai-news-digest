"""NVIDIA 官方博客（厂商一手，RSS）。混合内容（非纯 AI），靠分类器归桶。
探测 2026-10-15：200，18 条。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "NVIDIA Blog"
FEED_URL = "https://blogs.nvidia.com/feed/"
SCORE_CLASS = "lab"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=15)
