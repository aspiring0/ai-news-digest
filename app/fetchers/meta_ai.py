"""Meta AI 官方博客（无 RSS，HTML 抓取）。探测 2026-10-15：200，可解析。

要点：链接是带尾斜杠的绝对 URL，标题在 aria-label（"Read <标题>"）——
parse_link_page 的尾斜杠归一与 aria-label 优先即为此源实测设计。
"""
from .base import NewsItem, parse_link_page

SOURCE_NAME = "Meta AI"
PAGE_URL = "https://ai.meta.com/blog/"
LINK_RE = r"^https://ai\.meta\.com/blog/[a-z0-9-]+$"
SCORE_CLASS = "lab"


def fetch() -> list[NewsItem]:
    return parse_link_page(PAGE_URL, SOURCE_NAME, LINK_RE, limit=15)
