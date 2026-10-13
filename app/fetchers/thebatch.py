"""The Batch（DeepLearning.AI / 吴恩达）：英文 AI 周报。

官方页面未暴露 RSS，采用社区维护的生成版 RSS
（2026-10-13 实测可用）。
"""
from .base import NewsItem, parse_rss

SOURCE_NAME = "The Batch"
FEED_URL = "https://raw.githubusercontent.com/SebastianLavertheDe/blog-rss-feed/main/rss/deeplearning_batch_rss.xml"
SCORE_CLASS = "rss"


def fetch() -> list[NewsItem]:
    return parse_rss(FEED_URL, SOURCE_NAME, limit=15)
