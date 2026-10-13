"""Hacker News AI 热帖：hnrss.org 官方过滤 feed（>100 赞的 AI 相关帖，无需 key）。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "Hacker News AI"
FEED_URL = "https://hnrss.org/newest?q=AI&points=100"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=15)
