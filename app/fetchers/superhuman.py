"""Superhuman AI：英文 AI Newsletter。

官方无 RSS，采用社区维护的生成版 RSS（每日从官网归档页抓取更新，
GitHub Action 定时刷新，2026-10-13 实测可用）。
"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "Superhuman"
FEED_URL = "https://raw.githubusercontent.com/dqcenter/feedmint/main/feeds/superhuman-ai.xml"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=20)
