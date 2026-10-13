"""AIHOT 精选（24h 窗口）：中文 AI 资讯精选站，公开 RSS。

注意：AIHOT 曾用域名 aihot.virxact.com，已公告 2026-10-31 起停用，
现用 https://aihot.news/feed.xml（已于 2026-10-13 实测可用）。
"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "AIHOT"
FEED_URL = "https://aihot.news/feed.xml"
# AIHOT 采用上游分：RSS 未带分数，记 None，由 scorer 按规则给 50
SCORE_CLASS = "aihot"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=30)
