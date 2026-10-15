"""xAI 官方新闻页（无 RSS，HTML 抓取）。探测 2026-10-15：200，84 条链接。

标题为"标题+描述"粘连锚文本，清洗后截 120 字符，观察期人工过目。
"""
from .base import NewsItem, parse_link_page

SOURCE_NAME = "xAI"
PAGE_URL = "https://x.ai/news"
LINK_RE = r"^/news/[a-z0-9-]+$"
SCORE_CLASS = "lab"


def fetch() -> list[NewsItem]:
    return parse_link_page(PAGE_URL, SOURCE_NAME, LINK_RE, limit=15)
