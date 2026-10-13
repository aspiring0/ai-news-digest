"""Ars Technica AI：英文科技媒体 AI 板块官方 RSS（AIHOT 上游源之一，2026-10-13 实测可用）。"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "Ars Technica AI"
FEED_URL = "https://arstechnica.com/ai/feed/"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=15)
