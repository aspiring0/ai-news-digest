"""Product Hunt：公开 Atom feed（无需 key），返回当日热门产品。

注意：公开 feed 不带票数，只有标题/链接/时间。
官方 GraphQL API 需要 token，本项目 v0.1 不用。
"""
import logging

import requests

from .base import HEADERS, FETCH_TIMEOUT, NewsItem, parse_rss

logger = logging.getLogger("ai-news-oss")

SOURCE_NAME = "Product Hunt"
FEED_URL = "https://www.producthunt.com/feed"
SCORE_CLASS = "ph"  # 70 起按位置递减


def fetch() -> list[NewsItem]:
    # Atom 格式，parse_rss 用 feedparser 通吃
    return parse_rss(FEED_URL, SOURCE_NAME, limit=15)
