"""OpenAI 官方 News：官方 RSS（全量归档 feed 很大，只取最新 10 条）。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "OpenAI"
FEED_URL = "https://openai.com/news/rss.xml"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=10)
